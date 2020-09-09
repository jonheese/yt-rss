import aniso8601, feedparser, json, opml, os, requests, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


yt_api_url = "https://www.googleapis.com/youtube/v3/videos?id=%s&part=contentDetails&key=%s"
config_file = os.path.join(os.path.dirname(os.path.realpath(__file__)),
    "config.json")
with open(config_file, "r") as fp:
    config = json.load(fp)
with open(config["datastore_file"], "r") as fp:
    datastore = json.load(fp)

outline = opml.parse(config["opml_file"])[0]
august_13th = datetime.fromisoformat("2020-08-13T00:00:00+00:00")
messages = []

# Loop through subscribed channels
for item in outline:
    entries = feedparser.parse(item.xmlUrl).entries
    # Loop through videos in this channel's feed
    for entry in entries:
        if "published" in entry.keys():
            published_date = datetime.fromisoformat(entry.published)
        elif "updated" in entry.keys():
            published_date = datetime.fromisoformat(entry.updated)
        else:
            # Couldn't find a published/updated date, skip it and hope it's got
            # this data next time
            continue
        # Skip videos we already know about or are older than 8/13/2020
        if entry.link not in datastore.keys() and published_date > august_13th:
            try:
                duration_data = json.loads(requests.get(yt_api_url % (entry.yt_videoid, config["api_key"])).text)
                if "items" in duration_data.keys():
                    duration = str(aniso8601.parse_duration(duration_data['items'][0]['contentDetails']['duration']))
                else:
                    duration = "Unknown Duration"
            except Exception as e:
                duration = "Unknown Duration"
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
            message["Subject"] = f"{item.title} just uploaded a video"
            message["From"] = 'YouTube <{config["email"]}>'
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

with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
    server.ehlo()
    for message in messages:
        server.sendmail(config["email"], config["email"], message.as_string())

with open(config["datastore_file"], "w") as fp:
    json.dump(datastore, fp, indent=2)
