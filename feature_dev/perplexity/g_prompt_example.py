import requests
import os
import sys
from pathlib import Path
import json
from openai import OpenAI

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
KEYRING = os.environ["KEYRING"]
sys.path.insert(1, KEYRING)
from pol_app_goog_cust_search import g_search_api_key
from pol_app_goog_cust_search import g_search_eng_id
from pol_app_openai import openai_key

#NOTE:  Needed rule in prompt to stop queries from having "" (exact quote searches)

claim = "the U.S. Supreme Court issued a ruling early Saturday morning blocking deportations of Venezuelans held in northern Texas under an 18th-century wartime law"
API_KEY = g_search_api_key
SEARCH_ENGINE_ID = g_search_eng_id
url = "https://www.googleapis.com/customsearch/v1"

params = {
    "key": API_KEY,
    "cx": SEARCH_ENGINE_ID,
    "num" : "5"
}

# Get search query from OpenAI
with open('./g_search_prompt.txt', "r") as f:
    prompt = f.read()

with open("./site_rest_prompt.txt", "r") as f:
    prompt = prompt + f.read()

prompt = prompt + f"\n\nClaim:\n{claim}"

client = OpenAI(api_key=openai_key)
try:
    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        #model="gpt-4o",             
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    result = completion.choices[0].message.content
    result = result.replace("json", '')
    result = result.replace("```", '')
    #print(result)
    result = json.loads(result)
except:
    raise


# Get search results from google
params.update(result)

# 📡 Make the request
response = requests.get(url, params=params)
response.raise_for_status()

# write full result to file
with open("./outputs/g_prompt_ex.txt", "w+") as f:
    f.write(f"Query prompt:\n{prompt}\n\n")
    f.write(f"Query resp:\n")
    json.dump(result, f, indent=2)

    f.write(f"\n\nSearch results:\n")
    results = response.json()
    for item in results.get("items", []):
        f.write(f"Title: {item['title']}\n")
        f.write(f"Link: {item['link']}\n\n")

    f.write(f"\n\nRaw resp json:\n")
    json.dump(results, f, indent=2)

"""
    params = {
        "q" : q["q"],
        "orTerms" : gpt_res["orTerms"],
        "fileType": "pdf",
        "num": "5",
        "key": API_KEY,
        "cx": SEARCH_ENGINE_ID
    }

    # 📡 Make the request
    response = requests.get(url, params=params)
    response.raise_for_status()

    # 📦 Parse and display results
    results = response.json()

    #with open("./outputs/gpt_g_search_res.json", "a+") as f:
    with open("./outputs/deep_g_search_res.json", "a+") as f:
        json.dump(results, f, indent=2)

    print(f"{prompt}\n\n{result}")
"""