#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import time
import logging
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from bs4 import BeautifulSoup
from bencoder import bencode, bdecode, BTFailure
from feedparser import parse as feed_parse
from urllib.parse import urljoin, urlsplit, urlunsplit, urlparse, urlencode


def rss_parser(rss_url, ids):
    null_entry_data = {
        'topic_id': '',
        'size': '',
        'download_url': '',
        'name': '',
    }
    result_entries = {guid: null_entry_data for guid in ids}
    guid_pattern = r'\/(\d*)$'
    try:
        feed = feed_parse(rss_url)
    except Exception as exc:
        logging.error(f'[teamhd] RSS fetch/parse failed: {exc}')
        return list(result_entries.values())
    feed_status = getattr(feed, 'status', None)
    if feed_status == 200:
        entries = reversed(feed['entries'])
        for entry in entries:
            try:
                entry_id = re.search(guid_pattern, entry['id']).group(1)
            except (AttributeError, KeyError):
                logging.warning('[teamhd] RSS entry without a parsable id, skipped')
                continue
            if entry_id in ids:
                entry_data = {
                    'topic_id': entry_id,
                    'size': entry['links'][-1]['length'],
                    'download_url': entry['link'],
                    'name': entry['title']
                }
                result_entries[entry_id] = entry_data
    else:
        logging.warning(f'[teamhd] RSS returned status {feed_status} (expected 200)')
    new_ids = list(result_entries.values())
    return new_ids


def _login_response_looks_unauthenticated(html):
    """
    Heuristic check on the page FlareSolverr got back after submitting the
    login POST. A genuinely successful login redirects away from the login
    form; if the response still shows a CAPTCHA prompt or the login form
    itself, the credentials were not actually accepted — most likely a
    CAPTCHA requirement, which neither FlareSolverr nor any scripted client
    can satisfy — even though the HTTP request itself "succeeded" and cookies
    were set (typically just an anonymous session).
    """
    if not html:
        return False
    lowered = html.lower()
    markers = (
        'cap_sid',                    # rutracker/nnmclub CAPTCHA field
        'капч',                       # "капча"/"капчи" etc.
        'код подтверждения',          # CAPTCHA prompt wording
        'name="login_username"',      # rutracker login form still showing
        'name="username"',            # nnmclub login form still showing
    )
    return any(marker in lowered for marker in markers)


def solve_login_via_flaresolverr(flaresolverr_url, login_url, post_params):
    """
    Perform the tracker's own login POST *through* FlareSolverr instead of a
    plain GET. This way the browser solves the Cloudflare challenge and logs
    into the tracker account in one shot, so the returned cookies contain
    both the Cloudflare clearance and the tracker's session cookie together —
    which is what's actually needed to reach pages gated behind a login
    (e.g. a torrent download link), not just to get past Cloudflare itself.

    post_params is the same dict the tracker would otherwise hand to
    requests.Session().post(login_url, data=post_params); it's serialized
    here the same way requests would (urlencode handles str/bytes values
    identically), so the credentials reach the site byte-for-byte the same.

    Returns (cookie_header_string, user_agent) or (None, None) on failure —
    including the case where FlareSolverr reports success but the resulting
    page shows the login was actually rejected (see
    _login_response_looks_unauthenticated). A cookie is only ever returned
    here if it looks like a genuine, logged-in session; the caller persists
    it to settings.conf on the strength of that, so a false "success" here
    would silently clobber a working cookie with a useless one.
    """
    body = urlencode(post_params)
    payload = {
        'cmd': 'request.post',
        'url': login_url,
        'postData': body,
        'maxTimeout': 60000,
    }
    try:
        # No impersonate=: this call goes to our own FlareSolverr instance,
        # not to the tracker's Cloudflare-fronted domain — nothing here needs
        # a browser-like TLS fingerprint. FlareSolverr's headless browser
        # handles that on the actual login request it makes on our behalf.
        response = requests.post(flaresolverr_url, json=payload, timeout=70)
        data = response.json()
    except (RequestException, ValueError) as exc:
        logging.error(f'[flaresolverr] login request failed: {exc}')
        return None, None
    if data.get('status') != 'ok':
        logging.error(f'[flaresolverr] solver status={data.get("status")}: {data.get("message")}')
        return None, None
    solution = data.get('solution', {})
    if _login_response_looks_unauthenticated(solution.get('response', '')):
        logging.error(
            '[flaresolverr] login was not accepted — the response still shows a login '
            'form or CAPTCHA prompt (most likely the site requires solving a CAPTCHA, '
            'which cannot be automated here). Not treating this as a successful login; '
            'any existing cookie in settings.conf is left untouched.'
        )
        return None, None
    cookies = solution.get('cookies', [])
    if not cookies:
        logging.error('[flaresolverr] solver returned no cookies')
        return None, None
    cookie_header = '; '.join(f'{c["name"]}={c["value"]}' for c in cookies)
    user_agent = solution.get('userAgent', '')
    return cookie_header, user_agent


def _merge_cookie_strings(old_cookie_str, new_cookie_str):
    """
    Merge two 'name=value; name2=value2' cookie header strings. Values from
    new_cookie_str win for any name it defines; everything else from
    old_cookie_str is preserved untouched. This matters specifically because
    a fresh anonymous FlareSolverr solve only ever returns Cloudflare's own
    cookies (e.g. cf_clearance) — never a real login session cookie like
    RuTracker's bb_session — so blindly replacing the whole cookie string
    with the new one would silently drop an existing login.
    """
    def parse(cookie_str):
        pairs = {}
        for part in (cookie_str or '').split(';'):
            part = part.strip()
            if not part or '=' not in part:
                continue
            name, _, value = part.partition('=')
            pairs[name.strip()] = value.strip()
        return pairs

    merged = parse(old_cookie_str)
    merged.update(parse(new_cookie_str))
    return '; '.join(f'{name}={value}' for name, value in merged.items())


def solve_challenge_via_flaresolverr(flaresolverr_url, target_url):
    """
    Ask FlareSolverr to pass a Cloudflare challenge for target_url via a
    plain GET — no login involved. Used to recover mid-run when Cloudflare
    re-challenges a request that was working moments ago (observed in
    practice: a bulk run hitting many different topic pages in quick
    succession can trigger this even though the initial reachability ping
    passed fine). A plain GET only yields Cloudflare's own cookies — the
    caller must merge them into any existing, already-authenticated cookie
    rather than replacing it outright (see _merge_cookie_strings); this
    function is not a substitute for solve_login_via_flaresolverr where a
    genuinely authenticated cookie is needed from scratch.

    Returns (cookie_header_string, user_agent) or (None, None) on failure.
    """
    payload = {'cmd': 'request.get', 'url': target_url, 'maxTimeout': 60000}
    try:
        response = requests.post(flaresolverr_url, json=payload, timeout=70)
        data = response.json()
    except (RequestException, ValueError) as exc:
        logging.error(f'[flaresolverr] challenge-solve request failed: {exc}')
        return None, None
    if data.get('status') != 'ok':
        logging.error(f'[flaresolverr] solver status={data.get("status")}: {data.get("message")}')
        return None, None
    solution = data.get('solution', {})
    cookies = solution.get('cookies', [])
    if not cookies:
        logging.error('[flaresolverr] solver returned no cookies')
        return None, None
    cookie_header = '; '.join(f'{c["name"]}={c["value"]}' for c in cookies)
    user_agent = solution.get('userAgent', '')
    return cookie_header, user_agent


def _looks_like_cf_challenge(response):
    """
    Detects a live Cloudflare JS-challenge response (the "Just a moment..."
    interstitial), as opposed to a tracker-level "you're not logged in"
    response (e.g. RuTracker's 302-to-login.php) — only the former can be
    recovered from by re-solving via FlareSolverr; the latter needs a real
    login instead, which this deliberately does not attempt.
    """
    if response.status_code not in (403, 503):
        return False
    if 'html' not in response.headers.get('Content-Type', '').lower():
        return False
    return 'Just a moment' in response.text[:2000]


def resolve_tracker_access(tracker_name, auth, tracker_class, attempts=5):
    """
    Decide, once per run, whether a tracker needs Cloudflare bypassing —
    and if so, establish it — before any topic is processed.

    Model: ping the tracker's plain URL with whatever cookie is already in
    `auth` (loaded from settings.conf — either left there manually, or
    written back by a previous run's successful FlareSolverr login; see
    Conf.persist_cookie). If that gets a normal 200, we're done — the
    tracker's usual username/password session login is used downstream
    exactly as before, no cookie involved at all. If it comes back 403,
    treat that as Cloudflare and, if a FlareSolverr instance is configured,
    log in *through* it — a single request that yields a cookie good for
    both reading topic pages and downloading torrents.

    Mutates `auth` in place (sets/overwrites 'cookie' and 'useragent') only
    when a *new* cookie is obtained via FlareSolverr this call.

    Returns (reachable, refreshed):
      reachable — True if the tracker can be reached one way or another.
      refreshed — True if a new cookie was just solved and needs to be
                  persisted to settings.conf by the caller.
    """
    headers = {}
    if auth.get('cookie'):
        headers['Cookie'] = auth['cookie']
    if auth.get('useragent'):
        headers['User-Agent'] = auth['useragent']

    cf_blocked = False
    for attempt in range(attempts):
        try:
            response = requests.get(auth['url'], headers=headers, impersonate='chrome', timeout=30)
        except RequestException as exc:
            logging.error(f'[{tracker_name}] reachability check failed (attempt {attempt + 1}/{attempts}): {exc}')
            continue
        if response.status_code == 200:
            return True, False
        if response.status_code == 403:
            cf_blocked = True
            break  # retrying against a live Cloudflare challenge won't help
        logging.warning(
            f'[{tracker_name}] HTTP {response.status_code} on reachability check '
            f'(attempt {attempt + 1}/{attempts})'
        )

    if not cf_blocked:
        return False, False

    logging.info(f'[{tracker_name}] HTTP 403 — looks Cloudflare-blocked')
    fs_url = auth.get('flaresolverr')
    if not fs_url:
        logging.error(f'[{tracker_name}] blocked by Cloudflare and no flaresolverr configured, skipping')
        return False, False

    login_url, post_params = tracker_class.login_url_and_params(auth)
    logging.info(f'[{tracker_name}] logging in via FlareSolverr to obtain a Cloudflare + session cookie')
    cookie, useragent = solve_login_via_flaresolverr(fs_url, login_url, post_params)
    if not cookie:
        logging.error(f'[{tracker_name}] FlareSolverr login failed, skipping this run')
        return False, False
    auth['cookie'] = cookie
    auth['useragent'] = useragent
    logging.info(f'[{tracker_name}] Cloudflare bypass established via FlareSolverr')
    return True, True


def extract_base_url(url):
    split_url = urlsplit(url)
    base_url = urlunsplit((split_url.scheme, split_url.netloc, '', '', ''))
    return str(base_url)


def add_subdomain(url, subdomain):
    scheme = urlparse(url).scheme
    netloc = urlparse(url).netloc
    url_sub = urlunsplit((scheme, f'{subdomain}.{netloc}', '', '', ''))
    return url_sub


class Tracker:

    # Fallback used to decode page text when the server does not declare a
    # charset in its Content-Type header. A declared charset always wins, so
    # this only matters for trackers/mirrors that omit it — with curl_cffi
    # the built-in default is utf-8, which mangles cp1251 pages into U+FFFD
    # and breaks parsing (e.g. Kinozal's size field).
    default_encoding = 'utf-8'

    def __init__(self, auth, topic_id, session=None):
        self.auth = auth
        self.topic_id = topic_id
        self.display_id = str(topic_id)
        self.login_url = ''
        self.topic_url = ''
        self.magnet_find = ''
        self.post_params = {
            'login': 'Вход',
        }
        self.session = session
        self.hash_pattern = r'urn:btih:([A-z0-9]*)'
        self.last_topic_response = None
        self.request_headers = {}
        if self.auth.get('cookie'):
            self.request_headers['Cookie'] = self.auth['cookie']
        if self.auth.get('useragent'):
            self.request_headers['User-Agent'] = self.auth['useragent']

    def get_actual_hash(self):
        response = self.authenticated_get(self.topic_url)
        self.last_topic_response = response
        if response is None:
            return ''
        topic = BeautifulSoup(response.text, features='html.parser')
        try:
            magnet = topic.find('a', self.magnet_find).get('href')
            torrent_hash = re.search(self.hash_pattern, magnet).group(1)
        except AttributeError:
            logging.debug(f'magnet link / hash not found on {self.topic_url}')
            torrent_hash = ''
        return torrent_hash

    def create_session(self):
        self.session = requests.Session(
            impersonate='chrome', default_encoding=self.default_encoding
        )
        try:
            self.session.post(self.login_url, data=self.post_params, timeout=30)
        except RequestException as exc:
            logging.error(f'login request to {self.login_url} failed: {exc}')

    def authenticated_get(self, url, attempts=3):
        """
        Fetch `url` the way this run resolved for the tracker: if a cookie is
        present (manual override, or one obtained via FlareSolverr for a
        Cloudflare-blocked tracker), use it directly — no login step needed,
        the cookie already carries a logged-in session. Otherwise fall back
        to the original username/password requests.Session login.

        Both paths impersonate a real browser's TLS fingerprint (via
        curl_cffi) rather than using a plain HTTP client — Cloudflare's bot
        management can tell them apart even with an otherwise valid cookie
        and User-Agent, and does so for these trackers in practice.

        A couple of retries guard against occasional transient connection
        errors (observed in practice as a one-off curl_cffi/OpenSSL hiccup
        that clears up on the very next call) without masking a genuine,
        persistent failure — the URL is simply skipped once attempts run out.

        Separately, if a request in cookie mode comes back as a live
        Cloudflare challenge (not an app-level "not logged in" response, but
        an active "Just a moment..." interstitial — observed in practice
        mid-run, on a request that was working moments earlier, likely
        triggered by hitting many different topic pages back to back), one
        recovery attempt is made: solve the challenge via FlareSolverr (a
        plain GET, no login) and merge the resulting Cloudflare cookies into
        the existing cookie string, preserving whatever login session cookie
        (e.g. bb_session) was already there rather than replacing it.
        """
        use_cookie = bool(self.request_headers.get('Cookie'))
        if not use_cookie and not self.session:
            self.create_session()

        def fetch():
            if use_cookie:
                return requests.get(
                    url, headers=self.request_headers, impersonate='chrome',
                    default_encoding=self.default_encoding, timeout=30,
                )
            return self.session.get(url, timeout=30)

        cf_retried = False
        for attempt in range(attempts):
            try:
                response = fetch()
            except RequestException as exc:
                logging.warning(f'request to {url} failed (attempt {attempt + 1}/{attempts}): {exc}')
                if attempt + 1 < attempts:
                    time.sleep(2)
                continue
            if use_cookie and not cf_retried and _looks_like_cf_challenge(response):
                cf_retried = True
                logging.warning(
                    f'Cloudflare re-challenged mid-run on {url}, attempting a one-off '
                    f'cookie refresh via FlareSolverr'
                )
                if self._refresh_cf_cookie_merged(url):
                    continue
                logging.error(f'could not refresh Cloudflare cookie for {url}')
            return response
        logging.error(f'request to {url} failed after {attempts} attempts')
        return None

    def _refresh_cf_cookie_merged(self, target_url=None):
        fs_url = self.auth.get('flaresolverr')
        if not fs_url:
            return False
        # Solve for the exact URL being fetched, not the site root: Cloudflare
        # can apply different rules per path on these trackers, and clearance
        # obtained on the root does not necessarily cover /forum/ pages.
        new_cookie, useragent = solve_challenge_via_flaresolverr(
            fs_url, target_url or self.auth['url']
        )
        if not new_cookie:
            return False
        # Merge, don't replace — a plain-GET solve only ever yields
        # Cloudflare's own cookies, never a real login session cookie, so
        # replacing outright would silently log the tracker back out.
        # Mutates the shared auth dict too, so any other topic processed
        # later in this same run also benefits immediately. Deliberately not
        # persisted to settings.conf from here — the next run's own
        # reachability ping will re-solve and persist normally if needed.
        merged_cookie = _merge_cookie_strings(self.auth.get('cookie', ''), new_cookie)
        self.auth['cookie'] = merged_cookie
        self.request_headers['Cookie'] = merged_cookie
        if useragent:
            self.auth['useragent'] = useragent
            self.request_headers['User-Agent'] = useragent
        logging.info(
            'Cloudflare cookie refreshed mid-run via FlareSolverr — merged into the '
            'existing cookie, any login session (e.g. bb_session) preserved as-is'
        )
        return True

        return None

    def download_torrent(self):
        pass


class RuTracker(Tracker):

    default_encoding = 'windows-1251'

    @staticmethod
    def login_url_and_params(auth):
        base_url = urljoin(auth['url'], 'forum/')
        login_url = urljoin(base_url, 'login.php')
        post_params = {
            'login': 'Вход',
            'login_username': auth['username'].encode('Windows-1251'),
            'login_password': auth['password'],
        }
        return login_url, post_params

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.login_url, login_params = self.login_url_and_params(self.auth)
        self.post_params.update(login_params)
        self.announce_key = bytes(self.auth['announcekey'], 'UTF-8')
        self.base_url = urljoin(self.auth['url'], 'forum/')
        self.topic_url = urljoin(self.base_url, f'viewtopic.php?t={self.topic_id}')
        self.download_url = urljoin(self.base_url, f'dl.php?t={self.topic_id}')
        self.magnet_find = {'class': 'magnet-link'}
        self.fingerprint = self.get_actual_hash()

    def download_torrent(self):
        response = self.authenticated_get(self.download_url)
        if response is None:
            return None
        torrent_fix = self.fix_announcers(response.content)
        return torrent_fix

    def fix_announcers(self, torrent):
        try:
            torrent_decode = bdecode(torrent)
        except BTFailure:
            logging.warning(
                '[rutracker] downloaded data is not a valid torrent '
                '(Cloudflare challenge page or expired/invalid cookie?)'
            )
            return torrent
        announce_piece = bytes('?pk=', 'UTF-8')
        if announce_piece not in torrent_decode[b'announce'] and self.announce_key:
            torrent_decode[b'announce'] = torrent_decode[b'announce'] + announce_piece + self.announce_key
            try:
                announcers = torrent_decode[b'announce-list']
            except KeyError:
                logging.info('[rutracker] torrent has no announce-list, patched primary announce only')
            else:
                for ann_id, ann in enumerate(announcers):
                    if bytes('.t-ru.org', 'UTF-8') in ann[0]:
                        announce_fix = [ann[0] + bytes(f'?pk={self.announce_key}', 'UTF-8')]
                        announcers[ann_id] = announce_fix
            torrent_encode = bencode(torrent_decode)
            return torrent_encode
        return torrent


class NNMClub(Tracker):

    default_encoding = 'windows-1251'

    @staticmethod
    def login_url_and_params(auth):
        base_url = urljoin(auth['url'], 'forum/')
        login_url = urljoin(base_url, 'login.php')
        post_params = {
            'login': 'Вход',
            'username': auth['username'].encode('Windows-1251'),
            'password': auth['password'],
        }
        return login_url, post_params

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.login_url, login_params = self.login_url_and_params(self.auth)
        self.post_params.update(login_params)
        self.base_url = urljoin(self.auth['url'], 'forum/')
        self.topic_url = urljoin(self.base_url, f'viewtopic.php?p={self.topic_id}')
        self.download_url = ''
        self.magnet_find = {'title': 'Примагнититься'}
        self.fingerprint = self.get_actual_hash()
        self.display_id = self._build_display_id()

    def _build_display_id(self):
        """
        self.topic_id is nnmclub's post id (the `p=` query param) — it's
        what actually came from the torrent's comment field in the client,
        and what topic_url/the hash check are built from, so it stays the
        primary, first-shown number here regardless of anything else. The
        human-recognizable topic number (`t=`) isn't something we request
        directly, but it's normally present somewhere in the topic page's
        own links (breadcrumbs, pagination, "reply" button, etc.) even
        though we reached the page via `p=` — so pull it from the page we
        already fetched, purely as auxiliary info in parentheses, without
        requesting anything extra. Falls back to just the post id if no such
        link is found.
        """
        html = getattr(self.last_topic_response, 'text', '') if self.last_topic_response else ''
        match = re.search(r'viewtopic\.php\?t=(\d+)', html)
        if match and match.group(1) != str(self.topic_id):
            return f'{self.topic_id} ({match.group(1)})'
        return str(self.topic_id)

    def download_torrent(self):
        response = self.authenticated_get(self.topic_url)
        if response is None:
            return None
        self.get_download_url(response)
        if not self.download_url:
            return None
        response = self.authenticated_get(self.download_url)
        return response.content if response is not None else None

    def get_download_url(self, response):
        topic = BeautifulSoup(response.text, features='html.parser')
        try:
            href = topic.find(lambda tag: tag.name == 'a' and 'Скачать' in tag.text).get('href')
        except AttributeError:
            logging.warning(
                f'[nnmclub] download link not found on {self.topic_url} '
                f'(not logged in or cookie expired?)'
            )
            self.download_url = ''
            return
        self.download_url = urljoin(self.base_url, href)


class TeamHD(Tracker):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.download_url = self.topic_id['download_url']
        self.fingerprint = self.topic_id['size']
        self.base_url = extract_base_url(self.download_url)
        self.topic_url = urljoin(self.base_url, f'details/id{self.topic_id["topic_id"]}')

    def download_torrent(self):
        try:
            response = requests.get(self.download_url, timeout=30)
        except RequestException as exc:
            logging.error(f'[teamhd] download failed for {self.download_url}: {exc}')
            return None
        torrent = response.content
        return torrent


class Kinozal(Tracker):

    default_encoding = 'windows-1251'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.post_params['username'] = self.auth['username'].encode('Windows-1251')
        self.post_params['password'] = self.auth['password']
        del self.post_params['login']
        self.base_url = self.auth['url']
        self.login_url = urljoin(self.base_url, 'takelogin.php')
        self.topic_url = urljoin(self.base_url, f'details.php?id={self.topic_id}')
        self.download_url = urljoin(
            add_subdomain(self.base_url, 'dl'), f'download.php?id={self.topic_id}'
        )
        self.fingerprint = self.get_actual_weight()

    def download_torrent(self):
        if not self.session:
            self.create_session()
        torrent = self.session.get(self.download_url).content
        return torrent

    def get_actual_weight(self):
        weight = ''
        for attempt in range(5):
            # Must be authenticated: the tracker redirects anonymous requests
            # for topic pages to login.php, so a plain GET never sees the size.
            response = self.authenticated_get(self.topic_url)
            if response is None:
                logging.error(
                    f'[kinozal] failed to fetch {self.topic_url} '
                    f'(attempt {attempt + 1}/5)'
                )
                continue
            topic = BeautifulSoup(response.text, features='html.parser')
            try:
                weight_field = topic.find('span', {'class': 'floatright green n'}).get_text()
            except AttributeError:
                logging.warning(
                    f'[kinozal] size field not found on {self.topic_url} '
                    f'(attempt {attempt + 1}/5, not logged in or layout changed?)'
                )
            else:
                pattern = r'^[\s\./d\w]*\(([\d\,]*)\)$'
                match = re.match(pattern, weight_field)
                if match:
                    weight = match.group(1).replace(',', '')
                else:
                    logging.warning(
                        f'[kinozal] could not parse size from {weight_field!r} on '
                        f'{self.topic_url} (attempt {attempt + 1}/5, unexpected format '
                        f'or wrong page encoding?)'
                    )
            if weight:
                break
        if not weight:
            logging.error(f'[kinozal] could not read size from {self.topic_url} after 5 attempts')
        return weight
