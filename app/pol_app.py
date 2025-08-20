'''
First draft of top level control program, will most likely split control logic into specialized 
directories.
'''

# TODO: Change failed_links to MP.List/Set?

'''
TODO: Focus on claims to sources for MVP
    - Add more RSS feeds (NYT, WSJ, CNN, etc...)
        * Doesn't seem many RSS feeds provide articles, will run into paywalled articles
    - Extract facts from primary, reliable sources
    - Compare similar facts (supports, counters, etc...)
    - Decide: Link facts to canon claims or rely on graph traversal
    - Some logic to do initial searchs of my beliefs

TODO: Start including cost estimates for each step/module
'''

from datetime import datetime
from dotenv import load_dotenv
import logging
import multiprocessing as mp
import os
from pathlib import Path
import time

import pickle
import json

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from text_processor import TextProcessor
from routines.grab_rss_feeds import RssGrabber
from routines.resolve_sources import resolve_unresolved_sources
from database.init_db import DbInit
from data_processor import DataProcessor

#from text_extractor import TextExtractor


load_dotenv(dotenv_path="./.env")
PROJ_ROOT = Path(os.environ["PROJ_ROOT"])

log_file = PROJ_ROOT / f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    filename=log_file,
    level=logging.WARNING,
    format='%(asctime)s.%(msecs)03d [%(levelname)-7s] %(module)-20s: %(message)s',
    datefmt='%H:%M:%S'
)
module_list = [
    "__main__",
    "text_processor",
    "text_extractor",
    "data_processor",
    "routines.resolve_sources"
]
for module in module_list:
    logging.getLogger(module).setLevel(logging.INFO)    
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting Top Level Process")
    db = DbInit()
    db.create_tables()

    text_proc_in_queue = mp.Queue()
    data_proc_in_queue = mp.Queue()
    failed_links = mp.Queue()

    logger.info("Starting DataProcessor")
    data_processor = DataProcessor(data_proc_in_queue)
    data_processor.start()

    logger.info("Starting TextProcessor")
    text_extract = TextProcessor(
        text_proc_in_queue,
        failed_links,
        output_queue=data_proc_in_queue
    )
    text_extract.start()

    # Set up APScheduler for source resolution
    # scheduler = BackgroundScheduler()
    # scheduler.add_job(
    #     func=resolve_unresolved_sources,
    #     trigger=IntervalTrigger(minutes=30),
    #     id='source_resolution_job',
    #     name='Process unresolved sources',
    #     replace_existing=True,
    #     max_instances=1  # Prevent overlapping runs
    # )
    
    # logger.info("Starting Source Resolution Scheduler")
    # scheduler.start()

    logger.info("Starting Rss Retriever")
    res = RssGrabber.grab(out_queue=text_proc_in_queue)

    time.sleep(20)
    logger.info("Sending Shutdown sentinel - None")
    text_proc_in_queue.put(None)
    text_extract.join()
    data_proc_in_queue.put(None)
    data_processor.join()
    
    # logger.info("Stopping Source Resolution Scheduler")
    # scheduler.shutdown()

    logger.info("Starting Source Resolution")
    resolve_unresolved_sources()

    while not failed_links.empty():
        link = failed_links.get()
        logger.info(f"Failed to get data for link - {link}")

    logger.info("Shut down Top Level Process")
    return


if __name__ == "__main__":
    main()