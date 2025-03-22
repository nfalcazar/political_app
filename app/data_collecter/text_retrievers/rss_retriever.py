# TODO: Going to have to confirm feed struct when grabbing feeds from other sites
#       Might be Fox specific file

from bs4 import BeautifulSoup
import feedparser
import json
import html

class RssRetriever:
    def __init__(self, out_queue, self_run = False):
        self.self_run = self_run
        self.out_queue = out_queue
        self.rss_feeds = [
            "https://moxie.foxnews.com/google-publisher/politics.xml"       # Fox Politics
        ]
        

    def proc(self):
        count = 0

        for feed_url in self.rss_feeds:
            feed = feedparser.parse(feed_url)

            for entry in feed.entries:
                article_text = entry.content[0]["value"]

                soup = BeautifulSoup(article_text, "html.parser")
                text = ""

                # Attempt to only grab text, not hyperlinks
                for tag in soup.find_all("p"):
                    if not (len(tag.contents) == 1 and tag.find("a")):
                        text = text + tag.text + " "

                data_json = {}
                data_json["title"] = html.unescape(entry.title)
                data_json["link"] = entry.link
                data_json["summary"] = html.unescape(entry.summary)
                data_json["text"] = text

                if self.self_run:
                    # output to files
                    with open(f"./outputs/link_{count}.json", "w+") as f:
                        json.dump(data_json, f, indent=4)
                    count = count + 1
                else:
                    # Normal run (called by controller)
                    self.out_queue.put(data_json)


if __name__ == "__main__":
    retriever = RssRetriever(None, True)
    retriever.proc()