'''
First draft of top level control program, will most likely split control logic into specialized 
directories.
'''

# TODO: Change failed_links to MP.List/Set?

'''
TODO: Focus on claims to sources for MVP

Only extract from text:
    - Claims that reference some verifiable source (study, gov data, court decisions, etc...)
    - Either the link or a description of the source being referenced
    - An attempt to form canonicalized claims that reference each claim
** Make new prompt, break up system and user prompts

Make two vector searchable tables:
    - Canon Claims
    - Facts ( to allow for counter linking, etc...)

Make an edge table
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

from text_processor import TextProcessor
from routines.grab_rss_feeds import RssGrabber

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
    "grab_rss_feeds"
]
for module in module_list:
    logging.getLogger(module).setLevel(logging.INFO)    
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting Top Level Process")
    link_queue = mp.Queue()
    failed_links = mp.Queue()

    logger.info("Starting TextProcessor")
    text_extract = TextProcessor(link_queue, failed_links)
    text_extract.start()

    logger.info("Starting Fox Rss Retriever")
    res = RssGrabber.grab(out_queue=link_queue)

    time.sleep(10)
    logger.info("Sending Shutdown sentinel - None")
    link_queue.put(None)
    text_extract.join()

    while not failed_links.empty():
        link = failed_links.get()
        logger.info(f"Failed to get data for link - {link}")

    logger.info("Shut down Top Level Process")
    return


if __name__ == "__main__":
    main()