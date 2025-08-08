'''
First draft of top level control program, will most likely split control logic into specialized 
directories.
'''

# TODO: Change failed_links to MP.List/Set?
# TODO: Place AI keys / DB urls into env as part of setup

from datetime import datetime
import logging
import multiprocessing as mp
import os
from pathlib import Path
import time
import sys
from dotenv import load_dotenv

import pickle

import queue

from fox_rss_retriever import FoxRssRetriever
from text_processing import TextProcessing

load_dotenv(dotenv_path="./.env")
PROJ_ROOT = Path(os.environ["PROJ_ROOT"])

log_file = PROJ_ROOT / f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG,
    format='[%(levelname)-7s] %(module)-20s: %(message)s'
    #format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Top Level Process")
    link_queue = mp.Queue()
    failed_links = mp.Queue()

    logger.info("Starting TextProcessing")
    extracter = TextProcessing(input_queue=link_queue, failed_links=failed_links, max_workers=15)
    extracter.start()

    logger.info("Starting Fox Rss Retriever")
    fox_retrieve = FoxRssRetriever(link_queue)
    fox_retrieve.start()

    time.sleep(30)
    
    link_queue.put(None)
    extracter.join()
    while not failed_links.empty():
        link = failed_links.get()
        logger.info(f"Failed to get data for link - {link}")

    logger.info("Shut down Top Level Process")
    return


if __name__ == "__main__":
    main()