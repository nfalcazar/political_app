import feedparser
import pprint

url = "https://moxie.foxnews.com/google-publisher/politics.xml"
feed = feedparser.parse(url)
# for entry in feed.entries:
#     print(entry.title, entry.link)
#     print()

with open("./outputs/rss_struct.txt", "w+") as f:
    pprint.pp(feed.entries, stream=f)

with open("./outputs/rss_article_list.txt", "w+") as f:
    for entry in feed.entries:
        f.write(f"{entry.title}\n{entry.link}\n\n")
