#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from client import QBT, TM
from os import path, getenv, mkdir
from configparser import ConfigParser, NoOptionError, NoSectionError


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


def get_ids_from_client(client, tracker_ids):
    topics = client.all_topics()
    all_trackers = list(topics.keys())
    for tracker in all_trackers:
        if tracker not in tracker_ids.keys():
            del topics[tracker]
    return topics


class Conf:

    def __init__(self):
        self.work_dir = path.join(getenv('HOME'), '.config', 'TorrUpd')
        self.config_file = path.join(self.work_dir, 'settings.conf')
        self.update_file = path.join(self.work_dir, 'update.list')
        self.log_file = path.join(self.work_dir, 'torrent_updater.log')
        self.config = ConfigParser(interpolation=None)
        self.exist()
        self.config.read(self.config_file)
        self.source = self.read_config('Settings', 'source')
        self.auth = {
            'rutracker': {
                'url': self.read_config('RuTracker', 'url'),
                'username': self.read_config('RuTracker', 'username'),
                'password': self.read_config('RuTracker', 'password'),
                'announcekey': self.read_config('RuTracker', 'announcekey'),
            },
            'nnmclub': {
                'url': self.read_config('NNMClub', 'url'),
                'cookie': self.read_config('NNMClub', 'cookie'),
                'username': self.read_config('NNMClub', 'username'),
                'password': self.read_config('NNMClub', 'password'),
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
        client = clients[client_name](self.auth[client_name])
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
        self.config.add_section('NNMClub')
        self.config.set('NNMClub', 'url', 'https://nnmclub.to')
        self.config.set('NNMClub', 'cookie', '')
        self.config.set('NNMClub', 'username', 'NNMUsername')
        self.config.set('NNMClub', 'password', 'NNMPassword')
        self.config.add_section('TeamHD')
        self.config.set('TeamHD', 'url', 'https://teamhd.org')
        self.config.set('TeamHD', 'passkey', '1a2b3c4d5e6f7g8h9i0j10k11l12m13n')
        self.config.add_section('Kinozal')
        self.config.set('Kinozal', 'url', 'https://kinozal.tv')
        self.config.set('Kinozal', 'username', 'KTVUsername')
        self.config.set('Kinozal', 'password', 'KTVPassword')
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
        with open(self.config_file, 'w') as file:
            self.config.write(file)
        raise FileNotFoundError(f'Required to fill data in config: {self.config_file}')

    def create_update_file(self):
        update_info = '[RuTracker]\n\n[NNMClub]\n\n[TeamHD]\n\n[Kinozal]\n'
        with open(self.update_file, 'w') as file:
            file.write(update_info)
        raise FileNotFoundError(f'Required to fill list of topics id in: {self.update_file}')

    def read_config(self, section, setting):
        try:
            value = self.config.get(section, setting)
        except (NoSectionError, NoOptionError):
            value = ''
        return value

    def get_ids(self):
        tracker_ids = {
            'rutracker': [],
            'nnmclub': [],
            'teamhd': [],
            'kinozal': [],
        }
        if self.source == 'file':
            tracker_ids = get_ids_from_file(self.update_file, tracker_ids)
        else:
            tracker_ids = get_ids_from_client(self.client, tracker_ids)
        return tracker_ids
