#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import requests
from config import Conf
from bencoder import bdecode
from urllib.parse import urljoin
from tracker import RuTracker, NNMClub, TeamHD, rss_parser


def main():
    config = Conf()
    sessions = {}
    trackers = {
        'rutracker': {
            'incarnation': RuTracker,
            'fingerprint': 'hash',
        },
        'nnmclub': {
            'incarnation': NNMClub,
            'fingerprint': 'hash',
        },
        'teamhd': {
            'incarnation': TeamHD,
            'fingerprint': 'size',
            'rssjoin': 'rss.php?feed=dl&passkey='
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
        if trackers[tracker]['fingerprint'] == 'size' and config.tracker_ids[tracker]:
            rss_url = urljoin(config.auth[tracker]["url"], trackers[tracker]["rssjoin"])
            rss_url = f'{rss_url}{config.auth[tracker]["passkey"]}'
            config.tracker_ids[tracker] = rss_parser(rss_url, config.tracker_ids[tracker])
    for tracker in config.tracker_ids.keys():
        response = requests.get(config.auth[tracker]['url'])
        tracker_status = response.status_code
        if tracker_status == 200:
            for topic_id in config.tracker_ids[tracker]:
                current_torrent = config.client.get_torrent_by_topic(tracker, topic_id)
                fresh_tracker = trackers[tracker]['incarnation'](
                    auth=config.auth[tracker],
                    topic_id=topic_id,
                    session=sessions[tracker]
                )
                current_fingerprint = str(current_torrent[trackers[tracker]['fingerprint']]).lower()
                if current_fingerprint != fresh_tracker.fingerprint.lower() and fresh_tracker.fingerprint:
                    new_torrent = fresh_tracker.download_torrent()
                    new_torrent_name = bdecode(new_torrent)[b'info'][b'name'].decode('UTF-8')
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


if __name__ == '__main__':
    main()
