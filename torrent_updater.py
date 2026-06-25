#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import requests
from config import Conf
from bencoder import bdecode, BTFailure
from urllib.parse import urljoin
from tracker import RuTracker, NNMClub, TeamHD, Kinozal, rss_parser


def setup_logging(log_file):
    formatter = logging.Formatter(
        fmt='%(asctime)s\t\t%(levelname)s\t\t%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    root = logging.getLogger()
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
        current_torrent = config.client.get_torrent_by_topic(tracker, topic_id)
        if current_torrent is None:
            logging.warning(
                f'[{tracker}] topic {topic_id}: no matching torrent found in client, skipped'
            )
            continue
        fresh_tracker = trackers[tracker]['incarnation'](
            auth=config.auth[tracker],
            topic_id=topic_id,
            session=sessions[tracker]
        )
        if not fresh_tracker.fingerprint:
            logging.warning(
                f'[{tracker}] topic {topic_id}: no fingerprint on tracker '
                f'(topic removed/closed, or login/layout issue), skipped'
            )
            continue
        current_fingerprint = str(current_torrent[trackers[tracker]['fingerprint']]).lower()
        if current_fingerprint == fresh_tracker.fingerprint.lower():
            logging.info(f'[{tracker}] topic {topic_id}: up to date')
            continue
        logging.info(
            f'[{tracker}] topic {topic_id}: change detected '
            f'({trackers[tracker]["fingerprint"]} differs), updating "{current_torrent["name"]}"'
        )
        new_torrent_name, new_torrent = get_torrent(fresh_tracker, tracker, topic_id)
        if new_torrent_name and new_torrent:
            if not sessions[tracker] and fresh_tracker.session:
                sessions[tracker] = fresh_tracker.session
            data = {
                'category': current_torrent['category'],
                'tags': current_torrent['tags'],
                'path': current_torrent['save_path'],
                'state': current_torrent['state'],
                'tracker': tracker,
                'topic_id': topic_id,
            }
            config.client.remove_torrent(current_torrent['hash'])
            logging.info(
                f'[{tracker}] topic {topic_id}: removed old torrent from client, '
                f'adding new one at {current_torrent["save_path"]}'
            )
            config.client.add_torrent(torrent=new_torrent, data=data)
            logging.info(f'[{tracker}] topic {topic_id}: updated successfully — "{new_torrent_name}"')
            if new_torrent_name != current_torrent['name']:
                logging.warning(
                    f'[{tracker}] topic {topic_id}: torrent name changed '
                    f'"{current_torrent["name"]}" -> "{new_torrent_name}". Duplicate files may appear.'
                )


def main():
    config = Conf()
    setup_logging(config.log_file)
    logging.info('TorrUpd run started')
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
        reachable = False
        for attempt in range(5):
            try:
                response = requests.get(config.auth[tracker]['url'], timeout=30)
            except requests.RequestException as exc:
                logging.error(f'[{tracker}] request failed (attempt {attempt + 1}/5): {exc}')
                continue
            if response.status_code == 200:
                logging.info(
                    f'[{tracker}] reachable, checking {len(config.tracker_ids[tracker])} topic(s)'
                )
                run_through_tracker(config, sessions, tracker, trackers)
                reachable = True
                break
            else:
                logging.warning(
                    f'[{tracker}] HTTP {response.status_code} (attempt {attempt + 1}/5)'
                )
        if not reachable:
            logging.error(f'[{tracker}] unreachable after 5 attempts, skipped')

    logging.info('TorrUpd run finished')


if __name__ == '__main__':
    main()
