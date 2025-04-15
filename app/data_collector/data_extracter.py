# TODO: Add Force Stop (cancel_futures on threadpool)

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
import multiprocessing as mp
import os
from pathlib import Path
import pickle
import queue
import sys
import threading
import time

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
dir_path = PROJ_ROOT / "app/data_collector"
util_path = PROJ_ROOT / "app/util"
sys.path.insert(1, str(dir_path))
sys.path.insert(1, str(util_path))

from ContinuousExecutor import ContinuousExecutor
from text_processor import TextProcessor
# TODO: Database injector

logger = logging.getLogger(__name__)

class DataExtracter(mp.Process):
    def __init__(self, cmd_queue, link_queue, failed_links=None, max_threads=10):
        super().__init__()
        self.cmd_queue = cmd_queue
        self.link_queue = link_queue
        self.res_queue = queue.Queue()
        self.cmds = [
            "SHUTDOWN"
            #"SUBMIT_ARTICLE"
        ]
        self.run_flag = True
        self.max_threads = max_threads
        self.text_processor = TextProcessor(save_json=True)
        self.links_file = PROJ_ROOT / "data/links.pkl"
        self.link_bank = set()
        self.link_recv = set() # use for error logging
        self.link_read = set() # use for error logging
        self.failed_links = failed_links
        self.data_grab_flag = True
        self.link_run_flag = True
        

    def run(self):
        logger.info("Started Run")
        self.link_bank = self.load_links()

        # NOTE: If I set up ContinuousExecutor in __init__, looks like it belongs to pol_app proc (constructed up there)?
        self.thread_pool = ContinuousExecutor(
            max_workers=self.max_threads,
            poll_interval=10
        )
        self.proc_link = threading.Thread(target=self.link_handler)
        self.proc_data = threading.Thread(target=self.data_handler)
        self.proc_link.start()
        self.proc_data.start()

        while self.run_flag:
            cmd, arg = self.cmd_queue.get()
            logger.info(f"cmd_queue - {cmd}")

            if cmd == "SHUTDOWN":
                if arg == "GRACE":
                    self.shutdown_graceful()

        if self.failed_links:
            for link in self.link_recv.difference(self.link_read):
                self.failed_links.put(link)
        logger.info(f"Shutdown Run - {len(self.link_recv) - len(self.link_read)} processing errors occured.")
        return
    

    def link_handler(self):
        logger.debug("Starting Link Handler")
        while self.link_run_flag:
            try:
                link = self.link_queue.get(block=True, timeout=5)

                if link['link'] not in self.link_bank:
                    logger.debug(f"Adding link to threadpool - {link['link']}")
                    self.thread_pool.submit(self.text_processor.proc, link)
                    self.link_recv.add(link['link'])
            except queue.Empty:
                time.sleep(1)
        logger.debug("Shutdown Link Handler")


    def data_handler(self):
        logger.debug("Starting Data Handler")

        while self.data_grab_flag:
            time.sleep(10)
            while self.thread_pool.has_result():
                att_res = self.thread_pool.get_result()
                try:
                    res, data = att_res
                    if res:
                        logger.debug(f"Got data for link - {data['link']}")
                        self.link_read.add(data['link'])
                    else:
                        logger.info(f"Error processing link: {data['link']}")
                except:
                    logger.warning(f"Thread error?  - {att_res}")
                
        # Save links back to file
        self.save_links(self.link_bank | self.link_read)
        logger.debug("Shutdown Data Handler")
        return


    def load_links(self):
        try:
            with open(self.links_file, "rb") as f:
                links = pickle.load(f)
                return links
        except Exception as e:
            logger.warning(f"{e} - Empty Links File? returing empty set")
            return set()
        

    def save_links(self, links):
        with open(self.links_file, "wb+") as f:
           pickle.dump(links, f)
        return
    

    def get_cmd_list(self):
        return self.cmds
    

    def get_max_threads(self):
        return self.max_threads
    

    def shutdown_graceful(self):
        logger.info("Graceful Shutdown triggered...")
        logger.info("Waiting on link handler to terminate...")
        self.link_run_flag = False
        self.proc_link.join()

        # Let current jobs finish
        logger.info("Waiting on ThreadPool jobs to complete...")
        while self.thread_pool.has_jobs():
            time.sleep(5)

        # Let data_handler finish grabbing results
        logger.info("Waiting on data_handler to grab all results...")
        while self.thread_pool.has_result():
            time.sleep(5)

        logger.info("Waiting on data handler to terminate...")
        self.data_grab_flag = False
        self.proc_data.join()
        
        logger.info("Waiting on ThreadPool to terminate...")
        self.thread_pool.shutdown(wait=True, cancel_futures=False)
        
        self.run_flag = False
        return
