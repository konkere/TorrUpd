#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from client import QBT
from config import Conf
from bencoder import bdecode
from tracker import RuTracker, NNMClub


def main():
    config = Conf()
    client = QBT(config.auth['qbittorrent'])
    sessions = {}
    trackers = {
        'rutracker': RuTracker,
        'nnmclub': NNMClub
    }
    logging.basicConfig(
        filename=config.log_file,
        level=logging.INFO,
        format='%(asctime)s\t\t%(levelname)s\t\t%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    for tracker in config.tracker_ids.keys():
        sessions[tracker] = None
    for tracker in config.tracker_ids.keys():
        for topic_id in config.tracker_ids[tracker]:
            current_torrent = client.get_torrent_by_topic(tracker, topic_id)
            fresh_tracker = trackers[tracker](
                auth=config.auth[tracker],
                topic_id=topic_id,
                session=sessions[tracker]
            )
            if current_torrent['hash'].lower() != fresh_tracker.actual_hash.lower():
                new_torrent = fresh_tracker.download_torrent()
                new_torrent_decode = bdecode(new_torrent)
                new_torrent_name = new_torrent_decode[b'info'][b'name'].decode('UTF-8')
                if not sessions[tracker] and fresh_tracker.session:
                    sessions[tracker] = fresh_tracker.session
                data = {
                    'category': current_torrent['category'],
                    'tags': current_torrent['tags'],
                    'path': current_torrent['save_path'],
                }
                client.remove_torrent(current_torrent['hash'])
                logging.info(
                    f'The torrent hash in topic {fresh_tracker.topic_url} has changed. '
                    f'Updating the torrent — {current_torrent["name"]}'
                )
                client.add_torrent(torrent=new_torrent, data=data)
                if new_torrent_name != current_torrent['name']:
                    logging.warning(
                        f'The torrent name has changed: {current_torrent["name"]} → {new_torrent_name}. '
                        f'Duplicate files may appear.'
                    )


if __name__ == '__main__':
    main()
