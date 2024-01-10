#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from qbittorrentapi import Client as QBT_Client
from transmission_rpc import Client as TM_Client
from qbittorrentapi.torrents import TorrentDictionary


def extract_topics(pattern, comments):
    topics = {}
    for comment in comments:
        re_comment = re.match(pattern, comment)
        try:
            tracker_name = re_comment.group(1)
            topic_id = re_comment.group(2)
        except AttributeError:
            continue
        try:
            topics[tracker_name].append(topic_id)
        except KeyError:
            topics[tracker_name] = [topic_id]
    return topics


class TorrentClient:
    def __init__(self, auth):
        self.auth = auth
        self.client = None
        self.force_state = None
        self.hash_key = 'hash'

    def generate_client(self):
        pass

    def get_torrent_by_hash(self, torrent_hash):
        pass

    def get_torrent_by_topic(self, tracker, topic_id):
        pass

    def remove_torrent(self, torrent_info):
        pass

    def all_topics(self):
        pass


class QBT(TorrentClient):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = self.generate_client()
        self.force_state = 'forcedUP'

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

    def get_torrent_by_topic(self, tracker, topic_id):
        torrents = self.client.torrents_info()
        for torrent in torrents:
            comment = torrent.properties['comment']
            if isinstance(topic_id, dict) and tracker in comment and topic_id['topic_id'] in comment:
                return torrent
            elif isinstance(topic_id, str) and tracker in comment and topic_id in comment:
                return torrent
        return None

    def remove_torrent(self, torrent_info):
        torrent_hash = ''
        if isinstance(torrent_info, TorrentDictionary):
            torrent_hash = torrent_info['hash']
        elif isinstance(torrent_info, str):
            torrent_hash = torrent_info
        self.client.torrents_delete(delete_files=False, torrent_hashes=torrent_hash)

    def add_torrent(self, torrent, data):
        self.client.torrents_add(
            torrent_files=torrent,
            category=data['category'],
            tags=data['tags'],
            save_path=data['path'],
        )
        if data['state'] == self.force_state:
            torrent_hash = self.get_torrent_by_topic(data['tracker'], data['topic_id'])['hash']
            self.client.torrents.set_force_start(torrent_hashes=torrent_hash)

    def all_topics(self):
        pattern = r'^https?://([A-z-]*)\..*[d=](\d*)$'
        dump_torrents = self.client.torrents_info()
        comments = [torrent.properties['comment'] for torrent in dump_torrents]
        topics = extract_topics(pattern, comments)
        return topics


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

    def get_torrent_by_topic(self, tracker, topic_id):
        torrents = self.client.get_torrents()
        for torrent_tm in torrents:
            comment = torrent_tm.comment
            torrent = torrent_tm.fields
            torrent['hash'] = torrent['hashString']
            torrent['category'] = None
            torrent['tags'] = None
            torrent['save_path'] = torrent['downloadDir']
            torrent['state'] = None
            if isinstance(topic_id, dict) and tracker in comment and topic_id['topic_id'] in comment:
                return torrent
            elif isinstance(topic_id, str) and tracker in comment and topic_id in comment:
                return torrent
        return None

    def remove_torrent(self, torrent_info):
        torrent_hash = ''
        if isinstance(torrent_info, TorrentDictionary):
            torrent_hash = torrent_info['hash']
        elif isinstance(torrent_info, str):
            torrent_hash = torrent_info
        self.client.remove_torrent(delete_data=False, ids=torrent_hash)

    def add_torrent(self, torrent, data):
        self.client.add_torrent(
            torrent=torrent,
            download_dir=data['path'],
        )

    def all_topics(self):
        pattern = r'^https?://([A-z-]*)\..*[d=](\d*)$'
        dump_torrents = self.client.get_torrents()
        comments = [torrent.comment for torrent in dump_torrents]
        topics = extract_topics(pattern, comments)
        return topics
