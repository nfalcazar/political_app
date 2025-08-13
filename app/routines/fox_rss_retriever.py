from bs4 import BeautifulSoup
import feedparser
import json
import html
import logging

logger = logging.getLogger(__name__)

class FoxRssRetriever:
    def __init__(self, out_queue, self_run = False):
        self.self_run = self_run
        self.out_queue = out_queue
        self.rss_feeds = [
            "https://moxie.foxnews.com/google-publisher/politics.xml"       # Fox Politics
        ]
        

    def proc(self):
        logger.debug("Started proc() run")
        count = 0

        for feed_url in self.rss_feeds:
            logger.info(f"Grabbing feed - {feed_url}")
            feed = feedparser.parse(feed_url)

            for entry in feed.entries:
                logger.debug(f"Found - {entry.title}")
                article_text = entry.content[0]["value"]

                soup = BeautifulSoup(article_text, "html.parser")
                # text = ""

                # # Attempt to only grab text, not hyperlinks
                # for tag in soup.find_all("p"):
                #     if not (len(tag.contents) == 1 and tag.find("a")):
                #         text = text + tag.text + " "

                # Trying to send full source from rss so I can grab links to sources


                data_json = {}
                data_json["title"] = html.unescape(entry.title)
                data_json["link"] = entry.link
                data_json["published"] = entry.published
                data_json["summary"] = html.unescape(entry.summary)
                data_json["text"] = str(article_text)

                if self.self_run:
                    # output to files
                    with open(f"./outputs/link_{count}.json", "w+") as f:
                        json.dump(data_json, f, indent=4)
                    count = count + 1
                else:
                    # Normal run (called by controller)
                    self.out_queue.put(data_json)
        logger.debug("Finished proc() run")


if __name__ == "__main__":
    retriever = FoxRssRetriever(None, True)
    retriever.proc()