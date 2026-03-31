import warnings

warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module="google",
)

import argparse
import json
import logging
import os
import sys
import time

from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from wsgiref.simple_server import make_server
import urllib.parse

import aniso8601
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ===================== CONFIG =====================
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
NUM_MONTHS_BACKLOG = 1
MAX_RETRIES = 3
TOKEN_FILE = "token.json"
API_CALL_COUNT = 0

# ===================== LOGGING =====================
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

logger = logging.getLogger(__name__)

# ===================== AUTH =====================
def get_credentials(config):
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing credentials")
            creds.refresh(Request())
        else:
            logger.info("Running manual loopback OAuth flow (port 8081)")

            flow = InstalledAppFlow.from_client_config(
                {
                    "web": {
                        "client_id": config["client_id"],
                        "client_secret": config["client_secret"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                SCOPES,
            )

            # Required for web client
            flow.redirect_uri = "http://localhost:8081/"

            # IMPORTANT: do NOT include access_type here
            auth_url, _ = flow.authorization_url(prompt="consent")

            print("\nOpen this URL in your browser:\n")
            print(auth_url)
            print("\nWaiting for authorization...\n")

            code_holder = {}

            def app(environ, start_response):
                query = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""))
                if "code" in query:
                    code_holder["code"] = query["code"][0]
                    start_response("200 OK", [("Content-Type", "text/plain")])
                    return [b"Authorization successful. You can close this window."]
                start_response("400 Bad Request", [])
                return [b"Missing authorization code"]

            server = make_server("0.0.0.0", 8081, app)

            while "code" not in code_holder:
                server.handle_request()

            flow.fetch_token(code=code_holder["code"])
            creds = flow.credentials

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds

# ===================== API HELPERS =====================
def execute_request(request):
    global API_CALL_COUNT

    for attempt in range(MAX_RETRIES):
        try:
            API_CALL_COUNT += 1
            return request.execute()
        except HttpError as e:
            logger.warning(f"API error (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError("Max retries exceeded")

def paginated_call(service_method, **kwargs):
    results = []
    request = service_method.list(**kwargs)

    while request is not None:
        response = execute_request(request)
        results.extend(response.get("items", []))
        request = service_method.list_next(request, response)

    return results

# ===================== MAIN =====================
def main():
    setup_logging()

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()

    with open(args.config) as f:
        config = json.load(f)

    with open(config["datastore_file"]) as f:
        datastore = json.load(f)

    creds = get_credentials(config)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    logger.info("Fetching subscriptions")
    channels = paginated_call(youtube.subscriptions(), part="snippet", mine=True)

    date_threshold = datetime.now(timezone.utc) - relativedelta(months=NUM_MONTHS_BACKLOG)
    new_messages = []

    for channel in channels:
        snippet = channel.get("snippet", {})
        channel_title = snippet.get("title")
        channel_id = snippet.get("resourceId", {}).get("channelId")

        if not channel_id:
            continue

        uploads_playlist_id = channel_id.replace("UC", "UU", 1)
        logger.info(f"Checking channel: {channel_title}")

        try:
            response = execute_request(
                youtube.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_playlist_id,
                    maxResults=25,
                )
            )
            videos = response.get('items', [])
        except Exception as e:
            logger.error(f"Failed fetching videos for {channel_title}: {e}")
            continue

        for video in videos:
            v_snippet = video.get("snippet", {})
            video_id = v_snippet.get("resourceId", {}).get("videoId")

            if not video_id:
                continue

            published_str = v_snippet.get("publishedAt")
            published_date = datetime.strptime(
                published_str, "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)

            video_url = f"https://www.youtube.com/watch?v={video_id}"

            if video_url in datastore or published_date < date_threshold:
                continue

            logger.info(f"New video: {channel_title} - {v_snippet.get('title')}")

            try:
                details = execute_request(
                    youtube.videos().list(
                        part="contentDetails,liveStreamingDetails",
                        id=video_id,
                    )
                )
                item = details["items"][0]

                duration = str(aniso8601.parse_duration(item["contentDetails"]["duration"]))
                livestream = (
                    "liveStreamingDetails" in item and
                    "actualStartTime" in item["liveStreamingDetails"]
                )
            except Exception as e:
                logger.warning(f"Failed video details: {video_id} ({e})")
                duration = "Unknown"
                livestream = False

            datastore[video_url] = {
                "channel": channel_title,
                "title": v_snippet.get("title"),
                "date": published_date.isoformat(),
            }

            image_html = ""
            thumbnail = v_snippet.get("thumbnails", {}).get("high")
            if thumbnail is not None and 'url' in thumbnail:
                image_html = f"""<p><img src="{thumbnail['url']}"
                width="{thumbnail['width']} height="{thumbnail['height']}"
                /></p>"""
            else:
                image_html = "NO THUMBNAIL"

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"{channel_title} just {'announced' if livestream else 'uploaded'} a {'LIVE STREAM' if livestream else 'video'}"
            msg["From"] = f'YouTube <{config["email"]}>'
            msg["To"] = config["email"]

            text = f"{v_snippet.get('title')}\n{video_url} ({duration})"
            html = f"""
                <html>
                <body>
                    <a href="{video_url}">{image_html}</a>
                    <p><a href="{video_url}">{v_snippet['title']}</a>
                    ({duration})</p>
                </body>
                </html>"""
            msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html, "html"))

            new_messages.append(msg)

    if new_messages:
        logger.info(f"Sending {len(new_messages)} emails")
        with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
            for msg in new_messages:
                server.sendmail(config["email"], config["email"], msg.as_string())

    # Prune datastore
    prune_threshold = datetime.now(timezone.utc) - relativedelta(months=NUM_MONTHS_BACKLOG + 1)
    datastore = {
        k: v for k, v in datastore.items()
        if datetime.fromisoformat(v["date"]) > prune_threshold
    }

    with open(config["datastore_file"], "w") as f:
        json.dump(datastore, f, indent=2)

    logger.info(f"Total API calls made: {API_CALL_COUNT}")
    logger.info("Done")

if __name__ == "__main__":
    main()
