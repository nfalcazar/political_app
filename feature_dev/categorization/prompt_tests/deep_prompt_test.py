from openai import OpenAI
import sys
import json
import os

import multiprocessing as mp

sys.path.insert(1, "/home/nalc/Keyring")
from pol_app_deepseek import deepseek_key

from fox_article_retriever import FoxArticleRetriever

# Grab text of RSS articles
# edu_file = "../../text_scraper/Fox_RSS_Scrap_Test/outputs/link_3.json"
# with open(edu_file, "r") as f:
#     article = json.load(f)

# Grab from fox web article
url = "https://www.foxnews.com/politics/fani-willis-thinks-shes-above-law-georgia-lawmaker-subpoena-fight-says"

# Grab Prompt
#prompt_name = "gpt4.5_gen_v1"
#prompt_name = "gpt4.5_gen_v1_w_ids"
#prompt_name = "gpt4.5_goal_claim_split"
#prompt_name = "summ_and_quote"
#prompt_name = "summ_and_quote2"
#prompt_name = "canon_claim_test"
prompt_name = "canon_supp_refut_claims"
with open(f"./prompts/{prompt_name}.txt", "r") as f:
    prompt = f.read()

# deepseek rotation
client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
dir_name = "./outputs"

queue = mp.Queue()

fox_retr = FoxArticleRetriever()
ret, article = fox_retr.grabText(url)
print(ret)

queue.put(article)
article = queue.get(article)

full_prompt = f"{prompt}\n\nTitle:\n{article['title']}\n\nText:\n{article['text']}"
try:
    completion = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[{
            "role": "user",
            #"content": f"{prompt}\n\nTitle:\n{article['title']}\n\nText:\n{article['text']}"
            "content": full_prompt
        }]
    )

    filepath = dir_name + "/" + prompt_name + ".json"
    with open(filepath, "w+") as f:
        f.write(f"{full_prompt}\n\n\n{completion.choices[0].message.content}")

except Exception as e:
    print(e)