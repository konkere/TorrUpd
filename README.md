![Torrent updater](/.github/img/TorrUpd.jpg)

Tool for automatically keeping seeded torrents up to date. When a topic on a tracker gets a newer version of a release (a new episode, a better quality, a re-upload), TorrUpd detects the change and replaces the torrent in your client — so you keep seeding the current version without checking trackers by hand.

It runs once per launch: start it, it does its job and exits. Scheduling is up to you (cron, a systemd timer, a Docker container started on a timer — whatever fits).

Supported trackers: RuTracker and NNM-Club (compared by topic hash), Kinozal (compared by torrent size in topics), TeamHD (compared by torrent size in RSS).

Supported clients: qBittorrent, Transmission.

> **Note on TeamHD:** login may fail due to reCaptcha on the tracker side. TeamHD is also checked via its RSS feed, which only lists recent releases — older tracked topics are picked up again once they reappear in the feed (e.g. when re-uploaded).

#### Host/venv run:

**Python 3.10** required.

```shell
git clone https://github.com/konkere/TorrUpd.git
cd TorrUpd
python -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
python torrent_updater.py
```

``torrent_updater.py`` — main script.

``config.py``, ``client.py``, ``tracker.py`` — related modules.

#### Run in Docker:

```shell
docker run -d --rm \
            --name=torrupd \
            -e TZ=Europe/Moscow \
            -v /PATH/TO/HOST/DIR:/config \
            ghcr.io/konkere/torrupd:latest
```

Set ``-e TZ=`` to your own timezone (e.g. ``Europe/Berlin``). Without it the container runs in UTC.

#### After first run:

The first run creates config files in ``$HOME/.config/TorrUpd/`` (or ``/PATH/TO/HOST/DIR`` for Docker). Fill them in, then run again.

**1. ``settings.conf``**

Minimum to get started:

- ``username`` and ``password`` in the tracker sections you use.
- ``host``, ``username`` and ``password`` in the client section (for Transmission also set ``protocol`` and ``port``).
- in ``[Settings]``: ``client`` name, and ``source`` for IDs — ``client`` to check all torrents in the client, ``file`` to check only the list from ``update.list``.

Optional:

- ``announcekey`` in ``[RuTracker]`` — workaround for broken announcers.
- ``passkey`` in ``[TeamHD]``.
- ``cookie`` in ``[NNMClub]`` — see [instructions for obtaining a cookie](README_get_cookie.md).
- ``url`` in tracker sections — if a tracker URL changes or you want to use a mirror.

**2. ``update.list``**

Topic IDs under the matching tracker sections, one ID per line (a comment may be added). Only needed when ``source`` is set to ``file``.

#### Logs:

Each run writes a log to ``torrent_updater.log`` in the config directory (``$HOME/.config/TorrUpd/`` or ``/PATH/TO/HOST/DIR`` for Docker) and to stdout, so for the Docker container the same output is available via ``docker logs torrupd``. The log covers what was checked, what was updated, and any tracker or client errors. Timestamps follow the system timezone (for Docker, set it via ``-e TZ=``, otherwise UTC is used).

## License

MIT — see [LICENSE](LICENSE).