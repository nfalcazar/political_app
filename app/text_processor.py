from datetime import datetime
from dotenv import load_dotenv
import json
import logging
import multiprocessing as mp
import os
from pathlib import Path
import pickle
import re
import time
import uuid

from util.ai_ext_calls import OpenAiSync
from util.ContinuousExecutor import ContinuousExecutor

logger = logging.getLogger(__name__)
#logging.getLogger("httpx").setLevel(logging.ERROR)

#NOTE I don't think I need to worry about adding to link_bank not being thread safe
#       - Only issue I currently see is if repeat link is seen while being processed

#NOTE Since processing logic all handled in worker func, don't need to grab results from threadpool

#NOTE Moved loadenv to after super init just in case a new proc doesn't inherit env

#TODO: OpenAI fallback on link fail (in case of Chinese censor)
#   - Make the two clients (one for deep, one for openai) as class vars
#   - Check if link passes in a client override (similar to how I'm checking for prompt override)
#   - Add model override aswell

class TextProcessor(mp.Process):
    def __init__(self, input_queue, failed_links, max_threads=10):
        super().__init__()
        load_dotenv(dotenv_path="./.env")
        self.PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
        self.input_queue = input_queue
        self.failed_links = failed_links
        self.links_file = self.PROJ_ROOT / "data/links.pkl"
        self.max_threads = max_threads
        with open(self.PROJ_ROOT / f'app/prompts/text_extract_sys.txt', "r") as f:
            self.default_sys_prompt = f.read()
        

    
    def run(self):
        logger.debug("Started Run")
        ai_client = OpenAiSync()
        self.link_bank = self.load_links()
        thread_pool = ContinuousExecutor(
            max_workers=self.max_threads,
            poll_interval=10
        )

        # Main Loop
        while True:
            link = self.input_queue.get()
            if link is None:
                logger.info("Detected None sentinel, stopping...")
                break
            else:
                if link['link'] not in self.link_bank or link.get("forced_rerun", False):
                    thread_pool.submit(self.process_link, ai_client, link)

        # Wait for current links to be processed
        while thread_pool.has_jobs():
            time.sleep(5)
        thread_pool.shutdown(wait=True, cancel_futures=False)

        # Update links file
        with open(self.links_file, "wb+") as f:
           pickle.dump(self.link_bank, f)
        return


    def process_link(self, client, link):
        logger.info(f"Sending to AI: {link['link']}")

        if "sys_prompt" not in link.keys():
            sys_prompt = self.default_sys_prompt
        else:
            sys_prompt = link["sys_prompt"]

        try:
            resp = client.query(
                user_prompt = link['text'],
                sys_prompt = sys_prompt
            )

            # Get resp json from str
            result_str = re.sub(r'^```json\s*|```$', '', str(resp))
            result_json = json.loads(result_str)

        except Exception as e:
            return {'link': link["link"], "error": str(e)}
        
        # Store in file
        # TODO: Send to DB processing
        if result_json.get("sources", False):
            fname = datetime.now().strftime("%Y%m%d_%H%M") + f"__{uuid.uuid4().hex}.json"
            data_json = {
                "filename": fname,
                "title": link['title'],
                "link": link['link'],
            }
            data_json.update(result_json)
            fpath = self.PROJ_ROOT / f"data/{fname}"
            with open(fpath, "w+") as f:
                json.dump(data_json, f, indent=2)
                
        self.link_bank.add(link['link'])
        return


    def load_links(self):
        try:
            with open(self.links_file, "rb") as f:
                links = pickle.load(f)
                return links
        except Exception as e:
            logger.warning(f"{e} - Empty Links File? returing empty set")
            return set()
