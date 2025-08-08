'''
First draft of top level control program, will most likely split control logic into specialized 
directories.
'''

# TODO: Change failed_links to MP.List/Set?

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
from text_collector.text_retrievers.fox_rss_retriever import FoxRssRetriever

from text_extractor import TextExtractor


load_dotenv(dotenv_path="./.env")
PROJ_ROOT = Path(os.environ["PROJ_ROOT"])

log_file = PROJ_ROOT / f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    filename=log_file,
    level=logging.WARNING,
    format='%(asctime)s.%(msecs)03d [%(levelname)-7s] %(module)-20s: %(message)s',
    datefmt='%H:%M:%S'
    #format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
module_list = [
    #"pol_app",
    "__main__",
    "text_processor",
    "text_extractor",
    "fox_rss_retriever"
]
for module in module_list:
    logging.getLogger(module).setLevel(logging.INFO)    
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting Top Level Process")
    link_queue = mp.Queue()
    failed_links = mp.Queue()

    # logger.info("Starting TextProcessor")
    # text_proc = TextProcessor(input_queue=link_queue, failed_links=failed_links, max_threads=15)
    # text_proc.start()

    logger.info("Starting Fox Rss Retriever")
    fox_retrieve = FoxRssRetriever(link_queue)
    fox_retrieve.proc()

    logger.info("Starting TextExtractor")
    tmp_queue_in = mp.Queue()
    tmp_queue_out = mp.Queue()
    text_extract = TextExtractor(tmp_queue_in, tmp_queue_out)
    text_extract.start()
    time.sleep(15)

    res_list = []
    while not link_queue.empty():
        entry = link_queue.get()
        res_list.append(entry)

    #NOTE: Hangs with full ~25 articles? Maybe just deepseek issue
    urls = [entry['link'] for entry in res_list[:5]]
    test_input = {
        "source_type": "news_article",
        "urls": urls
    }
    tmp_queue_in.put(test_input)
    time.sleep(10)
    logger.info("Sending Shutdown sentinel - None")
    #link_queue.put(None)
    #text_proc.join()
    tmp_queue_in.put(None)
    text_extract.join()

    while not tmp_queue_out.empty():
        result = tmp_queue_out.get()
        print(json.dumps(result, indent=2))

    while not failed_links.empty():
        link = failed_links.get()
        logger.info(f"Failed to get data for link - {link}")

    logger.info("Shut down Top Level Process")
    return


if __name__ == "__main__":
    main()