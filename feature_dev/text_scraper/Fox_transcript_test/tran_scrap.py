# Want smarter breaking up of text, there are distinct sections which would be nice
# to have already separated out for processing

# Reason for results_b is that I was testing between tag.text and tag.get_text(strip=True)

#TODO: Remember to delete trans_text.txt when I've finished method of categorizing

import requests
from bs4 import BeautifulSoup

url = "https://www.foxnews.com/transcript/fox-news-sunday-october-20-2024"

headers = {"User-Agent": "Mozilla/5.0"}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")


with open("./outputs/trans_text.txt", "w+") as j:
    article_body = soup.find("div", class_="article-body")

    results_b = []
    if article_body:
        
        for tag in soup.find_all("p"):
            # Exclude only links, exclude sections aren't classless or speakable
            if not (len(tag.contents) == 1 and tag.find("a")) and (not tag.get("class") or "speakable" in tag.get("class")):
                for br in tag.find_all("br"):
                    br.replace_with("\n")
                
                results_b.append(tag.text)

    for item in results_b:
        # print([item])
        j.write(f"{item}\n")