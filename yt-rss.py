import aniso8601, feedparser, json, opml, requests, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

smtp_server = "192.168.27.25"
smtp_port = 25
opml_file = "file:///Users/jheese/devel/yt-rss/subscribed.xml"
stored_links_file = "/Users/jheese/devel/yt-rss/yt-links.json"
email = "yt-rss@jonheese.com"
api_key = "AIzaSyA9G1H3eqpUSZJI5Fgs48ySlB1b_omNNPc"
yt_api_url = "https://www.googleapis.com/youtube/v3/videos?id=%s&part=contentDetails&key=%s"

with open(stored_links_file, "r") as fp:
    stored_links = json.load(fp)

outline = opml.parse(opml_file)[0]
august_13th = datetime.fromisoformat("2020-08-13T00:00:00+00:00")
messages = []

for item in outline:
    url = item.xmlUrl
    channel_name = item.title
    entries = feedparser.parse(url).entries
    for entry in entries:
        published_date = datetime.fromisoformat(entry.published)
        duration = str(aniso8601.parse_duration(json.loads(requests.get(yt_api_url % (entry.yt_videoid,
            api_key)).text)['items'][0]['contentDetails']['duration']))
        if entry.link not in stored_links.keys() and published_date > august_13th:
            stored_links[entry.link] = {
                    "title": entry.title,
                    "date": entry.published
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
            message["From"] = email
            message["To"] = email
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

with smtplib.SMTP(smtp_server, smtp_port) as server:
    server.ehlo()
    for message in messages:
        server.sendmail(email, email, message.as_string())

with open(stored_links_file, "w") as fp:
    json.dump(stored_links, fp, indent=2)
