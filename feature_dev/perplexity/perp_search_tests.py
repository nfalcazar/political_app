import requests
import sys
import os
from pathlib import Path
import json

"""
Seems about 5c per 7 reqs so far, a little pricy :/

TODO:
    - Process each source, pairing the source descr with claim linked to source
    - Determine canon claims with most linked claims
    - Prompt Perplexity to research facts about canon claim

    REMOVE
    - I could pull multiple facts per source link, use embed compare to prevent dups
    - fact node:
        claim
        links: [
            {"titile", "url", "date", "last_updated"}
        ]
    - Determine either edge table or related node stored in node
"""

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
KEYRING = os.environ["KEYRING"]
sys.path.insert(1, KEYRING)
from pol_app_perplexity import perplexity_key


class SonarAPI():
    def __init__(self):
        self.api_key = perplexity_key
        self.url = "https://api.perplexity.ai/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {perplexity_key}",  # Replace with your actual API key
            "Content-Type": "application/json"
        }
        self.models = [
            "sonar",
            "sonar-pro",
            "sonar-reasoning",
            "sonar-reasoning-pro"
        ]
        self.handled_flags = [
            "stream",               # True, False
            "search_mode",          # academic
            "web_search_options",   # { dict of web search options }
            "search_domain_filter"  # [ list of domain names ]
        ]


    def sonar_query(self, query : str, flags : dict=dict(), model : str="sonar"):
        if model not in self.models:
            raise ValueError("Bad model passed in.")
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": query}
            ]
        }

        if flags:
            if type(flags) is not dict:
                raise TypeError("flags is not of type dict.")
            
            for flag in flags.keys():
                if self.flag_validate(flag):
                    payload[flag] = flags[flag]
                else:
                    # return list of unhandled flags?
                    err = f"{flag} is not in list of handled flags."
                    raise ValueError(err)

        response = requests.post(self.url, headers=self.headers, json=payload)

        if not response.ok:
            raise RuntimeError(f"Sonar Request failed with code: {response.status_code}")
        else:
            return response.json()



    def flag_validate(self, flag):
        """
        WIP: Could validate args, for now looking for known names
        Compares passed in flag name to list of known flags
        """
        if flag not in self.handled_flags:
            return False
        return True
        


if __name__ == "__main__":
    sonar = SonarAPI()

    # Grab Sources from data
    # Use perplexity to grab primary source
    article_file = "data/20250422_1445__b998f29f04dd496bb4a699286dcd4370.json"
    data_fpath = PROJ_ROOT / article_file
    with open(data_fpath, "r") as f:
        data = json.load(f)

    claims = data["claims"]
    sources = data["sources"]

    tar_claim = claims[0]
    tar_source = sources[0]
    del tar_source["id"]
    del tar_source["reference"]

    sys_prompt = "You are an expert journalist, your job is to find the primary source of a provided claim. You prefer sources from well known research institutes or .gov\n"
    prompt = f"source description:\n{tar_source}\n\n"
    prompt = prompt + f"claim:\n{tar_claim["quote"]}"
    full_prompt = sys_prompt + prompt

    try:
        #flags = {"search_mode" : "academic"}
        flags = {"search_domain_filter" : ["-wikipedia.org", "-cnn.com", "-www.texastribune.org"]}
        resp = sonar.sonar_query(full_prompt, flags=flags)
        #with open("./outputs/source_grab.json", "w+") as f:
        #with open("./outputs/source_grab_academ.json", "w+") as f:
        with open("./outputs/source_grab_domain_filt.json", "w+") as f:
            json.dump(resp, f, indent=2)
    except:
        raise


    # Grab canon claims from data
    # Use perplexity to research claim and return sources (use pro model?)
