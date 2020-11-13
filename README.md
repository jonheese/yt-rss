# yt-rss
yt-rss is a simple Python script (`yt-rss.py`) that will get the YouTube channels a user is subscribed to, get all of the new videos for each of the subscribed channels and send email notifications to the configured email address with a linked thumbnail to each new video.

# Configuration
1. `pip3 install -r requirements.txt`
1. `cp config-dist.json config.json`
2. `cp datastore-dist.json datastore.json`
3. `vim config.json`, adjusting as follows:
 - `smtp_server`: your local SMTP server
 - `smtp_port`: your local SMTP server's SMTP port
 - `datastore_file`: the path to your `datastore.json` (from step 3 above)
 - `email`: your email address
 - `api_key`: your YouTube API key
 - `client_id`: your YouTube API client ID
 - `client_secret`: your YouTube API client secret
4. `python3 yt-rss.py` to test that it works
5. Add this to your favorite cron scheduler -- I run it every hour on the hour.
