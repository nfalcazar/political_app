# TODO: Determine if better to pass prompt in init or proc
#       Current thinking is: if I want multiple text processors, I'll probably spin them up with
#       unique purpose, so maybe better to put in init for now

# TODO: Remove Deepseek hardcode when I move to incorporate more models
# TODO: Proper file path handling when I move to make this app delierable
# TODO: Proper error handling
# TODO: Assuming there will always be delay in processing, using time stamp to allow unique filenames

from openai import OpenAI
from multiprocessing import Queue
import re
import sys
import datetime
from pathlib import Path
import json

sys.path.insert(1, "/home/nalc/Keyring")
from pol_app_deepseek import deepseek_key

class TextProcessor:
    def __init__(self, in_queue, prompt=None):
        self.in_queue = in_queue
        self.data_dir = "~/project_app/data/"
        self.links_file = self.data_dir + "links.json"
        self.client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        
        # load prompt from file if None passed in
        if not prompt:
            with open("prompt.txt", "r") as f:
                self.prompt = f.read()
        else:
            self.prompt = prompt


    def load_links(self):
        # Create file if not exist
        Path(self.links_file).touch(exist_ok=True)

        try:
            with open(self.links_file, "r") as f:
                links = json.load(f)
                return links
        except json.JSONDecodeError as e:
            print(e)        #TODO: add to logging when imp
            return set()
        

    def save_links(self, link_json):
        with open(self.links_file, "w") as f:
           json.dump(link_json, f, indent=2)
        return
        

    def proc(self):
        # Grab set of already processed links
        links_json = self.load_links()
        if links_json:
            links = links_json["links"]

        while True:
            media_data = self.in_queue.get()
            if media_data is None:
                break

            # Check if media was already processed
            if media_data["link"] in links:
                continue

            # TODO: grab AI output, purge json comments it usually has
            try:
                completion = self.client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=[{
                        "role": "user",
                        "content": f"{self.prompt}\n\nText:\n{media_data['text']}"
                    }]
                )
                result_str = completion.choices[0].message.content

                # clean json tags that sometime show up
                cleaned_text = re.sub(r'^```json\s*|```$', '', result_str)

                time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = self.data_dir + "/" + time_str + ".json"
                
                with open(filepath, "w+") as f:
                    json.dump(cleaned_text, f, indent=2)

                # Store seen link after all processing done
                links.add(media_data["link"])
            except Exception as e:
                print(e)

        new_links_json = {}
        new_links_json["links"] = links
        self.save_links(links)

