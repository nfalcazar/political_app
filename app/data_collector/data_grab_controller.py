from datetime import datetime
import logging
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
dir_path = PROJ_ROOT / "app/data_collector"
sys.path.insert(1, str(dir_path))

from text_retrievers.rss_retriever import RssRetriever
from text_processor import TextProcessor

log_file = PROJ_ROOT / f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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


    def rss_grab(self):
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
    contr.rss_grab()
