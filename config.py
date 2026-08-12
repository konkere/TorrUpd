#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
from client import QBT, TM
from os import path, getenv, mkdir
from configparser import ConfigParser, NoOptionError, NoSectionError


def work_dir():
    return path.join(getenv('HOME'), '.config', 'TorrUpd')


def log_file_path():
    """
    Resolve the log file before Conf() is built, so that logging is already
    configured when the config starts talking to the torrent client.
    """
    directory = work_dir()
    if not path.isdir(directory):
        mkdir(directory)
    return path.join(directory, 'torrent_updater.log')


def get_ids_from_file(update_file, tracker_ids):
    tracker = None
    tracker_pattern = r'^\[([A-z]*)\]$'
    id_pattern = r'^(\d*)'
    with open(update_file) as file:
        for line in file:
            line = line.strip()
            line_crop = line.lower().replace('[', '').replace(']', '')
            if not line or line[0] == '#':
                continue
            elif any(tracker_name == line_crop for tracker_name in tracker_ids.keys()):
                tracker = re.match(tracker_pattern, line).group(1).lower()
            else:
                topic_id = re.match(id_pattern, line).group(1)
                tracker_ids[tracker].append(topic_id)
    return tracker_ids


def parse_skip_tags(raw):
    if not raw:
        return set()
    return {tag.strip().lower() for tag in raw.split(',') if tag.strip()}


def get_ids_from_client(client, tracker_ids):
    topics = client.all_topics()
    all_trackers = list(topics.keys())
    for tracker in all_trackers:
        if tracker not in tracker_ids.keys():
            del topics[tracker]
    return topics


class Conf:

    # Only trackers that support the Cloudflare-bypass-via-FlareSolverr flow
    # (see tracker.resolve_tracker_access) need their cookie persisted back.
    CF_BYPASS_SECTIONS = {
        'rutracker': 'RuTracker',
        'nnmclub': 'NNMClub',
        'booktracker': 'BookTracker',
    }

    def __init__(self):
        self.work_dir = work_dir()
        self.config_file = path.join(self.work_dir, 'settings.conf')
        self.update_file = path.join(self.work_dir, 'update.list')
        self.log_file = path.join(self.work_dir, 'torrent_updater.log')
        self.config = ConfigParser(interpolation=None)
        self.exist()
        self.config.read(self.config_file)
        self.source = self.read_config('Settings', 'source')
        self.dry_run = self.read_config('Settings', 'dry_run').strip().lower() in ('1', 'true', 'yes', 'on')
        self.skip_tags = parse_skip_tags(self.read_config('Settings', 'skip_tags'))
        self.auth = {
            'rutracker': {
                'url': self.read_config('RuTracker', 'url'),
                'username': self.read_config('RuTracker', 'username'),
                'password': self.read_config('RuTracker', 'password'),
                'announcekey': self.read_config('RuTracker', 'announcekey'),
                'cookie': self.read_config('RuTracker', 'cookie'),
                'useragent': self.read_config('RuTracker', 'useragent'),
                'flaresolverr': self.read_config('FlareSolverr', 'url'),
            },
            'nnmclub': {
                'url': self.read_config('NNMClub', 'url'),
                'cookie': self.read_config('NNMClub', 'cookie'),
                'useragent': self.read_config('NNMClub', 'useragent'),
                'username': self.read_config('NNMClub', 'username'),
                'password': self.read_config('NNMClub', 'password'),
                'flaresolverr': self.read_config('FlareSolverr', 'url'),
            },
            'teamhd': {
                'url': self.read_config('TeamHD', 'url'),
                'passkey': self.read_config('TeamHD', 'passkey'),
            },
            'kinozal': {
                'url': self.read_config('Kinozal', 'url'),
                'username': self.read_config('Kinozal', 'username'),
                'password': self.read_config('Kinozal', 'password'),
            },
            'booktracker': {
                'url': self.read_config('BookTracker', 'url'),
                'username': self.read_config('BookTracker', 'username'),
                'password': self.read_config('BookTracker', 'password'),
                'cookie': self.read_config('BookTracker', 'cookie'),
                'useragent': self.read_config('BookTracker', 'useragent'),
                'flaresolverr': self.read_config('FlareSolverr', 'url'),
            },
            'qbittorrent': {
                'host': self.read_config('qBittorrent', 'host'),
                'username': self.read_config('qBittorrent', 'username'),
                'password': self.read_config('qBittorrent', 'password'),
            },
            'transmission': {
                'protocol':  self.read_config('Transmission', 'protocol'),
                'host': self.read_config('Transmission', 'host'),
                'port': self.read_config('Transmission', 'port'),
                'username': self.read_config('Transmission', 'username'),
                'password': self.read_config('Transmission', 'password'),
            },
        }
        self.client = self.generate_client()
        self.tracker_ids = self.get_ids()

    def generate_client(self):
        clients = {
            'qbittorrent': QBT,
            'transmission': TM,
        }
        client_name = self.read_config('Settings', 'client').lower()
        client = clients[client_name](self.auth[client_name], skip_tags=self.skip_tags)
        return client

    def exist(self):
        if not path.isdir(self.work_dir):
            mkdir(self.work_dir)
        if not path.exists(self.config_file):
            try:
                self.create_config()
            except FileNotFoundError as exc:
                print(exc)
        if not path.exists(self.update_file):
            try:
                self.create_update_file()
            except FileNotFoundError as exc:
                print(exc)

    def create_config(self):
        self.config.add_section('RuTracker')
        self.config.set('RuTracker', 'url', 'https://rutracker.org')
        self.config.set('RuTracker', 'username', 'TRUsername')
        self.config.set('RuTracker', 'password', 'TRPassword')
        self.config.set('RuTracker', 'announcekey', '1a2b3c4d5e6f7g8h9i0j10k11l12m13n')
        self.config.set('RuTracker', 'cookie', '')
        self.config.set('RuTracker', 'useragent', '')
        self.config.add_section('NNMClub')
        self.config.set('NNMClub', 'url', 'https://nnmclub.to')
        self.config.set('NNMClub', 'cookie', '')
        self.config.set('NNMClub', 'useragent', '')
        self.config.set('NNMClub', 'username', 'NNMUsername')
        self.config.set('NNMClub', 'password', 'NNMPassword')
        self.config.add_section('TeamHD')
        self.config.set('TeamHD', 'url', 'https://teamhd.org')
        self.config.set('TeamHD', 'passkey', '1a2b3c4d5e6f7g8h9i0j10k11l12m13n')
        self.config.add_section('Kinozal')
        self.config.set('Kinozal', 'url', 'https://kinozal.tv')
        self.config.set('Kinozal', 'username', 'KTVUsername')
        self.config.set('Kinozal', 'password', 'KTVPassword')
        self.config.add_section('BookTracker')
        self.config.set('BookTracker', 'url', 'https://booktracker.org')
        self.config.set('BookTracker', 'username', 'BTUsername')
        self.config.set('BookTracker', 'password', 'BTPassword')
        self.config.set('BookTracker', 'cookie', '')
        self.config.set('BookTracker', 'useragent', '')
        self.config.add_section('FlareSolverr')
        self.config.set('FlareSolverr', 'url', '')
        self.config.add_section('qBittorrent')
        self.config.set('qBittorrent', 'host', 'qBtHostURL:port')
        self.config.set('qBittorrent', 'username', 'qBtUsername')
        self.config.set('qBittorrent', 'password', 'qBtPassword')
        self.config.add_section('Transmission')
        self.config.set('Transmission', 'protocol', 'http')
        self.config.set('Transmission', 'host', 'TMHostURL')
        self.config.set('Transmission', 'port', 'TMport')
        self.config.set('Transmission', 'username', 'TMUsername')
        self.config.set('Transmission', 'password', 'TMPassword')
        self.config.add_section('Settings')
        self.config.set('Settings', 'client', 'qBittorrent')
        self.config.set('Settings', 'source', 'client')
        self.config.set('Settings', 'dry_run', 'false')
        self.config.set('Settings', 'skip_tags', 'stasis')
        with open(self.config_file, 'w') as file:
            self.config.write(file)
        raise FileNotFoundError(f'Required to fill data in config: {self.config_file}')

    def create_update_file(self):
        update_info = '[RuTracker]\n\n[NNMClub]\n\n[TeamHD]\n\n[Kinozal]\n\n[BookTracker]\n'
        with open(self.update_file, 'w') as file:
            file.write(update_info)
        raise FileNotFoundError(f'Required to fill list of topics id in: {self.update_file}')

    def read_config(self, section, setting):
        try:
            value = self.config.get(section, setting)
        except (NoSectionError, NoOptionError):
            value = ''
        return value

    def persist_cookie(self, tracker_name, cookie, useragent):
        """
        Write a freshly solved Cloudflare cookie back into settings.conf so
        the next run picks it up via the normal read_config() path — no
        separate cache file needed. Note: ConfigParser.write() regenerates
        the whole file and does not preserve comments, so any manual
        comments in settings.conf will be lost the first time this runs.
        """
        section = self.CF_BYPASS_SECTIONS.get(tracker_name)
        if not section:
            return
        self.config.set(section, 'cookie', cookie or '')
        self.config.set(section, 'useragent', useragent or '')
        try:
            with open(self.config_file, 'w') as file:
                self.config.write(file)
            logging.info(f'[{tracker_name}] refreshed Cloudflare cookie saved to {self.config_file}')
        except OSError as exc:
            logging.error(f'[{tracker_name}] failed to persist cookie to {self.config_file}: {exc}')

    def get_ids(self):
        tracker_ids = {
            'rutracker': [],
            'nnmclub': [],
            'teamhd': [],
            'kinozal': [],
            'booktracker': [],
        }
        if self.source == 'file':
            tracker_ids = get_ids_from_file(self.update_file, tracker_ids)
        else:
            tracker_ids = get_ids_from_client(self.client, tracker_ids)
        return tracker_ids
