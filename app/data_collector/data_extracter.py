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

if __name__ != "__main__":
    logger = logging.getLogger(__name__)

class DataExtracter(mp.Process):
    def __init__(self, cmd_queue, link_queue, max_threads=10):
        super().__init__()
        self.cmd_queue = cmd_queue
        self.link_queue = link_queue
        self.shared_queue = None
        self.cmds = [
            "SHUTDOWN",
        ]
        self.run_flag = True
        self.t_pool_quit = False
        #self.running_grab_procs = []
        self.max_threads = max_threads
        self.thread_pool = ContinuousExecutor(max_workers=self.max_threads)
        self.text_processor = TextProcessor(save_json=True)
        self.curr_links = self.load_links()
        self.links_file = PROJ_ROOT / "data" / "links.pkl"

    
    def run(self):
        logger.info("Started Run")
        proc_link = threading.Thread(target=self.link_handler)
        proc_data = threading.Thread(target=self.data_handler)
        proc_link.start()
        proc_data.start()

        while self.run_flag:
            cmd = self.cmd_queue.get()
            logger.info(f"cmd_queue - {cmd}")

            if cmd == "SHUTDOWN":
                self.run_flag = False

        logger.info("Shutdown triggered, waiting on link handler...")
        proc_link.join()
        logger.info("Shutdown triggered, waiting on ThreadPool...")
        self.thread_pool.shutdown(wait=True, cancel_futures=False)
        self.t_pool_quit = True
        logger.info("Shutdown triggered, waiting on data handler...")
        proc_data.join()
        
        logger.info("Shutdown Run")
        return
    

    def link_handler(self):
        logger.debug("Starting Link Handler")
        while self.run_flag:
            try:
                link = self.link_queue.get(block=True, timeout=5)

                if link['link'] not in self.curr_links:
                    logger.info(f"Adding link to threadpool: {link['link']}")
                    self.thread_pool.submit(self.text_processor.proc, link)
                    self.curr_links.add(link['link'])
            except queue.Empty:
                time.sleep(1)
        logger.debug("Shutdown Link Handler")


    def data_handler(self):
        logger.debug("Starting Data Handler")
        while not self.t_pool_quit:
            if self.thread_pool.has_result():
                result = self.thread_pool.get_result()
                if not result:
                    logger.info(f"Error processing link: {result['link']}")
                    self.curr_links.remove(result["link"])
                # else:
                #     logger.info(f"Link processed: {result['link']}")

                # TODO: Add data to DB
            else:
                time.sleep(1)

        # Save links back to file
        self.save_links(self.curr_links)
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


# if __name__ == "__main__":
#     log_file = PROJ_ROOT / f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
#     logging.basicConfig(
#         filename=log_file,
#         level=logging.INFO,
#         format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
#     )
#     logger = logging.getLogger(__name__)

#     contr = DataExtracter(None, None)
#     contr.selfrun_rss_grab()
