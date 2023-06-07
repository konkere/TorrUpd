# Torrent updater

A script for automatically checking the relevance of torrents and updating them in the torrent client.

Supports trackers: RuTracker and NNM-Club.

Supports clients: qBittorrent.

**Python 3.10** required.


``torrent_updater.py`` — main script.

``config.py``, ``client.py``, ``tracker.py`` — related modules.


After first run fill data in files (in ``$HOME/.config/TorrUpd/`` directory):

1. ``settings.conf``:

1.1. ``username`` and ``password`` in tracker sections.

1.2. ``announcekey`` in section ``[RuTracker]`` (optional, crutch for fix broken announcers)

1.3. ``host``, ``username`` and ``password`` in client section.

2. ``update.list``:

2.1. ID of topics in the tracker sections (you can add a comment). One line — one topic ID.
