import requests
from bs4 import BeautifulSoup

#url = "https://www.foxnews.com/politics/texas-lawmaker-proposes-bill-targeting-furries-measure-seeks-ban-non-human-behavior-schools"
url = "https://www.foxnews.com/politics/federal-judge-blocks-biden-nursing-home-staffing-mandate"

headers = {"User-Agent": "Mozilla/5.0"}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")

# ChatGPT ex to filter pure links
# Doesn't work, some links are still added to p tags with br for spacing
# for a in soup.find_all("a"):
#     # Strip whitespace from parent text and from anchor text
#     parent_text = a.parent.get_text(strip=True)
#     anchor_text = a.get_text(strip=True)

#     # If they match exactly, the anchor is the only text in its parent
#     if parent_text == anchor_text:
#         # Remove the link (including its text)
#         a.decompose()

# Try throwing out any link with strong tags
# for a in soup.find_all("strong"):
#     print(f"{a}\n")
#     a.decompose()


with open("./fox_article_text.txt", "w+") as f:
    headline = soup.find("h1").get_text()

    article_body = soup.find("div", class_="article-body")

    results = []
    if article_body:
        # filter strong links (assume these are unrelated links)
        for a in article_body.find_all('strong'):
            a.parent.decompose()

        for tag in article_body.find_all("p"):
            print(f"{tag}\n")

            # Remove text from featured vids (based on caption class)
            if "caption" in tag.parent.get('class'):
                continue

            # Remove any link breaks
            for br in tag.find_all("br"):
                br.replace_with('')

            if tag.get_text(strip=True):
                results.append(tag.get_text())


    print("\n\n")
    print(f"{headline}\n\n")
    for item in results:
        print([item])
        f.write(f"{item}")


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