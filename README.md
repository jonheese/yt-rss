# yt-rss
yt-rss is a simple Python script (`yt-rss.py`) that takes a YouTube subscribed channels opml (xml) file, gets all of the new videos for each of the subscribed channels and sends email notifications to the configured email address with a link to each new video.

# Configuration
1. `cp config-dist.json config.json`
2. `cp datastore-dist.json datastore.json`
3. `vim config.json`, adding:
 - `smtp_server`: your local SMTP server
 - `smtp_port`: your local SMTP server's SMTP port
 - `opml_file`: the URI of your OPML file (eg. `file:///some/path/subscribed.xml`)
 - `datastore_file`: the path to your `datastore.json` (from step 2 above)
 - `email`: your email address
 - `api_key`: your YouTube API key
4. `python3 yt-rss.py` to test that it works
5. Add this to your favorite cron scheduler -- I run it every hour on the hour.
