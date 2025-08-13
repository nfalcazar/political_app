import feedparser
import html
import logging

logger = logging.getLogger(__name__)

class RssGrabber():
    rss_feeds = {
        "Fox": {
            "fox_politics" : "https://moxie.foxnews.com/google-publisher/politics.xml"
        }   
    }

    
    @classmethod
    def grab(cls, feed = None, out_queue = None):
        if feed:
            feeds = [feed]
        else:
            feeds = [
                {"source": source, "url": url}
                for source, feeds_dict in cls.rss_feeds.items()
                for _, url in feeds_dict.items()
            ]
        
        results = []
        for feed in feeds:
            source = feed["source"]
            url = feed["url"]

            parser = cls.get_parser(source)
            if not out_queue:
                results.extend(parser(url))
            else:
                parser(url, out_queue)
        return results


    @classmethod
    def get_parser(cls, source):
        return {
            "Fox": cls.fox_parser
        }[source]


    ############
    ## Parsers
    ############
    @classmethod
    def fox_parser(cls, url, out_queue = None):
        logger.info(f"Grabbing feed - {url}")
        results = []

        feed = feedparser.parse(url)
        for entry in feed.entries:
            logger.debug(f"Found - {entry.title}")
            article_text = entry.content[0]["value"]
            data_json = {}
            data_json["title"] = html.unescape(entry.title)
            data_json["link"] = entry.link
            data_json["published"] = entry.published
            data_json["summary"] = html.unescape(entry.summary)
            data_json["text"] = str(article_text)
            if out_queue:
                out_queue.put(data_json)
            else:
                results.append(data_json)

        return results





