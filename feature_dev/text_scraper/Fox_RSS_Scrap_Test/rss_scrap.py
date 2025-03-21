# List of feed sources:
# https://www.foxnews.com/story/foxnews-com-rss-feeds

from bs4 import BeautifulSoup
import feedparser
import html
import json

rss_url = "https://moxie.foxnews.com/google-publisher/politics.xml"
feed = feedparser.parse(rss_url)
headers = {"User-Agent": "Mozilla/5.0"}

count = 0
for entry in feed.entries:
    article_text = entry.content[0]["value"]

    #print(f"article_text:\n{article_text}\n\n")

    soup = BeautifulSoup(article_text, "html.parser")
    text = ""

    for tag in soup.find_all("p"):
        if not (len(tag.contents) == 1 and tag.find("a")):
            #print(f"{tag.text}\n\n")
            text = text + tag.text + " "
    
    with open(f"./outputs/link_{count}.txt", "w+") as f:
        f.write(f"{html.unescape(entry.title)}\n")
        f.write(f"{entry.link}\n\n")
        f.write("Summary:\n")
        f.write(f"{html.unescape(entry.summary)}\n\n")
        f.write(f"Text:\n")
        f.write(f"{text}\n")

    data_json = {}
    data_json["title"] = html.unescape(entry.title)
    data_json["link"] = entry.link
    data_json["summary"] = html.unescape(entry.summary)
    data_json["text"] = text
    with open(f"./outputs/link_{count}.json", "w+") as f:
        json.dump(data_json, f, indent=4)

    count = count + 1