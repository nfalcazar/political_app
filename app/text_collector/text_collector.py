import logging
import multiprocessing as mp
import time

from text_retrievers.fox_rss_retriever import FoxRssRetriever

if __name__ != "__main__":
    logger = logging.getLogger(__name__)

def selfrun_rss_grab(self):
        manager = mp.Manager()
        shared_queue = manager.Queue()
        rss_retriever = FoxRssRetriever(shared_queue)

        # TODO: General proc startup
        logger.info("Initializing Procs")
        data_grabber_proc = mp.Process(target=rss_retriever.proc)

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
        logger.info("Data Processor ended")

        logger.info("All RSS articles processed, terminating...")
        return