import aniso8601
import argparse
import feedparser
import httplib2
import json
import oauth2client
import os
import requests
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from googleapiclient import discovery
from oauth2client import file, tools


def main(argv):
    SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    api_service_name = "youtube"
    api_version = "v3"

    parser = argparse.ArgumentParser(
        description="yt-rss args",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[tools.argparser]
    )
    flags = parser.parse_args(argv[1:])

    storage = file.Storage('creds.dat')
    credentials = storage.get()

    yt_api_url = "https://www.googleapis.com/youtube/v3/videos?id=%s&part=contentDetails&key=%s"
    config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)),
        "config.json")
    with open(config_file, "r") as fp:
        config = json.load(fp)
    with open(config["datastore_file"], "r") as fp:
        datastore = json.load(fp)

    if credentials is None or credentials.invalid:
        flow = oauth2client.client.OAuth2WebServerFlow(
            client_id=config.get('client_id'),
            client_secret=config.get('client_secret'),
            scope=SCOPE,
            user_agent="yt-rss",
            oauth_displayname="yt-rss",
        )
        credentials = tools.run_flow(flow, storage, flags)
    http = httplib2.Http()
    http = credentials.authorize(http)


    youtube = discovery.build(
        api_service_name, api_version, credentials=credentials
    )

    items = []
    request = youtube.subscriptions().list(
        part="snippet",
        maxResults=50,
        mine=True,
    )
    while request is not None:
        response = request.execute()
        items.extend(response.get("items"))
        request = youtube.subscriptions().list_next(
            previous_request=request,
            previous_response=response,
        )

    #date_threshold = datetime.fromisoformat("2020-08-13T00:00:00+00:00")
    today = datetime.today()
    if today.month < 7:
        date_threshold = datetime(today.year - 1, today.month + 6, today.day).replace(tzinfo=timezone.utc)
    else:
        date_threshold = datetime(today.year, today.month - 6, today.day).replace(tzinfo=timezone.utc)
    messages = []
    found = False

    # Loop through subscribed channels
    for item in items:
        channel_id = item.get("snippet").get("resourceId").get("channelId")
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        entries = feedparser.parse(url).entries
        # Loop through videos in this channel's feed
        for entry in entries:
            livestream = int(entry.media_statistics["views"]) < 2
            if "published" in entry.keys():
                published_date = datetime.fromisoformat(entry.published)
            elif "updated" in entry.keys():
                published_date = datetime.fromisoformat(entry.updated)
            else:
                # Couldn't find a published/updated date, skip it and hope it's got
                # this data next time
                continue
            # Skip videos we already know about or are older than 8/13/2020
            if entry.link not in datastore.keys() and published_date > date_threshold:
                try:
                    duration_data = json.loads(requests.get(yt_api_url % (entry.yt_videoid, config["api_key"])).text)
                    if "items" in duration_data.keys():
                        duration = str(aniso8601.parse_duration(duration_data['items'][0]['contentDetails']['duration']))
                    else:
                        duration = "Unknown Duration"
                except Exception as e:
                    duration = "Unknown Duration"
                if duration == "0:00:00":
                    livestream = True
                datastore[entry.link] = {
                    "title": entry.title,
                    "date": datetime.isoformat(published_date)
                    }
                print(f"Found new video for channel {entry.author}: {entry.title}")
                image_html = ""
                for thumbnail in entry.media_thumbnail:
                    image_html += f"""<p><img src="{thumbnail['url']}"
                    width="{thumbnail['width']} height="{thumbnail['height']}"
                    /></p>"""
                    if not image_html:
                        image_html = "NO THUMBNAIL"
                message = MIMEMultipart("alternative")
                if livestream:
                    message["Subject"] = f"{item['snippet']['title']} just announced a LIVE STREAM"
                else:
                    message["Subject"] = f"{item['snippet']['title']} just uploaded a video"
                message["From"] = f'YouTube <{config["email"]}>'
                message["To"] = config["email"]
                text = f"""\
                    {entry.title}
                    {entry.link} ({duration})"""
                html = f"""\
                    <html>
                    <body>
                        <a href="{entry.link}">{image_html}</a>
                        <p><a href="{entry.link}">{entry.title}</a>
                        ({duration})</p>
                    </body>
                   </html>
                   """
                message.attach(MIMEText(text, "plain"))
                message.attach(MIMEText(html, "html"))
                messages.append(message)
                found = True

    if found:
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            server.ehlo()
            for message in messages:
                server.sendmail(config["email"], config["email"], message.as_string())

        with open(config["datastore_file"], "w") as fp:
            json.dump(datastore, fp, indent=2)


if __name__ == '__main__':
    main(sys.argv)
