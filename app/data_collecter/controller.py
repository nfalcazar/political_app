# NOTE: For first iteration, RssRetriever send flag when all rss articles
#       to send "None" to processor to close it when processing is done

# TODO: Modify for continuous run, accept commands from top level controller

import multiprocessing as mp
from text_retrievers.rss_retriever import RssRetriever
from text_processor import TextProcessor
import time

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
        print("Initializing Procs")
        data_processor_proc = mp.Process(target=text_processor.proc)
        data_grabber_proc = mp.Process(target=rss_retriever.proc)

        print("Starting Data Processor")
        data_processor_proc.start()
        time.sleep(1)
        print("Starting Data Grabber")
        data_grabber_proc.start()

        # Block until all article shoved into queue
        print("Waiting on Data Grabber to end...")
        data_grabber_proc.join()
        print("Data Grabber Ended")

        # Send end flag to processor to terminate after queue processed
        print("Waiting on Data Processor to end...")
        shared_queue.put(None)
        data_processor_proc.join()
        print("Data Processor ended")

        print("All RSS articles processed, terminating...")
        return


if __name__ == "__main__":
    contr = DataGrabController()
    contr.main_proc_selfrun()
