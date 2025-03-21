from openai import OpenAI
import sys
import json
import os

sys.path.insert(1, "/home/nalc/Keyring")
from pol_app_openai import openai_key
from pol_app_deepseek import deepseek_key

prompt = "You are an expert journalist with a lot of years in the craft and also experiencing how history unfolds. \
You are able to find all the statements and claims made in media, relate them to who or what they originated from as well as categorize them. You are able to relate these claims to issues that are either grand in scale like speech, healthcare, and immigration, or small like the environmental quality of a small town. \
You are able to list any source, event, name, or any other hard fact and relate them to the claims. \
I want you to analyze this article and report your results in a json structure that can be read by a program. No additional conversational text is injected."


# openai_client = OpenAI(api_key=openai_key)
# deepseek_client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")

openai_models = [
    "o3-mini",
    "gpt-4o-mini",
    "gpt-4o",
    "o1"
]

# openai_expensive_models = [
#     "o1-pro",
#     "gpt-4.5-preview"
# ]

deepseek_models = [
    "deepseek-reasoner",
    "deepseek-chat"
]

# Grab text of RSS articles
articles = []
dir_path = "../text_scraper/Fox_RSS_Scrap_Test/outputs"
for filename in os.listdir(dir_path):
    if filename.endswith('.json'):
        with open(dir_path + '/' + filename) as f:
            #articles.append(json.load(f))
            article = json.load(f)
            article["filename"] = os.path.splitext(filename)[0]
            articles.append(article)


# OpenAI rotation
print("######\tOPEN AI MODELS\t######\n")
client = OpenAI(api_key=openai_key)
error_sent = False
error = ""
for article in articles:
    dir_name = "./stress_results/" + article["filename"]
    print(f"{article['filename']}\n")

    for model in openai_models:
        print(f"\t{model}...")
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": f"{prompt}\n\nText:\n{article['text']}"
                }]
            )
        
            filepath = dir_name + "/" + model + ".json"
            directory = os.path.dirname(filepath)
            if not os.path.exists(directory):
                os.makedirs(directory)
            
            with open(filepath, "w+") as f:
                f.write(completion.choices[0].message.content)
        except Exception as e:
            error_sent = True
            print(e)
            break

    print("\n\n")
    if error_sent:
        break


# deepseek rotation
print("######\tDEEPSEEK MODELS\t######\n")
client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
error_sent = False
error = ""
for article in articles:
    dir_name = "./stress_results/" + article["filename"]
    print(f"{article['filename']}\n")

    for model in deepseek_models:
        print(f"\t{model}...")
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": f"{prompt}\n\nText:\n{article['text']}"
                }]
            )
        
            filepath = dir_name + "/" + model + ".json"
            directory = os.path.dirname(filepath)
            if not os.path.exists(directory):
                os.makedirs(directory)
            
            with open(filepath, "w+") as f:
                f.write(completion.choices[0].message.content)
        except Exception as e:
            error_sent = True
            print(e)
            break

    print("\n\n")
    if error_sent:
        break
        
print("FINISHED TEST!!!")        

# with open("../text_scraper/Fox_RSS_Scrap_Test/outputs/link_0.json", "r") as f:
#     article = json.load(f)

# print(f"{article['title']}\n\n")
# print(f"{article['link']}\n\n")
# print(f"{article['summary']}\n\n")
# print(f"{article['text']}\n\n")

# completion = client.chat.completions.create(

#     #model="o3-mini",
#     #model=""
#     #model="deepseek-reasoner",
#     model="gpt-4o-mini",
#     messages=[{
#         "role": "user",
#         "content": f"{prompt}\n\nText:\n{article['text']}"
#     }]
# )

# with open("./outputs/source1_results.txt", "w+") as f:
#     print(completion.choices[0].message.content)
#     f.write(completion.choices[0].message.content)
