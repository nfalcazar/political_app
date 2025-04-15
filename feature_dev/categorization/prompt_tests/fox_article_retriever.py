from bs4 import BeautifulSoup
from datetime import datetime
import html
import logging
import os
from pathlib import Path
import requests

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])

class FoxArticleRetriever:
    def __init__(self, save_errors=True):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.data_dir = PROJ_ROOT / "data"
        self.save_errors = save_errors

    # def save_error(self, link, bad_output):
    #     if not self.save_errors:
    #         return

    #     err_path = self.data_dir / f"text_collect_errs/err_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    #     err_path.parent.mkdir(parents=True, exist_ok=True)
    #     with open(err_path, "w+", encoding="utf-8") as f:
    #         f.write(f"{link}\n\n{bad_output.prettify().encode("utf-8")}")
    #     self.error_count += 1
    #     return


    def grabText(self, link):
        try:
            response = requests.get(link, headers=self.headers)
            soup = BeautifulSoup(response.text, "html.parser")
        except:
            #logger.error(f"Unable to grab text for link - {link}")
            return (False, link)

        try:
            title = soup.find("h1").get_text()
        except:
            return (False, link)

        article_body = soup.find("div", class_="article-body")

        results = []
        if article_body:
            #filter strong links (assume these are unrelated links)
            for a in article_body.find_all('strong'):
                if a and a.parent:
                    try:
                        a.parent.decompose()
                    except Exception as e:
                        #logger.warning(f"Error removing strong tag")
                        #self.save_error(link, a)
                        print(e)

            for tag in article_body.find_all("p"):
                # Remove text from featured vids (based on caption class)
                if "caption" in tag.parent.get('class'):
                    continue

                # Remove any link breaks
                for br in tag.find_all("br"):
                    br.replace_with('')

                if tag.get_text(strip=True):
                    results.append(tag.get_text())

        article_text = " ".join(results)

        data_json = {}
        data_json["title"] = html.unescape(title)
        data_json["link"] = link
        data_json["summary"] = None
        data_json["text"] = html.unescape(article_text)
        return (True, data_json)
