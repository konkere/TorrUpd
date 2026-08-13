#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import time
import hashlib
import logging
from qbittorrentapi import Client as QBT_Client
from transmission_rpc import Client as TM_Client
from bencoder import bencode, bdecode, BTFailure
from qbittorrentapi.torrents import TorrentDictionary


TOPIC_PATTERN = r'^https?://([A-z-]*)\..*[d=](\d*)$'


def torrent_infohash(torrent):
    """
    The v1 infohash of a torrent file: sha1 of its bencoded info dict — the
    same id the client keys torrents by. Computed locally so that a
    just-added torrent can be looked up directly instead of scanning every
    torrent's comment field, which is both slow and racy right after adding.
    Returns '' if the data cannot be decoded, leaving the caller to fall
    back to the comment-based search.
    """
    try:
        info = bdecode(torrent)[b'info']
    except (BTFailure, KeyError, TypeError):
        return ''
    return hashlib.sha1(bencode(info)).hexdigest()


def parse_topic(comment, pattern=TOPIC_PATTERN):
    """
    (tracker, topic_id) out of a torrent comment, or None if the comment is
    not a topic URL we understand. The comment may carry an explicit port
    (https://booktracker.org:443/viewtopic.php?p=111111), hence the loose
    middle part of the pattern.
    """
    match = re.match(pattern, comment or '')
    if not match:
        return None
    tracker_name = match.group(1).replace('-', '').lower()
    topic_id = match.group(2)
    if not tracker_name or not topic_id:
        return None
    return tracker_name, topic_id


def topic_key(topic_id):
    """
    The plain id to match on. For TeamHD topic_id is the whole RSS entry
    (a dict), everywhere else it is already a string.
    """
    if isinstance(topic_id, dict):
        return topic_id.get('topic_id') or ''
    return topic_id or ''


class TorrentClient:
    def __init__(self, auth, skip_tags=None):
        self.auth = auth
        self.skip_tags = skip_tags or set()
        self.client = None
        self.force_state = None
        self.hash_key = 'hash'
        # One snapshot of the client per run (see build_snapshot): the list of
        # (torrent, comment) pairs every lookup works on, plus an index that
        # turns the common case into a dict access. Lives in memory, for the
        # length of the run, and that is all.
        self.entries = None
        self.index = {}

    @staticmethod
    def torrent_tags(torrent):
        return []

    def skipped(self, torrent):
        """
        A torrent carrying one of the skip_tags is left alone entirely: it is
        neither collected from the client nor checked on the tracker. Handy for
        hand-picked releases that must stay exactly as they are.
        """
        if not self.skip_tags:
            return False
        tags = {tag.lower() for tag in self.torrent_tags(torrent)}
        return bool(self.skip_tags & tags)

    def log_skipped(self, count):
        if count:
            logging.info(
                f'[client] {count} torrent(s) excluded by tag '
                f'({", ".join(sorted(self.skip_tags))})'
            )

    def generate_client(self):
        pass

    def iter_torrents(self):
        """Every torrent in the client, in the shape the rest of the code expects."""
        return []

    def torrent_comment(self, torrent):
        return torrent.get('comment') or ''

    def refresh_torrent(self, torrent):
        """Re-read a single torrent, straight from the client."""
        return torrent

    def get_torrent_by_hash(self, torrent_hash):
        pass

    def remove_torrent(self, torrent_info):
        pass

    def build_snapshot(self):
        """
        Walk the client once and keep what was read.

        Both the topic collection and the per-topic lookup need the same
        thing — every torrent together with its comment — so it is fetched
        once per run instead of once per topic. The index covers comments
        that parse as a topic URL; entries keeps the full list for the
        substring fallback, which costs nothing now that it runs in memory.

        The snapshot is built once and never refreshed: it describes the
        client as it was at the start of the run, and the next run starts
        from a fresh read. Nothing is stored between runs.
        """
        entries = []
        index = {}
        skipped = 0
        for torrent in self.iter_torrents():
            # Filtering before reading the comment also saves an API call per
            # skipped torrent whenever the comment lives in a separate request.
            if self.skipped(torrent):
                skipped += 1
                continue
            comment = self.torrent_comment(torrent)
            entries.append((torrent, comment.replace('-', '')))
            topic = parse_topic(comment)
            if topic is not None:
                # First torrent wins, as with the old linear search.
                index.setdefault(topic, torrent)
        self.log_skipped(skipped)
        self.entries = entries
        self.index = index

    def snapshot(self):
        if self.entries is None:
            self.build_snapshot()
        return self.entries

    def get_torrent_by_topic(self, tracker, topic_id):
        self.snapshot()
        key = topic_key(topic_id)
        if not key:
            return None
        torrent = self.index.get((tracker, key))
        if torrent is not None:
            return torrent
        # Fallback for comments the pattern does not parse (a www. prefix, an
        # unusual host layout): same substring test as before, now in memory.
        for torrent, comment in self.entries:
            if tracker in comment and key in comment:
                return torrent
        return None

    def search_torrent_by_topic(self, tracker, topic_id):
        """
        Same search, but straight against the client instead of the snapshot.
        Only for the rare spot where the snapshot is knowingly out of date:
        right after a torrent has been added (see find_added_torrent).
        """
        key = topic_key(topic_id)
        if not key:
            return None
        for torrent in self.iter_torrents():
            comment = self.torrent_comment(torrent).replace('-', '')
            if tracker in comment and key in comment:
                return torrent
        return None

    def all_topics(self):
        self.snapshot()
        topics = {}
        for tracker_name, topic_id in self.index:
            topics.setdefault(tracker_name, []).append(topic_id)
        return topics


class QBT(TorrentClient):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = self.generate_client()
        self.force_state = 'forcedUP'
        # Whether torrents_info() carries the comment field: decided once, by
        # the presence of the key rather than by a version number.
        self.comment_in_info = None

    def generate_client(self):
        client = QBT_Client(
            host=self.auth['host'],
            username=self.auth['username'],
            password=self.auth['password'],
            VERIFY_WEBUI_CERTIFICATE=False,
        )
        return client

    def get_torrent_by_hash(self, torrent_hash):
        torrent = self.client.torrents_info(torrent_hashes=torrent_hash)[0]
        return torrent

    def iter_torrents(self):
        return self.client.torrents_info()

    def torrent_comment(self, torrent):
        """
        Newer WebAPI versions return comment right in torrents_info(), which
        makes the whole run a single request. Older ones keep it in
        /torrents/properties, and TorrentDictionary.properties is not cached
        by qbittorrent-api: every access is another HTTP request.
        """
        if self.comment_in_info is None:
            self.comment_in_info = 'comment' in torrent
            if not self.comment_in_info:
                logging.info(
                    '[client] qBittorrent does not return comment in torrents_info(), '
                    'reading it from properties instead (one request per torrent)'
                )
        if self.comment_in_info:
            return torrent.get('comment') or ''
        return torrent.properties.get('comment') or ''

    def refresh_torrent(self, torrent):
        """
        The snapshot is taken at the start of the run, so by the time a
        torrent is actually updated its state (and, in principle, its path or
        tags) may have moved on — force-start would not be restored for a
        torrent that was still checking back then. One targeted request right
        before the update, only for torrents that are really being updated.
        """
        torrent_hash = torrent.get('hash')
        if not torrent_hash:
            return torrent
        try:
            fresh = self.client.torrents_info(torrent_hashes=torrent_hash)
        except Exception as exc:
            logging.warning(f'[client] failed to re-read torrent {torrent_hash}: {exc}')
            return torrent
        return fresh[0] if fresh else torrent

    def remove_torrent(self, torrent_info):
        torrent_hash = ''
        if isinstance(torrent_info, TorrentDictionary):
            torrent_hash = torrent_info['hash']
        elif isinstance(torrent_info, str):
            torrent_hash = torrent_info
        self.client.torrents_delete(delete_files=False, torrent_hashes=torrent_hash)

    def add_torrent(self, torrent, data):
        # For TeamHD data['topic_id'] is the whole RSS entry (dict) — it stays
        # raw because find_added_torrent() matches on it, but only the plain id
        # is ever put in a log line.
        topic_display = data.get('display_id', data['topic_id'])
        try:
            self.client.torrents_add(
                torrent_files=torrent,
                category=data['category'],
                tags=data['tags'],
                save_path=data['path'],
            )
        except Exception as exc:
            logging.error(
                f'[{data["tracker"]}] topic {topic_display}: failed to add torrent '
                f'to qBittorrent ({data["path"]}): {exc}'
            )
            return
        if data['state'] == self.force_state:
            found = self.find_added_torrent(torrent, data)
            if found is None:
                logging.warning(
                    f'[{data["tracker"]}] topic {topic_display}: added torrent not found '
                    f'right after adding, cannot restore force-start state'
                )
                return
            self.client.torrents.set_force_start(torrent_hashes=found['hash'])

    def find_added_torrent(self, torrent, data, attempts=5, delay=2):
        """
        Locate the torrent that was just handed to qBittorrent.

        torrents_add() only queues the file: the torrent shows up in the API
        a moment later, so a single immediate lookup regularly comes back
        empty and the force-start state is lost for no good reason. Hence a
        few retries with a short pause.

        The lookup itself goes by infohash, computed from the torrent file
        we already have. That is exact, costs one small request per attempt,
        and — unlike matching on the comment field — does not depend on the
        tracker writing the same kind of topic link into the torrent as the
        one the client currently holds. The comment search stays as a
        fallback for the (unlikely) case the file cannot be decoded here —
        and it goes to the client directly, since the run's snapshot still
        holds the torrent that was just replaced.
        """
        torrent_hash = torrent_infohash(torrent)
        for attempt in range(attempts):
            if torrent_hash:
                try:
                    found = self.client.torrents_info(torrent_hashes=torrent_hash)
                except Exception as exc:
                    logging.warning(
                        f'[{data["tracker"]}] topic {data["topic_id"]}: lookup of the added '
                        f'torrent failed (attempt {attempt + 1}/{attempts}): {exc}'
                    )
                    found = []
                if found:
                    return found[0]
            else:
                found = self.search_torrent_by_topic(data['tracker'], data['topic_id'])
                if found is not None:
                    return found
            if attempt + 1 < attempts:
                time.sleep(delay)
        return None

    @staticmethod
    def torrent_tags(torrent):
        # qBittorrent keeps tags as a single comma-separated string; a tag
        # itself cannot contain a comma, so splitting is safe.
        raw = torrent.get('tags') or ''
        return [tag.strip() for tag in raw.split(',') if tag.strip()]


class TM(TorrentClient):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = self.generate_client()
        self.hash_key = 'hashString'

    def generate_client(self):
        client = TM_Client(
            protocol=self.auth['protocol'],
            host=self.auth['host'],
            port=self.auth['port'],
            username=self.auth['username'],
            password=self.auth['password'],
        )
        return client

    def get_torrent_by_hash(self, torrent_hash):
        torrent = self.client.get_torrent(torrent_id=torrent_hash)
        return torrent

    @staticmethod
    def normalized(torrent_tm):
        """Transmission fields plus the keys the rest of the code reads."""
        torrent = torrent_tm.fields
        torrent['hash'] = torrent['hashString']
        torrent['category'] = None
        torrent['tags'] = torrent.get('labels') or []
        torrent['save_path'] = torrent['downloadDir']
        torrent['state'] = None
        # Kinozal and TeamHD compare sizes, not hashes, and look the value up
        # under the qBittorrent spelling. Both report plain bytes, so the
        # numbers are directly comparable.
        torrent['total_size'] = torrent.get('totalSize')
        return torrent

    def iter_torrents(self):
        # get_torrents() already carries the comment in the fields, so the
        # whole list costs exactly one request.
        for torrent_tm in self.client.get_torrents():
            yield self.normalized(torrent_tm)

    def refresh_torrent(self, torrent):
        torrent_hash = torrent.get('hash')
        if not torrent_hash:
            return torrent
        try:
            fresh = self.client.get_torrent(torrent_id=torrent_hash)
        except Exception as exc:
            logging.warning(f'[client] failed to re-read torrent {torrent_hash}: {exc}')
            return torrent
        return self.normalized(fresh)

    def remove_torrent(self, torrent_info):
        torrent_hash = ''
        if isinstance(torrent_info, TorrentDictionary):
            torrent_hash = torrent_info['hash']
        elif isinstance(torrent_info, str):
            torrent_hash = torrent_info
        self.client.remove_torrent(delete_data=False, ids=torrent_hash)

    def add_torrent(self, torrent, data):
        labels = list(data['tags'] or [])
        try:
            self.client.add_torrent(
                torrent=torrent,
                download_dir=data['path'],
                labels=labels,
            )
        except Exception as exc:
            if not labels:
                logging.error(
                    f'[transmission] failed to add torrent to {data["path"]}: {exc}'
                )
                return
            # Labels need RPC 16+ (Transmission 3.0). On an older daemon the
            # call above fails, so retry without them rather than lose the
            # torrent entirely.
            logging.warning(
                f'[transmission] adding torrent with labels failed ({exc}), '
                f'retrying without them — labels {labels} will be lost'
            )
            try:
                self.client.add_torrent(
                    torrent=torrent,
                    download_dir=data['path'],
                )
            except Exception as retry_exc:
                logging.error(
                    f'[transmission] failed to add torrent to {data["path"]}: {retry_exc}'
                )

    @staticmethod
    def torrent_tags(torrent):
        # Transmission calls them labels and exposes them as a list.
        return list(torrent.get('labels') or [])
