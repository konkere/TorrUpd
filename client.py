#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from qbittorrentapi import Client
from qbittorrentapi.torrents import TorrentDictionary


class TorrentClient:
    def __init__(self, auth):
        self.auth = auth
        self.client = None

    def generate_client(self):
        pass

    def get_torrent_by_hash(self, torrent_hash):
        pass

    def get_torrent_by_topic(self, tracker, topic_id):
        pass

    def remove_torrent(self, torrent_info):
        pass


class QBT(TorrentClient):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = self.generate_client()

    def generate_client(self):
        qbt_client = Client(
            host=self.auth['host'],
            username=self.auth['username'],
            password=self.auth['password'],
            VERIFY_WEBUI_CERTIFICATE=False,
        )
        return qbt_client

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
