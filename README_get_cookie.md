1. Login to this tracker with your browser

2. If present in the login page, ensure you have the Remember me ticked and the Log Me Out if IP Changes unticked when you login

3. Navigate to the web site's torrent search page to view the list of available torrents for download

4. Open the DevTools panel by pressing F12

5. Select the Network tab

6. Click on the Doc button (Chrome Browser) or HTML button (FireFox)

7. Refresh the page by pressing F5

8. Click on the first row entry

9. Select the Headers tab on the Right panel

10. Find 'cookie:' in the Request Headers section

11. Select and Copy the whole cookie string (everything after 'cookie: ') and Paste it into parameter ``cookie`` section ``[NNMClub]`` in ``settings.conf`` file'.

Taken from [Jackett's Wiki](https://github.com/Jackett/Jackett/wiki/Troubleshooting#your-cookie-did-not-work).
