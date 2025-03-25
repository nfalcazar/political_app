from datetime import datetime
import logging
import multiprocessing as mp
import os
from pathlib import Path
import sys
import threading
import time

PROJ_ROOT = Path(os.environ["PROJ_ROOT"])
dir_path = PROJ_ROOT / "app/data_collector"
sys.path.insert(1, str(dir_path))

from text_retrievers.rss_retriever import RssRetriever
from text_processor import TextProcessor

if __name__ != "__main__":
    logger = logging.getLogger(__name__)

class DataGrabController:
    def __init__(self, cmd_queue, out_queue):
        self.cmd_queue = cmd_queue
        self.out_queue = out_queue
        self.shared_queue = None
        self.cmds = [
            #"START_DATAGRAB",      #Assume start when called, module will quit when no use
            "STOP_DATAGRAB",
            "GRAB_RSS"
        ]
        self.run_flag = True
        self.running_grab_procs = []
        self.proc_text_processor = None
        self.proc_cmd = None

    
    def cmd_processor(self):
        logger.info("Started CMD processor")
        while self.run_flag:
            cmd = self.cmd_queue.get()
            logger.info(f"cmd_queue - {cmd}")

            if cmd == "STOP_DATAGRAB":
                logger.info("See cmd - STOP_DATAGRAB")
                self.run_flag = False
            elif cmd == "GRAB_RSS":
                logger.info("See cmd - GRAB_RSS")
                grab_class = RssRetriever(self.shared_queue)
                proc_grab = mp.Process(target = grab_class.proc)
                self.running_grab_procs.append(proc_grab)
                proc_grab.start()

        return
    

    def main_proc(self):
        logger.info("Starting main_proc()")

        manager = mp.Manager()
        self.shared_queue = manager.Queue()

        logger.debug("Starting self CMD processor")
        self.proc_cmd = threading.Thread(target=self.cmd_processor)
        self.proc_cmd.start()

        logger.debug("Starting TextProcessor")
        text_processor = TextProcessor(self.shared_queue, self.out_queue)
        self.proc_text_processor = mp.Process(target = text_processor.proc)
        self.proc_text_processor.start()

        while self.run_flag is True:
            # Clean up finished text grabbers
            for i in range(0, len(self.running_grab_procs), -1):
                proc = self.running_grab_procs[i]
                if not proc.is_alive():
                    proc.join()
                    del self.running_grab_procs[i]

            time.sleep(1)

        # Shutdown
        logger.info("Caught run flag trigger, cleaning processes and shutting down...")
        self.shared_queue.put(None)
        for proc in self.running_grab_procs:
            proc.join()
        self.proc_text_processor.join()
        self.proc_cmd.join()

        logger.info("Shutdown main_proc()")
        return


    def selfrun_rss_grab(self):
        manager = mp.Manager()
        shared_queue = manager.Queue()

        text_processor = TextProcessor(shared_queue, None)
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
    

    def cmd_list(self):
        return self.cmds


if __name__ == "__main__":
    log_file = PROJ_ROOT / f"logs/{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    logger = logging.getLogger(__name__)

    contr = DataGrabController(None, None)
    contr.selfrun_rss_grab()
