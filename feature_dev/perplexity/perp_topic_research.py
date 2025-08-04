import requests
import sys
import os
from pathlib import Path
import json

"""
Seems about 5c per 7 reqs so far, a little pricy :/
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

    sys_prompt = "You are an expert journalist tasked with finding the primary sources to propaganda and narratives and either countering misleading/false statements or highlighting true statements."
    claim = "The rise of illegal immigration into the US has caused increased crime to citizens and thus is a danger that needs to be dealt with."

    full_prompt = f"{sys_prompt}\n\nStatement to counter:\n{claim}"

    try:
        flags = {"web_search_options" : {"search_context_size" : "medium"}}
        resp = sonar.sonar_query(full_prompt, model="sonar-pro", flags=flags)

        with open("./outputs/perp_topic_result_sonarpro_med.txt", "w+") as f:
            f.write(f"Prompt:\n{full_prompt}\n\n")
            f.write("Result:\n")
            json.dump(resp, f, indent=2)
    except:
        raise
