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
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Top Level Process")
    manager = mp.Manager()
    cmd_queue = manager.Queue()
    link_queue = manager.Queue()

    logger.info("Starting DataExtracter")
    extracter = DataExtracter(cmd_queue, link_queue, max_threads=50)
    extracter.start()

    # logger.info("Starting Fox Rss Retriever")
    # fox_retrieve = FoxRssRetriever(link_queue)
    # fox_retrieve.proc()

    # Process old data
    fox_article_ret = FoxArticleRetriever()
    with open(PROJ_ROOT / "data/old_data/links.pkl", "rb") as f:
        links = pickle.load(f)
    for link in links:
        link_queue.put(fox_article_ret.grabText(link))

    time.sleep(15)

    logger.info("Sending cmd - SHUTDOWN to DataExtracter")
    cmd_queue.put("SHUTDOWN")
    
    extracter.join()
    logger.info("Shut down Top Level Process")
    return


if __name__ == "__main__":
    main()