import html
import requests
from bs4 import BeautifulSoup


class FoxArticleRetriever:
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}


    def grabText(self, link):
        response = requests.get(link, headers=self.headers)
        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.find("h1").get_text()
        article_body = soup.find("div", class_="article-body")

        results = []
        if article_body:
            # filter strong links (assume these are unrelated links)
            for a in article_body.find_all('strong'):
                a.parent.decompose()

            for tag in article_body.find_all("p"):
                # Remove text from featured vids (based on caption class)
                if "caption" in tag.parent.get('class'):
                    continue

                # Remove any link breaks
                for br in tag.find_all("br"):
                    br.replace_with('')

                if tag.get_text(strip=True):
                    results.append(tag.get_text())

        article_text = "".join(results)

        data_json = {}
        data_json["title"] = html.unescape(title)
        data_json["link"] = link
        data_json["summary"] = None
        data_json["text"] = article_text
        return data_json
