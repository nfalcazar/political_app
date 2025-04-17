'''
First draft of top level control program, will most likely split control logic into specialized 
directories.
'''
from datetime import datetime
import logging
import multiprocessing as mp
import os
from pathlib import Path
import time

import pickle

from data_collector.data_extracter import DataExtracter
from text_collector.text_retrievers.fox_rss_retriever import FoxRssRetriever

from text_collector.text_retrievers.fox_article_retriever import FoxArticleRetriever


PROJ_ROOT = Path(os.environ["PROJ_ROOT"])

log_file = PROJ_ROOT / f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='[%(levelname)-7s] %(module)-20s: %(message)s'
    #format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Top Level Process")
    manager = mp.Manager()
    cmd_queue = manager.Queue()
    link_queue = manager.Queue()
    failed_links = manager.Queue()

    logger.info("Starting DataExtracter")
    extracter = DataExtracter(cmd_queue, link_queue, failed_links=failed_links, max_threads=25)
    extracter.start()

    logger.info("Starting Fox Rss Retriever")
    fox_retrieve = FoxRssRetriever(link_queue)
    fox_retrieve.proc()
    time.sleep(30)

    # # Process old data
    # fox_article_ret = FoxArticleRetriever(save_errors=True)
    # with open(PROJ_ROOT / "data/old_data/links.pkl", "rb") as f:
    #     links = pickle.load(f)
    # for link in links:
    #     res, link_data = fox_article_ret.grabText(link)
    #     if res:
    #         link_queue.put(link_data)
    #     else:
    #         failed_links.put(link_data)

    logger.info("Sending cmd - shutdown to DataExtracter")
    cmd = ("SHUTDOWN", "GRACE")
    cmd_queue.put(cmd)
    
    extracter.join()
    while not failed_links.empty():
        link = failed_links.get()
        logger.info(f"Failed to get data for link - {link}")

    logger.info("Shut down Top Level Process")
    return


if __name__ == "__main__":
    main()