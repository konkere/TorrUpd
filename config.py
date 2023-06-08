#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from os import path, getenv, mkdir
from configparser import ConfigParser


class Conf:

    def __init__(self):
        self.work_dir = path.join(getenv('HOME'), '.config', 'TorrUpd')
        self.config_file = path.join(self.work_dir, 'settings.conf')
        self.update_file = path.join(self.work_dir, 'update.list')
        self.log_file = path.join(self.work_dir, 'torrent_updater.log')
        self.config = ConfigParser()
        self.exist()
        self.tracker_ids = self.read_update_file()
        self.config.read(self.config_file)
        self.auth = {
            'rutracker': {
                'url': self.read_config('RuTracker', 'url'),
                'username': self.read_config('RuTracker', 'username'),
                'password': self.read_config('RuTracker', 'password'),
                'announcekey': self.read_config('RuTracker', 'announcekey'),
            },
            'nnmclub': {
                'url': self.read_config('NNMClub', 'url'),
                'username': self.read_config('NNMClub', 'username'),
                'password': self.read_config('NNMClub', 'password'),
            },
            'qbittorrent': {
                'host': self.read_config('qBittorrent', 'host'),
                'username': self.read_config('qBittorrent', 'username'),
                'password': self.read_config('qBittorrent', 'password'),
            },
        }

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
        self.config.add_section('NNMClub')
        self.config.set('NNMClub', 'url', 'https://nnmclub.to')
        self.config.set('NNMClub', 'username', 'NNMUsername')
        self.config.set('NNMClub', 'password', 'NNMPassword')
        self.config.add_section('qBittorrent')
        self.config.set('qBittorrent', 'host', 'qBtHostURL:port')
        self.config.set('qBittorrent', 'username', 'qBtUsername')
        self.config.set('qBittorrent', 'password', 'qBtPassword')
        with open(self.config_file, 'w') as file:
            self.config.write(file)
        raise FileNotFoundError(f'Required to fill data in config: {self.config_file}')

    def create_update_file(self):
        update_info = '[RuTracker]\n\n[NNMClub]\n'
        with open(self.update_file, 'w') as file:
            file.write(update_info)
        raise FileNotFoundError(f'Required to fill list of topics id in: {self.update_file}')

    def read_config(self, section, setting):
        value = self.config.get(section, setting)
        return value

    def read_update_file(self):
        tracker = None
        tracker_ids = {
            'rutracker': [],
            'nnmclub': [],
        }
        tracker_pattern = r'^\[([A-z]*)\]$'
        id_pattern = r'^(\d*)'
        with open(self.update_file) as file:
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
