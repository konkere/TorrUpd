#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import requests
from config import Conf
from bencoder import bdecode, BTFailure
from urllib.parse import urljoin
from tracker import RuTracker, NNMClub, TeamHD, Kinozal, rss_parser


def get_torrent(tracker):
    torrent = None
    torrent_name = None
    for _ in range(5):
        torrent = tracker.download_torrent()
        try:
            torrent_name = bdecode(torrent)[b'info'][b'name'].decode('UTF-8')
        except BTFailure:
            torrent = None
        else:
            break
    return torrent_name, torrent


def run_through_tracker(config, sessions, tracker, trackers):
    for topic_id in config.tracker_ids[tracker]:
        current_torrent = config.client.get_torrent_by_topic(tracker, topic_id)
        fresh_tracker = trackers[tracker]['incarnation'](
            auth=config.auth[tracker],
            topic_id=topic_id,
            session=sessions[tracker]
        )
        current_fingerprint = str(current_torrent[trackers[tracker]['fingerprint']]).lower()
        if current_fingerprint != fresh_tracker.fingerprint.lower() and fresh_tracker.fingerprint:
            new_torrent_name, new_torrent = get_torrent(fresh_tracker)
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
                    f'The torrent {trackers[tracker]["fingerprint"]} in topic {fresh_tracker.topic_url} has changed. '
                    f'Updating the torrent — {current_torrent["name"]}'
                )
                config.client.add_torrent(torrent=new_torrent, data=data)
                if new_torrent_name != current_torrent['name']:
                    logging.warning(
                        f'The torrent name has changed: {current_torrent["name"]} → {new_torrent_name}. '
                        f'Duplicate files may appear.'
                    )


def main():
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
    }
    logging.basicConfig(
        filename=config.log_file,
        level=logging.INFO,
        format='%(asctime)s\t\t%(levelname)s\t\t%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    for tracker in config.tracker_ids.keys():
        sessions[tracker] = None
        if trackers[tracker]['dl_from'] == 'feed' and config.tracker_ids[tracker]:
            rss_url = urljoin(config.auth[tracker]['url'], trackers[tracker]['rssjoin'])
            rss_url = f'{rss_url}{config.auth[tracker]["passkey"]}'
            config.tracker_ids[tracker] = rss_parser(rss_url, config.tracker_ids[tracker])
    for tracker in config.tracker_ids.keys():
        for _ in range(5):
            response = requests.get(config.auth[tracker]['url'])
            if response.status_code == 200:
                run_through_tracker(config, sessions, tracker, trackers)
                break


if __name__ == '__main__':
    main()
