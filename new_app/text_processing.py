import asyncio
from datetime import datetime
from dotenv import load_dotenv
import json
import logging
import multiprocessing as mp
import os
from pathlib import Path
import pickle
import re
import uuid
import queue

from typing import Optional
import time
import threading

import util.ai_ext_calls as ai

#TODO: Move link bank into Database?
#TODO: Move data handling logic into process_link funct

# In case WSL acts like windows and doesn't inherit environments
load_dotenv(dotenv_path='./.env')

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
logger = logging.getLogger(__name__)

class TextProcessing(mp.Process):
    def __init__(self, 
        #async_queue,
        input_queue,
        failed_links = None,
        max_workers: int=10
    ):
        super().__init__()
        #self.async_queue = async_queue
        self.input_queue = input_queue
        self.failed_links = failed_links
        self.max_workers = max_workers
        self.links_file = PROJ_ROOT / "data/links.pkl"
        self.async_queue = asyncio.Queue()
        #if self.async_queue is None:
        if self.input_queue is None:
            raise ValueError("Missing Queue for Links (async_queue).")
        
        
    
    def run(self):
        logger.info("Started Run")
        self.link_bank = self.load_links()
        self.ai_client = ai.OpenAiAsync()

        with open('./prompt.txt', "r") as f:
            self.sys_prompt = f.read()

        # Set up asyncio eventloop and queue puller
        loop = asyncio.new_event_loop()
        self.event_loop = loop

        def start_async_loop():
            asyncio.set_event_loop(loop)
            #asyncio.run(self.async_main())
            loop.run_until_complete(self.async_main())
        
        threading.Thread(target=start_async_loop, daemon=True).start()

        # Make sure async_main is spinning before grabbing input
        time.sleep(10)
        self.queue_puller()
        
        loop.stop()
        loop.close()
        return
    
    

    def queue_puller(self):
        while True:
            item = self.input_queue.get()
            print(f"{item}\n\n")
            asyncio.run_coroutine_threadsafe(self.async_queue.put(item), self.event_loop)
            if item is None:
                break


    async def async_main(self):
        logger.debug("Started Async Main.")
        tasks = []
        task_limiter = asyncio.Semaphore(self.max_workers)
        sentinel_detected = False

        while True:
            try:
                link = await self.async_queue.get()
                if link is None:
                    break

                if link not in self.link_bank:
                    logger.debug(f"Adding task for link: {link['link']}")
                    task = asyncio.create_task(self.process_link(self.ai_client, link, task_limiter))
                    tasks.append(task)
            except queue.Empty:
                logger.debug("Link Queue empty, waiting 5s for input.")
                await asyncio.sleep(5)
            except Exception:
                await asyncio.sleep(0.5)

        for coro in asyncio.as_completed(tasks):
            result = await coro
            if "error" in result.keys() and self.failed_links:
                self.failed_links.put(result)
            else:
                self.link_bank.add(result['link'])
                await asyncio.to_thread(self.handle_ai_resp,result)
        return


    async def process_link(self, ai_client: ai.OpenAiAsync, link: dict, semaphore: asyncio.Semaphore) -> dict:
        async with semaphore:
            logger.info(f"Started Worker for - {link['link']}")
            prompt = f'{self.sys_prompt}\n\n{link["text"]}'
            try:
                #result = await ai_client.query(prompt, "deepseek-reasoner")
                result = await ai_client.query(prompt, "deepseek-reasoner")

                # Clean up potential JSON wrappings
                result = re.sub(r'^```json\s*|```$', '', str(result))
                result_json = {
                    "link": link["link"],
                    "title": link["title"],
                    "response": result
                }
                return result_json
            except Exception as e:
                return {'link': link["link"], "error": str(e)}


    def load_links(self):
        try:
            with open(self.links_file, "rb") as f:
                links = pickle.load(f)
                return links
        except Exception as e:
            logger.warning(f"{e} - Empty Links File? returing empty set")
            return set()
        
    
    def handle_ai_resp(self, result: dict):
        # Form data json
        claims_json = json.loads(result["response"])
        fname = datetime.now().strftime("%Y%m%d_%H%M") + f"__{uuid.uuid4().hex}.json"

        data_json = {
            "filename": fname,
            "title": result["title"],
            "link": result["link"]
        }
        data_json.update(claims_json)

        # save to file
        fpath = PROJ_ROOT / f"data/{fname}"
        with open(fpath, "w+") as f:
            json.dump(data_json, f, indent=2)

        # Push to DB handler
        #TODO: