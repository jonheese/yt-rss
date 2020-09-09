import aniso8601, feedparser, json, opml, requests, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


with open("config.json", "r") as fp:
    config = json.load(fp)
yt_api_url = "https://www.googleapis.com/youtube/v3/videos?id=%s&part=contentDetails&key=%s"

with open(config["stored_links_file"], "r") as fp:
    stored_links = json.load(fp)

outline = opml.parse(config["opml_file"])[0]
august_13th = datetime.fromisoformat("2020-08-13T00:00:00+00:00")
messages = []

for item in outline:
    url = item.xmlUrl
    channel_name = item.title
    entries = feedparser.parse(url).entries
    for entry in entries:
        new = False
        if "published" in entry.keys():
            published_date = datetime.fromisoformat(entry.published)
        elif "updated" in entry.keys():
            published_date = datetime.fromisoformat(entry.updated)
        else:
            print(entry.keys())
            new = True
            published_date = datetime.now()
        if entry.link not in stored_links.keys() and (new or published_date > august_13th):
            try:
                duration_data = json.loads(requests.get(yt_api_url % (entry.yt_videoid, config["api_key"])).text)
                if "items" in duration_data.keys():
                    duration = str(aniso8601.parse_duration(duration_data['items'][0]['contentDetails']['duration']))
                else:
                    print(json.dumps(duration_data, indent=2))
                    duration = "Unknown Duration"
            except Exception as e:
                duration = "Unknown Duration"
                print(json.dumps(duration_data, indent=2))
            stored_links[entry.link] = {
                    "title": entry.title,
                    "date": datetime.isoformat(published_date)
                    }
            print(f"Found new video for channel {entry.author}: {entry.title}")
            thumbnail_data = entry.media_thumbnail
            image_html = ""
            for thumbnail in thumbnail_data:
                image_html += f"""<p><img src="{thumbnail['url']}"
                width="{thumbnail['width']} height="{thumbnail['height']}"
                /></p>"""
            if not image_html:
                image_html = "NO THUMBNAIL"
            message = MIMEMultipart("alternative")
            message["Subject"] = f"{channel_name} just uploaded a video"
            message["From"] = config["email"]
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
            part1 = MIMEText(text, "plain")
            part2 = MIMEText(html, "html")
            message.attach(part1)
            message.attach(part2)
            messages.append(message)

with smtplib.SMTP(config["smtp_server"], config["smtp_port"]) as server:
    server.ehlo()
    for message in messages:
        server.sendmail(config["email"], config["email"], message.as_string())

with open(config["stored_links_file"], "w") as fp:
    json.dump(stored_links, fp, indent=2)
