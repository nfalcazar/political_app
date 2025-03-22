# TODO: Determine if better to pass prompt in init or proc
#       Current thinking is: if I want multiple text processors, I'll probably spin them up with
#       unique purpose, so maybe better to put in init for now

# TODO: Remove Deepseek hardcode when I move to incorporate more models
# TODO: Proper file path handling when I move to make this app delierable
# TODO: Proper error handling
# TODO: Assuming there will always be delay in processing, using time stamp to allow unique filenames
# TODO: FOR ALL FILES, when proper flow establish, keep track of project root dir, store in env

# TODO: Saw error: Unterminated string starting at: line 489 column 15 (char 15171)
#       Add check after AI grab to see if string is able to convert to json?
#       -   Don't think I'd have programatic way of fixing bad formed JSON outputs
#       -   Current logic ok since link isn't added to processed list, can be hit again

# TODO: Convert stored links into hashes for faster check?

# TODO: Find out why unicodes are still appearing in final output
#       -   Looks like it's quote chars that would mess up JSON struct, don't see way around this
#       -   Need to remember this when I start adding claims to Graph

from openai import OpenAI
from multiprocessing import Queue
import re
import sys
from datetime import datetime
from pathlib import Path
import json
import html

sys.path.insert(1, "/home/nalc/Keyring")
from pol_app_deepseek import deepseek_key

class TextProcessor:
    def __init__(self, in_queue, prompt=None):
        self.in_queue = in_queue
        self.data_dir = Path("~/political_app/data/").expanduser()
        self.links_file = self.data_dir / "links.json"
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
            print(f"{e} - Empty Links File? returing empty set")        #TODO: add to logging when imp
            return []
        

    def save_links(self, link_json):
        with open(self.links_file, "w") as f:
           json.dump(link_json, f, indent=2)
        return
        

    def proc(self):
        # Grab set of already processed links
        links_json = self.load_links()
        if links_json:
            links = links_json["links"]
        else:
            links = links_json      # should be empty set

        while True:
            media_data = self.in_queue.get()
            if media_data is None:
                break

            # Check if media was already processed
            if media_data["link"] in links:
                continue

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

                # form result json
                result_json = json.loads(cleaned_text)
                result_json["title"] = media_data["title"]
                result_json["link"] = media_data["link"]
                result_json["summary"] = media_data["summary"]

                time_str = datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
                filepath = self.data_dir / time_str
                
                with open(filepath, "w+") as f:
                    json.dump(result_json, f, indent=2)

                # Store seen link after all processing done
                links.append(media_data["link"])
            except Exception as e:
                print(e)

        new_links_json = {}
        new_links_json["links"] = links
        self.save_links(new_links_json)
        return

