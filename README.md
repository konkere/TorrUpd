![Torrent updater](/img/TorrUpd.jpg)
A script for automatically checking the relevance of torrents and updating them in the torrent client.

Supports trackers: RuTracker and NNM-Club (hash comparison in topics) and TeamHD (torrent size comparison in RSS, login problem due to reCaptcha).

Supports clients: qBittorrent, Transmission.

#### Host/venv run:
**Python 3.10** required.


``torrent_updater.py`` — main script.

``config.py``, ``client.py``, ``tracker.py`` — related modules.

#### Run in Docker:
``docker run -d --rm --name=torrupd -v /PATH/TO/HOST/DIR:/config ghcr.io/konkere/torrupd``

#### After first run:
Fill data in files in ``$HOME/.config/TorrUpd/`` (or ``/PATH/TO/HOST/DIR`` for Docker) directory:

1. ``settings.conf``:

1.1. ``username`` and ``password`` in tracker sections.

1.2. ``announcekey`` in section ``[RuTracker]`` (optional, crutch for fix broken announcers).

1.3. ``passkey`` in section ``[TeamHD]``

1.4. ``url`` in tracker sections (optional, if the tracker url changes or to use a mirror).

1.5. ``host``, ``username`` and ``password`` in client section (fill out separately for Transmission: ``protocol`` and ``port``).

1.6. in section ``[Settings]`` set ``client`` name and ``source`` for IDs (``file`` is default, ``client`` for check all torrents)

2. ``update.list``:

2.1. ID of topics in the tracker sections (you can add a comment). One line — one topic ID.
