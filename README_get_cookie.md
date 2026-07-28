# Getting `cookie` and `useragent`

RuTracker and NNM-Club sit behind Cloudflare, and both require a login to
download torrent files. The most reliable way to give TorrUpd access is to
copy a working session straight out of your browser.

You need **two** values, and they must come from the **same** browser:
``cookie`` and ``useragent``. Cloudflare ties its clearance cookie to the
User-Agent it was issued to — a valid cookie sent with a different (or
missing) User-Agent is rejected, so copying only the cookie will not work.

## Steps

1. Login to the tracker with your browser.

2. If present on the login page, ensure **Remember me** is ticked and
   **Log Me Out if IP Changes** is unticked.

3. Navigate to any page of the site while logged in (the forum index is fine).

4. Open the DevTools panel by pressing <kbd>F12</kbd>.

5. Select the **Network** tab.

6. Click on the **Doc** button (Chrome) or **HTML** button (Firefox).

7. Refresh the page by pressing <kbd>F5</kbd>.

8. Click on the first row entry.

9. Select the **Headers** tab on the right panel.

10. In the **Request Headers** section, find ``cookie:`` — select and copy the
    whole string (everything after ``cookie: ``) into the ``cookie`` parameter
    of the matching tracker section in ``settings.conf``.

11. In the same **Request Headers** section, find ``user-agent:`` — copy that
    whole string into the ``useragent`` parameter of the same section.

Both values go into the same section, e.g.:

```ini
[RuTracker]
cookie = bb_guid=...; bb_ssl=1; bb_session=...; cf_clearance=...
useragent = Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36
```

## Good to know

- **The cookie is tied to your IP.** Copy it from a browser running on the
  same public IP as TorrUpd. If TorrUpd runs on a server elsewhere, a cookie
  taken from your desktop browser will most likely be rejected.

- **It lasts a while.** Cloudflare's ``cf_clearance`` is often valid for
  months, and the tracker's own session cookie (with *Remember me*) lasts
  even longer — this is not something you have to refresh daily.

- **When it expires** you will see topics logged as *no fingerprint on
  tracker* or downloads failing as *not a valid torrent*. Repeat the steps
  above to get a fresh pair. Configuring [FlareSolverr](README.md#cloudflare-and-flaresolverr)
  lets TorrUpd handle most of these cases on its own.

Steps adapted from [Jackett's Wiki](https://github.com/Jackett/Jackett/wiki/Troubleshooting#your-cookie-did-not-work).