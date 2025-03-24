# NOTE: For first iteration, RssRetriever send flag when all rss articles
#       to send "None" to processor to close it when processing is done

# TODO: Modify for continuous run, accept commands from top level controller
# TODO: move logger init logic to top level program in next phase

# ADD data grab dir to path
import sys
import os
from pathlib import Path

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
dir_path = PROJ_ROOT / "/app/data_collector"
sys.path.insert(1, str(dir_path))

import multiprocessing as mp
from text_retrievers.rss_retriever import RssRetriever
from text_processor import TextProcessor
import time

import logging

from datetime import datetime
log_file = PROJ_ROOT / f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_file = os.path.expanduser(log_file)
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

class DataGrabController:
    def __init__(self):
        pass

    
    def main_proc(self, cmd_queue):
        pass


    def main_proc_selfrun(self):
        manager = mp.Manager()
        shared_queue = manager.Queue()

        text_processor = TextProcessor(shared_queue)
        rss_retriever = RssRetriever(shared_queue)

        # TODO: General proc startup
        logger.info("Initializing Procs")
        data_processor_proc = mp.Process(target=text_processor.proc)
        data_grabber_proc = mp.Process(target=rss_retriever.proc)

        logger.info("Starting Data Processor")
        data_processor_proc.start()
        time.sleep(1)
        logger.info("Starting Data Grabber")
        data_grabber_proc.start()

        # Block until all article shoved into queue
        logger.info("Waiting on Data Grabber to end...")
        data_grabber_proc.join()
        logger.info("Data Grabber Ended")

        # Send end flag to processor to terminate after queue processed
        logger.info("Waiting on Data Processor to end...")
        shared_queue.put(None)
        data_processor_proc.join()
        logger.info("Data Processor ended")

        logger.info("All RSS articles processed, terminating...")
        return


if __name__ == "__main__":
    contr = DataGrabController()
    contr.main_proc_selfrun()
