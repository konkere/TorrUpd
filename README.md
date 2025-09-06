![Torrent updater](/.github/img/TorrUpd.jpg)
Tool for automatically checking the relevance of torrents and updating them in the torrent client.

Supports trackers: RuTracker and NNM-Club (hash comparison in topics), Kinozal (torrent size comparison in topics) and TeamHD (torrent size comparison in RSS, login problem due to reCaptcha).

Supports clients: qBittorrent, Transmission.

#### Host/venv run:
**Python 3.10** required.

```shell
git clone https://github.com/konkere/TorrUpd.git
cd TorrUpd
python -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
python torrent_updater.py
````

``torrent_updater.py`` — main script.

``config.py``, ``client.py``, ``tracker.py`` — related modules.

#### Run in Docker:
```shell
docker run -d --rm \
            --name=torrupd \
            -v /PATH/TO/HOST/DIR:/config \
            ghcr.io/konkere/torrupd:latest
```

#### After first run:
Fill data in files in ``$HOME/.config/TorrUpd/`` (or ``/PATH/TO/HOST/DIR`` for Docker) directory:

1. ``settings.conf``:

1.1. ``username`` and ``password`` in tracker sections.

1.2. ``announcekey`` in section ``[RuTracker]`` (optional, crutch for fix broken announcers).

1.3. ``passkey`` in section ``[TeamHD]``

1.4. ``cookie`` in section ``[NNMClub]`` (optional, [instructions for obtaining a cookie](README_get_cookie.md)).

1.5. ``url`` in tracker sections (optional, if the tracker url changes or to use a mirror).

1.6. ``host``, ``username`` and ``password`` in client section (fill out separately for Transmission: ``protocol`` and ``port``).

1.7. in section ``[Settings]`` set ``client`` name and ``source`` for IDs (``client`` for check all torrents, ``file`` for limited checking list from file)

2. ``update.list``:

2.1. ID of topics in the tracker sections (you can add a comment). One line — one topic ID.
