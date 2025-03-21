import requests
from bs4 import BeautifulSoup

url = "https://www.foxnews.com/politics/texas-lawmaker-proposes-bill-targeting-furries-measure-seeks-ban-non-human-behavior-schools"
headers = {"User-Agent": "Mozilla/5.0"}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")


with open("./fox_article_text.txt", "w+") as f:
    article_body = soup.find("div", class_="article-body")
    lines_to_ignore = [
            "Fox News Flash",
            "By entering your email"
    ]

    results = []
    if article_body:
        
        for tag in soup.find_all("p"):
                # Exclude only links, exclude sections aren't classless or speakable
                if not (len(tag.contents) == 1 and tag.find("a")) and (not tag.get("class") or "speakable" in tag.get("class")):
                    bad_line = False
                    
                    # Attempt to exclude site text not related to article
                    for line in lines_to_ignore:
                         if line in tag.text or tag.find_parent("div", class_="caption"):
                            bad_line = True
                            break
                         
                    if not bad_line:
                        #f.write(f"{tag.text}\n\n")
                        results.append(tag.text)

    for item in results:
        print([item])
        f.write(f"{item} ")


# This approach does grab all elements of text, even those in hyperlinks
# However it results in a lot of clutter, good last case sol
# with open("./fox_article_text.txt", "w+") as f:
#     for tag in soup.find_all(True):
#         #print(tag.name)
#         if tag.name == "p":
#             f.write(f"({tag.name})\t{tag.text}\n\n")


# This approach doesn't find deep nested "p" tags
# article_text = " ".join([p.text for p in soup.find_all("p")])
# with open("./fox_article_text.txt", "w+") as f:
#     f.write(article_text)