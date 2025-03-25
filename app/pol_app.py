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

from data_collector.data_grab_controller import DataGrabController

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
    data_queue = manager.Queue()
    cmd_queue = manager.Queue()

    logger.info("Starting DataGrabController")
    data_grabber = DataGrabController(cmd_queue, data_queue)
    proc_data_grabber = mp.Process(target=data_grabber.main_proc)
    proc_data_grabber.start()

    logger.info("Sending cmd - GRAB_RSS to DataGrabController")
    cmd_queue.put("GRAB_RSS")

    time.sleep(15)

    logger.info("Sending cmd - STOP_DATAGRAB to DataGrabController")
    cmd_queue.put("STOP_DATAGRAB")
    
    proc_data_grabber.join()
    logger.info("Shut down Top Level Process")
    return


if __name__ == "__main__":
    main()