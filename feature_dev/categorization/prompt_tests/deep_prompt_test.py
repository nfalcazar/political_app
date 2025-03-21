from openai import OpenAI
import sys
import json
import os

sys.path.insert(1, "/home/nalc/Keyring")
from pol_app_deepseek import deepseek_key

# Grab text of RSS articles
edu_file = "../../text_scraper/Fox_RSS_Scrap_Test/outputs/link_3.json"
with open(edu_file, "r") as f:
    article = json.load(f)

# Grab Prompt
#prompt_name = "gpt4.5_gen_v1"
#prompt_name = "gpt4.5_gen_v1_w_ids"
prompt_name = "gpt4.5_goal_claim_split"
with open(f"./prompts/{prompt_name}.txt", "r") as f:
    prompt = f.read()

# deepseek rotation
client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
dir_name = "./outputs"

try:
    completion = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[{
            "role": "user",
            "content": f"{prompt}\n\nText:\n{article['text']}"
        }]
    )

    filepath = dir_name + "/" + prompt_name + ".json"
    with open(filepath, "w+") as f:
        f.write(completion.choices[0].message.content)

except Exception as e:
    print(e)