#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import requests
from config import Conf, log_file_path
from bencoder import bdecode, BTFailure
from urllib.parse import urljoin
from tracker import RuTracker, NNMClub, TeamHD, Kinozal, BookTracker, rss_parser, resolve_tracker_access


def setup_logging(log_file):
    formatter = logging.Formatter(
        fmt='%(asctime)s\t\t%(levelname)s\t\t%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    root = logging.getLogger()
    # Drop anything a library (or logging's own basicConfig fallback) may
    # have attached before us, otherwise every record is emitted twice.
    root.handlers.clear()
    root.setLevel(logging.INFO)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)


def get_torrent(tracker, tracker_name, topic_id):
    torrent = None
    torrent_name = None
    for attempt in range(5):
        torrent = tracker.download_torrent()
        try:
            torrent_name = bdecode(torrent)[b'info'][b'name'].decode('UTF-8')
        except BTFailure:
            logging.warning(
                f'[{tracker_name}] topic {topic_id}: downloaded data is not a valid torrent '
                f'(attempt {attempt + 1}/5)'
            )
            torrent = None
        else:
            break
    if not torrent_name or not torrent:
        logging.error(
            f'[{tracker_name}] topic {topic_id}: failed to download a valid torrent after 5 attempts'
        )
    return torrent_name, torrent


def run_through_tracker(config, sessions, tracker, trackers):
    for topic_id in config.tracker_ids[tracker]:
        if isinstance(topic_id, dict) and not topic_id.get('topic_id'):
            continue
        # Log-safe id for the messages emitted before the tracker object (and
        # its display_id) exists: for TeamHD topic_id is the whole RSS entry,
        # whose download_url carries the passkey.
        topic_display = topic_id['topic_id'] if isinstance(topic_id, dict) else topic_id
        current_torrent = config.client.get_torrent_by_topic(tracker, topic_id)
        if current_torrent is None:
            logging.warning(
                f'[{tracker}] topic {topic_display}: no matching torrent found in client, skipped'
            )
            continue
        # Checked here rather than inside get_torrent_by_topic() so that the
        # log says why the torrent was left alone, and so that it works for
        # source = file too, where IDs never pass through all_topics().
        if config.client.skipped(current_torrent):
            logging.info(
                f'[{tracker}] topic {topic_display}: tagged '
                f'"{", ".join(sorted(config.client.skip_tags))}", left as is'
            )
            continue
        fresh_tracker = trackers[tracker]['incarnation'](
            auth=config.auth[tracker],
            topic_id=topic_id,
            session=sessions[tracker]
        )
        # Reuse the login session across topics: creating the tracker may have
        # logged in (e.g. Kinozal reads topic pages authenticated), and logging
        # in once per topic would hammer the tracker's login form.
        if not sessions[tracker] and fresh_tracker.session:
            sessions[tracker] = fresh_tracker.session
        if not fresh_tracker.fingerprint:
            if getattr(fresh_tracker, 'cf_blocked', False):
                # The page never actually loaded, so nothing can be said about
                # the topic itself — commonly the first FlareSolverr solve of
                # the run, which has to start a browser and can outlast the
                # timeout. Later topics usually go through on the warm solver.
                logging.warning(
                    f'[{tracker}] topic {fresh_tracker.display_id}: still behind a Cloudflare '
                    f'challenge after a cookie refresh attempt, skipped — the topic itself '
                    f'was not checked'
                )
            else:
                logging.warning(
                    f'[{tracker}] topic {fresh_tracker.display_id}: no fingerprint on tracker '
                    f'(topic removed/closed, or login/layout issue), skipped'
                )
            continue
        fingerprint_key = trackers[tracker]['fingerprint']
        # A missing value is not a difference: without it there is nothing to
        # compare against, and updating anyway would replace a torrent that
        # may well be up to date. Happens when the client does not report the
        # field at all (e.g. Transmission asked for a narrowed set of fields).
        current_value = current_torrent.get(fingerprint_key)
        if current_value is None or current_value == '':
            logging.warning(
                f'[{tracker}] topic {fresh_tracker.display_id}: client reported no '
                f'"{fingerprint_key}" for "{current_torrent["name"]}", nothing to compare '
                f'against, skipped'
            )
            continue
        current_fingerprint = str(current_value).lower()
        if current_fingerprint == fresh_tracker.fingerprint.lower():
            logging.info(f'[{tracker}] topic {fresh_tracker.display_id}: up to date')
            continue
        logging.info(
            f'[{tracker}] topic {fresh_tracker.display_id}: change detected '
            f'({fingerprint_key} differs), updating "{current_torrent["name"]}"'
        )
        new_torrent_name, new_torrent = get_torrent(fresh_tracker, tracker, fresh_tracker.display_id)
        if new_torrent_name and new_torrent:
            if config.dry_run:
                logging.info(
                    f'[{tracker}] topic {fresh_tracker.display_id}: DRY RUN — would remove '
                    f'"{current_torrent["name"]}" (hash {current_torrent["hash"]}) and add new '
                    f'torrent "{new_torrent_name}" at {current_torrent["save_path"]}; '
                    f'no changes made in the torrent client'
                )
                if new_torrent_name != current_torrent['name']:
                    logging.warning(
                        f'[{tracker}] topic {fresh_tracker.display_id}: DRY RUN — torrent name would change '
                        f'"{current_torrent["name"]}" -> "{new_torrent_name}"'
                    )
                continue
            # The client is read once per run, so state/path/tags come from a
            # snapshot taken before the trackers were walked. Only torrents
            # that are actually being updated are re-read, one request each.
            current_torrent = config.client.refresh_torrent(current_torrent)
            data = {
                'category': current_torrent['category'],
                'tags': current_torrent['tags'],
                'path': current_torrent['save_path'],
                'state': current_torrent['state'],
                'tracker': tracker,
                'topic_id': topic_id,  # raw internal id — must match what topic_url is built from
                'display_id': fresh_tracker.display_id,  # log-safe id (see TeamHD)
            }
            config.client.remove_torrent(current_torrent['hash'])
            logging.info(
                f'[{tracker}] topic {fresh_tracker.display_id}: removed old torrent from client, '
                f'adding new one at {current_torrent["save_path"]}'
            )
            config.client.add_torrent(torrent=new_torrent, data=data)
            logging.info(
                f'[{tracker}] topic {fresh_tracker.display_id}: updated successfully — "{new_torrent_name}"'
            )
            if new_torrent_name != current_torrent['name']:
                logging.warning(
                    f'[{tracker}] topic {fresh_tracker.display_id}: torrent name changed '
                    f'"{current_torrent["name"]}" -> "{new_torrent_name}". Duplicate files may appear.'
                )


def main():
    # Logging first: Conf() already reaches out to the torrent client, and
    # whatever it reports there has to end up in the log like everything else.
    setup_logging(log_file_path())
    logging.info('TorrUpd run started')
    config = Conf()
    sessions = {}
    trackers = {
        'rutracker': {
            'incarnation': RuTracker,
            'fingerprint': 'hash',
            'dl_from': 'topic',
        },
        'nnmclub': {
            'incarnation': NNMClub,
            'fingerprint': 'hash',
            'dl_from': 'topic',
        },
        'teamhd': {
            'incarnation': TeamHD,
            'fingerprint': 'total_size',
            'rssjoin': 'rss.php?feed=dl&passkey=',
            'dl_from': 'feed',
        },
        'kinozal': {
            'incarnation': Kinozal,
            'fingerprint': 'total_size',
            'dl_from': 'topic',
        },
        'booktracker': {
            'incarnation': BookTracker,
            'fingerprint': 'hash',
            'dl_from': 'topic',
        },
    }

    # First pass: prepare RSS feed data (TeamHD only).
    for tracker in config.tracker_ids.keys():
        sessions[tracker] = None
        if trackers[tracker]['dl_from'] == 'feed' and config.tracker_ids[tracker]:
            rss_url = urljoin(config.auth[tracker]['url'], trackers[tracker]['rssjoin'])
            rss_url = f'{rss_url}{config.auth[tracker]["passkey"]}'
            requested = len(config.tracker_ids[tracker])
            logging.info(f'[{tracker}] fetching RSS feed for {requested} topic(s)')
            config.tracker_ids[tracker] = rss_parser(rss_url, config.tracker_ids[tracker])
            resolved = sum(1 for entry in config.tracker_ids[tracker] if entry.get('topic_id'))
            logging.info(f'[{tracker}] RSS resolved {resolved}/{requested} topic(s)')
            if resolved == 0:
                logging.warning(
                    f'[{tracker}] RSS returned no usable entries '
                    f'(passkey/login issue or empty feed?)'
                )

    # Second pass: reach each tracker and run updates.
    for tracker in config.tracker_ids.keys():
        if not config.tracker_ids[tracker]:
            logging.info(f'[{tracker}] no topics configured, skipped')
            continue
        tracker_class = trackers[tracker]['incarnation']
        if hasattr(tracker_class, 'login_url_and_params'):
            # Cloudflare-aware path: ping first, log in through FlareSolverr
            # only if actually blocked. See resolve_tracker_access docstring.
            reachable, refreshed = resolve_tracker_access(tracker, config.auth[tracker], tracker_class)
            if refreshed:
                config.persist_cookie(
                    tracker, config.auth[tracker]['cookie'], config.auth[tracker]['useragent']
                )
        else:
            reachable = False
            for attempt in range(5):
                try:
                    response = requests.get(config.auth[tracker]['url'], timeout=30)
                except requests.RequestException as exc:
                    logging.error(f'[{tracker}] request failed (attempt {attempt + 1}/5): {exc}')
                    continue
                if response.status_code == 200:
                    reachable = True
                    break
                else:
                    logging.warning(
                        f'[{tracker}] HTTP {response.status_code} (attempt {attempt + 1}/5)'
                    )
        if reachable:
            logging.info(
                f'[{tracker}] reachable, checking {len(config.tracker_ids[tracker])} topic(s)'
            )
            run_through_tracker(config, sessions, tracker, trackers)
        else:
            logging.error(f'[{tracker}] unreachable, skipped')

    logging.info('TorrUpd run finished')


if __name__ == '__main__':
    main()
