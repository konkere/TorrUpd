#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
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
        tracker_name = tracker_name.replace('-', '')
        try:
            topics[tracker_name].append(topic_id)
        except KeyError:
            topics[tracker_name] = [topic_id]
    return topics


class TorrentClient:
    def __init__(self, auth, skip_tags=None):
        self.auth = auth
        self.skip_tags = skip_tags or set()
        self.client = None
        self.force_state = None
        self.hash_key = 'hash'

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
            comment = torrent.properties['comment'].replace('-', '')
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
        try:
            self.client.torrents_add(
                torrent_files=torrent,
                category=data['category'],
                tags=data['tags'],
                save_path=data['path'],
            )
        except Exception as exc:
            logging.error(
                f'[{data["tracker"]}] topic {data["topic_id"]}: failed to add torrent '
                f'to qBittorrent ({data["path"]}): {exc}'
            )
            return
        if data['state'] == self.force_state:
            found = self.get_torrent_by_topic(data['tracker'], data['topic_id'])
            if found is None:
                logging.warning(
                    f'[{data["tracker"]}] topic {data["topic_id"]}: added torrent not found '
                    f'right after adding, cannot restore force-start state'
                )
                return
            self.client.torrents.set_force_start(torrent_hashes=found['hash'])

    @staticmethod
    def torrent_tags(torrent):
        # qBittorrent keeps tags as a single comma-separated string; a tag
        # itself cannot contain a comma, so splitting is safe.
        raw = torrent.get('tags') or ''
        return [tag.strip() for tag in raw.split(',') if tag.strip()]

    def all_topics(self):
        pattern = r'^https?://([A-z-]*)\..*[d=](\d*)$'
        comments = []
        skipped = 0
        for torrent in self.client.torrents_info():
            # Filtering before reading properties also saves one API call per
            # skipped torrent, since properties is a separate request.
            if self.skipped(torrent):
                skipped += 1
                continue
            comments.append(torrent.properties['comment'])
        self.log_skipped(skipped)
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
            comment = torrent_tm.comment.replace('-', '')
            torrent = torrent_tm.fields
            torrent['hash'] = torrent['hashString']
            torrent['category'] = None
            torrent['tags'] = torrent.get('labels') or []
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

    def all_topics(self):
        pattern = r'^https?://([A-z-]*)\..*[d=](\d*)$'
        comments = []
        skipped = 0
        for torrent in self.client.get_torrents():
            if self.skipped(torrent.fields):
                skipped += 1
                continue
            comments.append(torrent.comment)
        self.log_skipped(skipped)
        topics = extract_topics(pattern, comments)
        return topics
