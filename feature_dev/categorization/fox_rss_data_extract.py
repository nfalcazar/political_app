from openai import OpenAI
import sys
import json

sys.path.insert(1, "/home/nalc/Keyring")
from pol_app_openai import openai_key
from pol_app_deepseek import deepseek_key

prompt = "You are an expert journalist with a lot of years in the craft and also experiencing how history unfolds. \
You are able to find all the statements and claims made in media, relate them to who or what they originated from as well as categorize them. You are able to relate these claims to issues that are either grand in scale like speech, healthcare, and immigration, or small like the environmental quality of a small town. \
You are able to list any source, event, name, or any other hard fact and relate them to the claims. \
I want you to analyze this article and report your results in a json structure that can be read by a program. No additional conversational text is injected."
#print(f"Prompt:\n{prompt}\n\n")

client = OpenAI(api_key=openai_key)
#client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")


with open("../text_scraper/Fox_RSS_Scrap_Test/outputs/link_0.json", "r") as f:
    article = json.load(f)

# print(f"{article['title']}\n\n")
# print(f"{article['link']}\n\n")
# print(f"{article['summary']}\n\n")
# print(f"{article['text']}\n\n")

completion = client.chat.completions.create(
    #model="o3-mini",
    #model=""
    #model="deepseek-reasoner",
    model="gpt-4o-mini",
    messages=[{
        "role": "user",
        "content": f"{prompt}\n\nText:\n{article['text']}"
    }]
)

with open("./outputs/source1_results.txt", "w+") as f:
    print(completion.choices[0].message.content)
    f.write(completion.choices[0].message.content)
