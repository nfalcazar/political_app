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
#       -   GPT reccomends trying Pickle first

# TODO: Find out why unicodes are still appearing in final output
#       -   Looks like it's quote chars that would mess up JSON struct, don't see way around this
#       -   Need to remember this when I start adding claims to Graph

# TODO: Save bad AI output for error analysis

# TODO: Should I move queue json structure into own class each file can refernce?

from openai import OpenAI
from multiprocessing import Queue
import re
import sys
from datetime import datetime
from pathlib import Path
import json
import pickle
import logging
import os
from pathlib import Path

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
KEYRING = os.environ["KEYRING"]

sys.path.insert(1, KEYRING)
from pol_app_deepseek import deepseek_key

logger = logging.getLogger(__name__)

class TextProcessor:
    def __init__(self, in_queue, prompt=None):
        self.error_count = 0
        self.in_queue = in_queue
        self.data_dir = PROJ_ROOT / "data"
        self.links_file = self.data_dir / "links.pkl"
        self.client = OpenAI(api_key=deepseek_key, base_url="https://api.deepseek.com")
        self.prompt_fname = PROJ_ROOT / "app/data_collector/prompt.txt"
        
        # load prompt from file if None passed in
        if not prompt:
            with open(self.prompt_fname, "r") as f:
                self.prompt = f.read()
        else:
            self.prompt = prompt
        return


    def load_links(self):
        try:
            with open(self.links_file, "rb") as f:
                links = pickle.load(f)
                return links
        except Exception as e:
            logger.warning(f"{e} - Empty Links File? returing empty set")        #TODO: add to logging when imp
            return set()
        

    def save_links(self, links):
        with open(self.links_file, "wb+") as f:
           pickle.dump(links, f)
        return
    

    def save_error(self, bad_output):
        err_path = self.data_dir / f"processing_errs/err_{self.error_count}.txt"
        err_path.parent.mkdir(parents=True, exist_ok=True)
        with open(err_path, "w+") as f:
            f.write(bad_output)
        return
           

    def proc(self):
        logger.info("Started proc() run")

        # Grab set of already processed links
        links = self.load_links()

        while True:
            media_data = self.in_queue.get()
            if media_data is None:
                break

            logger.debug(f"Got Media - {media_data['title']}")

            # Check if media was already processed
            if media_data["link"] in links:
                # I think using Pickle handles seen links pretty well, don't need to log skips
                #logger.info(f"\t\t- found in processed link store, skipping...")
                continue

            logger.info(f"Processing - {media_data['title']}")
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
                links.add(media_data["link"])
            except json.JSONDecodeError as e:
                self.save_error(cleaned_text)
                logger.warning(f"{e} - Error output saved to data/processing_errs")
            except Exception as e:
                logger.error(f"Exception bucket for OpenAI errors hit - {e}")

        self.save_links(links)
        logger.info("Finished proc() run")
        return

