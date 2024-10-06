#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import requests
from bs4 import BeautifulSoup
from bencoder import bencode, bdecode
from feedparser import parse as feed_parse
from urllib.parse import urljoin, urlsplit, urlunsplit, urlparse


def rss_parser(rss_url, ids):
    null_entry_data = {
        'topic_id': '',
        'size': '',
        'download_url': '',
        'name': '',
    }
    result_entries = {guid: null_entry_data for guid in ids}
    guid_pattern = r'\/(\d*)$'
    feed = feed_parse(rss_url)
    if feed.status == 200:
        entries = reversed(feed['entries'])
        for entry in entries:
            entry_id = re.search(guid_pattern, entry['id']).group(1)
            if entry_id in ids:
                entry_data = {
                    'topic_id': entry_id,
                    'size': entry['links'][-1]['length'],
                    'download_url': entry['link'],
                    'name': entry['title']
                }
                result_entries[entry_id] = entry_data
    new_ids = list(result_entries.values())
    return new_ids


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

    def __init__(self, auth, topic_id, session=None):
        self.auth = auth
        self.topic_id = topic_id
        self.login_url = ''
        self.topic_url = ''
        self.magnet_find = ''
        self.post_params = {
            'login': 'Вход',
        }
        self.session = session
        self.hash_pattern = r'urn:btih:([A-z0-9]*)'

    def get_actual_hash(self):
        response = requests.get(self.topic_url)
        topic = BeautifulSoup(response.text, features='html.parser')
        try:
            magnet = topic.find('a', self.magnet_find).get('href')
            torrent_hash = re.search(self.hash_pattern, magnet).group(1)
        except AttributeError:
            torrent_hash = ''
        return torrent_hash

    def create_session(self):
        self.session = requests.Session()
        self.session.post(self.login_url, data=self.post_params)

    def download_torrent(self):
        pass


class RuTracker(Tracker):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.post_params['login_username'] = self.auth['username'].encode('Windows-1251')
        self.post_params['login_password'] = self.auth['password']
        self.announce_key = bytes(self.auth['announcekey'], 'UTF-8')
        self.base_url = urljoin(self.auth['url'], 'forum/')
        self.login_url = urljoin(self.base_url, 'login.php')
        self.topic_url = urljoin(self.base_url, f'viewtopic.php?t={self.topic_id}')
        self.download_url = urljoin(self.base_url, f'dl.php?t={self.topic_id}')
        self.magnet_find = {'class': 'magnet-link'}
        self.fingerprint = self.get_actual_hash()

    def download_torrent(self):
        if not self.session:
            self.create_session()
        torrent = self.session.get(self.download_url).content
        torrent_fix = self.fix_announcers(torrent)
        return torrent_fix

    def fix_announcers(self, torrent):
        torrent_decode = bdecode(torrent)
        announce_piece = bytes('?pk=', 'UTF-8')
        if announce_piece not in torrent_decode[b'announce'] and self.announce_key:
            torrent_decode[b'announce'] = torrent_decode[b'announce'] + announce_piece + self.announce_key
            try:
                announcers = torrent_decode[b'announce-list']
            except KeyError:
                pass
            else:
                for ann_id, ann in enumerate(announcers):
                    if bytes('.t-ru.org', 'UTF-8') in ann[0]:
                        announce_fix = [ann[0] + bytes(f'?pk={self.announce_key}', 'UTF-8')]
                        announcers[ann_id] = announce_fix
            torrent_encode = bencode(torrent_decode)
            return torrent_encode
        return torrent


class NNMClub(Tracker):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.post_params['username'] = self.auth['username'].encode('Windows-1251')
        self.post_params['password'] = self.auth['password']
        self.base_url = urljoin(self.auth['url'], 'forum/')
        self.login_url = urljoin(self.base_url, 'login.php')
        self.topic_url = urljoin(self.base_url, f'viewtopic.php?p={self.topic_id}')
        self.download_url = ''
        self.magnet_find = {'title': 'Примагнититься'}
        self.fingerprint = self.get_actual_hash()

    def download_torrent(self):
        if not self.session:
            self.create_session()
        self.download_url = urljoin(self.base_url, self.get_download_href())
        torrent = self.session.get(self.download_url).content
        return torrent

    def get_download_href(self):
        response = self.session.get(self.topic_url)
        topic = BeautifulSoup(response.text, features='html.parser')
        href = topic.find(lambda tag: tag.name == 'a' and 'Скачать' in tag.text).get('href')
        return href


class TeamHD(Tracker):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.download_url = self.topic_id['download_url']
        self.fingerprint = self.topic_id['size']
        self.base_url = extract_base_url(self.download_url)
        self.topic_url = urljoin(self.base_url, f'details/id{self.topic_id["topic_id"]}')

    def download_torrent(self):
        response = requests.get(self.download_url)
        torrent = response.content
        return torrent


class Kinozal(Tracker):

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
        response = requests.get(self.topic_url)
        topic = BeautifulSoup(response.text, features='html.parser')
        try:
            weight_field = topic.find('span', {'class': 'floatright green n'}).get_text()
        except AttributeError:
            weight = ''
        else:
            pattern = r'^[\s\./d\w]*\(([\d\,]*)\)$'
            weight = re.match(pattern, weight_field).group(1)
            weight = weight.replace(',', '')
        return weight
