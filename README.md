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

#### Run with Docker Compose (TorrUpd + FlareSolverr):

To let TorrUpd solve Cloudflare challenges on its own (see [below](#cloudflare-and-flaresolverr)), run it alongside FlareSolverr on a shared network. Grab [`docker-compose.yml`](docker-compose.yml), set ``/PATH/TO/HOST/DIR`` and ``TZ`` in it, then:

```shell
docker compose run --rm torrupd; docker compose down
```

Step by step: FlareSolverr is started, TorrUpd waits until it actually accepts requests (the compose file declares a healthcheck for it), runs once, and its container is removed; then ``down`` stops the solver and removes the network. Nothing is left behind between runs — a fresh solver every time avoids the leaks and stuck browser processes a long-lived headless Chromium tends to accumulate. Note the ``;`` rather than ``&&``: the solver is shut down even if the run fails.

From cron, with a lock so that a long run is never torn down by the next one:

```shell
0 * * * * flock -n /tmp/torrupd.lock -c 'cd /path/to/compose/dir && docker compose run --rm torrupd; docker compose down'
```

If you run TorrUpd often (every few minutes), consider keeping the solver up instead — drop the ``docker compose down`` and it stays in the background, saving a few seconds of startup per run.

Note that ``docker compose up`` is not a good fit here: it is meant for long-living services and would leave the finished TorrUpd container behind in an ``Exited`` state.

With this setup put ``url = http://flaresolverr:8191/v1`` in the ``[FlareSolverr]`` section of ``settings.conf`` — inside the compose network the solver is reachable by its service name.

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
- ``cookie`` and ``useragent`` in ``[RuTracker]`` and ``[NNMClub]`` — see [instructions for obtaining them](README_get_cookie.md).
- ``url`` in ``[FlareSolverr]`` — see [Cloudflare and FlareSolverr](#cloudflare-and-flaresolverr).
- ``dry_run`` in ``[Settings]`` — see [Dry run](#dry-run).
- ``skip_tags`` in ``[Settings]`` — see [Keeping a torrent as is](#keeping-a-torrent-as-is).
- ``url`` in tracker sections — if a tracker URL changes or you want to use a mirror.

**2. ``update.list``**

Topic IDs under the matching tracker sections, one ID per line (a comment may be added). Only needed when ``source`` is set to ``file``.

#### Cloudflare and FlareSolverr:

RuTracker and NNM-Club are behind Cloudflare. TorrUpd impersonates a real browser's TLS fingerprint, which alone is not enough — Cloudflare also issues a clearance cookie that has to be obtained by a browser.

There are two ways to supply it, and they work together:

**1. A cookie from your browser (recommended).** Copy ``cookie`` and ``useragent`` into the tracker's section as described in [README_get_cookie.md](README_get_cookie.md). This covers both the Cloudflare clearance and the tracker login in one go, and typically keeps working for months.

**2. FlareSolverr (optional, automates the rest).** Set ``url`` in the ``[FlareSolverr]`` section, e.g.:

```ini
[FlareSolverr]
url = http://flaresolverr:8191/v1
```

TorrUpd then uses it in two situations:

- If a tracker answers with HTTP 403 at the start of a run, TorrUpd asks FlareSolverr to log in through it and stores the resulting cookie back into ``settings.conf``.
- If Cloudflare raises a challenge in the middle of a run, TorrUpd asks FlareSolverr to solve it for that exact URL and merges the fresh clearance into the cookie it already has, keeping the existing login session intact.

> **Note:** FlareSolverr cannot solve image CAPTCHAs. If a tracker shows one on its login form (RuTracker does), the automatic login will not go through — that case still needs a cookie copied from your browser. Challenge solving mid-run works regardless, since it needs no login.

Without a configured FlareSolverr, TorrUpd simply relies on the cookie from ``settings.conf`` and skips a tracker if Cloudflare blocks it.

#### Dry run:

To see what TorrUpd would do without touching your client, set in ``[Settings]``:

```ini
dry_run = true
```

Trackers are still checked and torrent files are still downloaded, but nothing is removed from or added to the client — every change is only reported in the log:

```
[rutracker] topic 4742818: DRY RUN — would remove "..." (hash ...) and add new torrent "..." at /torrent/manga; no changes made in the torrent client
```

Handy after changing the configuration, or on the very first run against a large list of torrents.

#### Keeping a torrent as is:

Sometimes a release should stay exactly as it is — a hand-picked version, a re-encode you like better than the current one, anything you do not want silently replaced. Tag it in the client and TorrUpd will leave it alone: such a torrent is neither collected from the client nor requested from the tracker.

The tag is set in ``[Settings]``, several may be listed separated by commas (matching is case-insensitive):

```ini
skip_tags = stasis
```

An empty value disables the feature.

> **Note for Transmission:** the mechanism works for both clients, but Transmission only supports labels over RPC — none of its interfaces (GTK, Qt, web) can set them. Use ``transmission-remote HOST:PORT -n user:pass -t <id> -L stasis``, keeping in mind that ``-L`` replaces the whole set of labels rather than adding to it. In qBittorrent, tags are set from the right-click menu as usual.

#### Logs:

Each run writes a log to ``torrent_updater.log`` in the config directory (``$HOME/.config/TorrUpd/`` or ``/PATH/TO/HOST/DIR`` for Docker) and to stdout, so for the Docker container the same output is available via ``docker logs torrupd``. The log covers what was checked, what was updated, and any tracker or client errors. Timestamps follow the system timezone (for Docker, set it via ``-e TZ=``, otherwise UTC is used).

Common messages:

- ``topic <id>: up to date`` — nothing to do.
- ``[client] N torrent(s) excluded by tag (stasis)`` — skipped by ``skip_tags``, reported once per run when ``source = client``.
- ``topic <id>: tagged "stasis", left as is`` — the same thing when ``source = file``, where topics are checked one by one.
- ``topic <id>: change detected (hash differs), updating "..."`` — a new version was found.
- ``topic <id>: no fingerprint on tracker`` — the topic page could not be read: the topic is gone or closed, or the cookie/login has expired.
- ``downloaded data is not a valid torrent`` — a page was returned instead of a torrent file, usually an expired cookie or a Cloudflare challenge.
- ``[flaresolverr] login was not accepted`` — the automatic login hit a CAPTCHA; supply a cookie manually.

For NNM-Club, topics are logged as ``<post id> (<topic id>)``: the first number is what TorrUpd works with (it comes from the torrent's comment field), the second is the human-facing topic number on the site.

## License

MIT — see [LICENSE](LICENSE).