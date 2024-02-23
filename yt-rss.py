import aniso8601
import argparse
import httplib2
import json
import oauth2client
import os
import smtplib
import sys
import time
import traceback
from dateutil.relativedelta import relativedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from googleapiclient import discovery
from oauth2client import file, tools

count = 0


def do_list_api_call(youtube=None, endpoint_name=None, part="snippet", max_results=50, params=None,):
    global count
    results = []

    api_endpoint = getattr(youtube, endpoint_name)
    params["part"] = part
    params["maxResults"] = max_results
    request = api_endpoint().list(**params)
    while request is not None:
        count += 1
        response = request.execute()
        results.extend(response.get("items"))
        request = api_endpoint().list_next(
            previous_request=request,
            previous_response=response,
        )
    return results


def log(message):
    now = datetime.now()
    print(f'{now} - {message}')


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

    channels = do_list_api_call(
        youtube=youtube,
        endpoint_name="subscriptions",
        params={"mine": True},
    )

    date_threshold = (datetime.today() - relativedelta(months=6)).replace(tzinfo=timezone.utc)
    messages = []
    found = False
    cancel = False

    # Loop through subscribed channels
    for channel in channels:
        if cancel:
            break
        channel_id = channel.get("snippet").get("resourceId").get("channelId")
        uploads_playlist_id = channel_id.replace("UC", "UU", 1)
        try:
            videos = do_list_api_call(
                youtube=youtube,
                endpoint_name="playlistItems",
                params={
                    "playlistId": uploads_playlist_id,
                },
            )
        except Exception:
            #traceback.print_exc()
            continue

        # Loop through videos in this channel's feed
        for video in videos:
            snippet = video.get("snippet")
            published_date = datetime.strptime(snippet.get("publishedAt"), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            video_id = snippet.get("resourceId").get("videoId")

            video_url = f'https://www.youtube.com/watch?v={video_id}'

            # Skip videos we already know about or are older than 8/13/2020
            if video_url in datastore.keys() or published_date < date_threshold:
                continue

            try:
                streaming_details = do_list_api_call(
                    youtube=youtube,
                    endpoint_name="videos",
                    part="liveStreamingDetails",
                    params={
                        "id": video_id
                    },
                )[0]
                livestream = "liveStreamingDetails" in streaming_details and \
                             "actualStartTime" in streaming_details["liveStreamingDetails"]
            except Exception:
                log(f"Unable to find streaming details for {channel['snippet']['title']}: {snippet['title']}")
                livestream = False

            try:
                duration_data = do_list_api_call(
                    youtube=youtube,
                    endpoint_name="videos",
                    part="contentDetails",
                    params={"id": video_id},
                )
                duration = str(aniso8601.parse_duration(duration_data[0]['contentDetails']['duration']))
            except Exception as e:
                duration = "Unknown Duration"

            datastore[video_url] = {
                "channel": channel['snippet']['title'],
                "title": snippet["title"],
                "date": datetime.isoformat(published_date),
            }
            log(f"Found new video for channel {channel['snippet']['title']}: {snippet['title']}")
            image_html = ""
            thumbnail = snippet.get("thumbnails").get("high")
            if "url" in thumbnail:
                image_html += f"""<p><img src="{thumbnail['url']}"
                width="{thumbnail['width']} height="{thumbnail['height']}"
                /></p>"""
            else:
                image_html = "NO THUMBNAIL"
            message = MIMEMultipart("alternative")
            if livestream:
                message["Subject"] = f"{channel['snippet']['title']} just announced a LIVE STREAM"
            else:
                message["Subject"] = f"{channel['snippet']['title']} just uploaded a video"
            message["From"] = f'YouTube <{config["email"]}>'
            message["To"] = config["email"]
            text = f"""\
                {snippet['title']}
                {video_url} ({duration})"""
            html = f"""\
                <html>
                <body>
                    <a href="{video_url}">{image_html}</a>
                    <p><a href="{video_url}">{snippet['title']}</a>
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
                log(f'Sending mail about message: {message}')
                server.sendmail(config["email"], config["email"], message.as_string())

    pruned = False
    date_threshold = (datetime.today() - relativedelta(months=6, days=1)).replace(tzinfo=timezone.utc)
    for key, item in datastore.copy().items():
        timestamp = datetime.fromisoformat(item["date"]).replace(tzinfo=timezone.utc)
        if timestamp < date_threshold:
            del datastore[key]
            pruned = True

    if found or pruned:
        if pruned:
            log("Performing datastore file pruning")
        with open(config["datastore_file"], "w") as fp:
            json.dump(datastore, fp, indent=2)

    global count
    log(f"I made a total of {count} API calls")


if __name__ == '__main__':
    main(sys.argv)
