import requests
import os
import sys
from pathlib import Path
import json

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
KEYRING = os.environ["KEYRING"]
sys.path.insert(1, KEYRING)
from pol_app_goog_cust_search import g_search_api_key
from pol_app_goog_cust_search import g_search_eng_id

# 🔐 Replace these with your actual values
API_KEY = g_search_api_key
SEARCH_ENGINE_ID = g_search_eng_id

# 📄 Targeted claim-based query
#query = 'site:supremecourt.gov inurl:/opinions/ ("Alien Enemies Act" OR Venezuelans OR Texas)'
#query = '"Supreme Court" "blocking deportations" "Venezuelans" "Texas" "18th century wartime law" site:.gov OR site:.us OR site:supremecourt.gov'
#query = '"Supreme Court" OR SCOTUS "blocking deportations" OR "stay of removal" Venezuelans Texas "18th century" OR "Alien Enemy Act" OR "1798"'

# 🌐 API endpoint
url = "https://www.googleapis.com/customsearch/v1"

# ⚙️ Parameters
# params = {
#     "key": API_KEY,
#     "cx": SEARCH_ENGINE_ID,
#     "q": query,
#     "fileType": "pdf",   # prioritize PDFs (optional)
#     "num": 5,            # max results (1–10)
#     #"sort" : "date"
# }

# Deepseek with GPT prompt
# params = {
#     "q": '("Supreme Court" OR SCOTUS) site:supremecourt.gov inurl:/opinions/ OR inurl:/orders/ OR site:.gov',
#     #"q": 'site:supremecourt.gov inurl:/opinions/',
#     "orTerms": 'Venezuelans Texas "block deportations" "stay of removal" "Alien Enemies Act" 1798 "18th century"',
#     "fileType": "pdf",
#     "exactTerms": "Venezuelan Texas",
#     "num": "10",
#     "key": API_KEY,
#     "cx": SEARCH_ENGINE_ID
# }

# ChatGPT w/ multi query (deepseek seems unreliable for this, maybe try after good prompt)
gpt_res = {
  "queries": [
    {
      "q": "Supreme Court ruling blocks deportation Venezuelans site:supremecourt.gov/opinions"
    },
    {
      "q": "SCOTUS decision halts Texas migrant removal site:supremecourt.gov/opinions"
    },
    {
      "q": "Supreme Court wartime law immigration case site:supremecourt.gov/opinions"
    }
  ],
  "orTerms": "\"Alien Enemies Act\" \"Venezuelan migrants\" \"immigration enforcement\" \"emergency ruling\" \"northern Texas\" \"expedited removal\" deportation detention \"wartime authority\" SCOTUS"
}

deep_res = {
    "queries": [
    {
      "q": "U.S. Supreme Court ruling blocking deportations of Venezuelans in Texas under 18th-century wartime law site:supremecourt.gov/opinions"
    },
    {
      "q": "Supreme Court emergency order halting removal of Venezuelan detainees in northern Texas citing 18th-century statute site:justice.gov/oip"
    },
    {
      "q": "SCOTUS decision prevents deportation of Venezuelan migrants in Texas using 1700s wartime legislation site:uscourts.gov"
    }
  ],
  "orTerms": "\"Supreme Court ruling\" \"emergency order\" \"injunction\" \"stay of removal\" \"deportation block\" Venezuelans \"Venezuelan migrants\" \"Venezuelan detainees\" Texas \"northern Texas\" \"18th-century law\" \"wartime statute\" \"Alien Enemies Act\" \"1798 law\" \"emergency powers\" \"immigration enforcement\" \"habeas corpus\" \"detention challenge\""
}

#for q in gpt_res["queries"]:
for q in deep_res["queries"]:
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

    print(f"Query: {q["q"]}")
    for item in results.get("items", []):
        print(f"Title: {item['title']}")
        print(f"Link: {item['link']}")
        print()

    print("\n\n\n")