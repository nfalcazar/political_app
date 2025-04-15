import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import os

logger = logging.getLogger(__name__)

class ContinuousExecutor:
    def __init__(self, max_workers=5, poll_interval=0.1):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        #self.out_queue = out_queue
        self._job_queue = queue.Queue()
        self._results_queue = queue.Queue()
        self._futures = []
        self._futures_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._poll_interval = poll_interval
        self._next_id = 0

        # Start job insterer
        self._insert_thread = threading.Thread(target=self._job_inserter)
        self._insert_thread.start()
        # Start a background thread that checks for completed futures
        self._monitor_thread = threading.Thread(target=self._monitor_futures)
        self._monitor_thread.start()


    def submit(self, func, *args, **kwargs):
        future = self.executor.submit(func, *args, **kwargs)
        logger.info(f"Placing into job queue - {args[0]['link']}")
        job = (self._next_id, future)
        self._job_queue.put(job)
        return
    

    def _job_inserter(self):
        logger.info(f"Starting Job Insert thread")
        while not self._stop_event.is_set():
            try:
                entry = self._job_queue.get(block=True, timeout=self._poll_interval)
                logger.info(f"Inserting entry into futures  PID: {os.getpid()}  self: {id(self)} id: {id(self._futures)}")
                self._futures.append(entry) 
            except queue.Empty:
                continue


    def _monitor_futures(self):
        logger.info("Starting ThreadPool Mon thread")
        while not self._stop_event.is_set():
            with self._futures_lock:
                logger.info(f"Mon Thread see futures? PID: {os.getpid()} self: {id(self)}  id: {id(self._futures)}  state: {bool(self._futures)}")
                pending = list(self._futures)
                for entry in self._futures:
                    id_val, fut = entry
                    logger.debug(f"Future [{id_val}] state: running={fut.running()}, done={fut.done()}")
                    if fut.done():
                        logger.info("Detected completed job...")
                        try:
                            result = fut.result()
                            self._results_queue.put(result)
                            #self.out_queue.put(result)
                            logger.info("Added result to queue")
                        except Exception as ex:
                            logger.warning(f"Thread in ThreadPool error - {ex}")
                            self._results_queue.put(ex)
                            #self.out_queue.put(ex)

                        pending.remove(entry)
                self._futures = pending
            time.sleep(self._poll_interval)


    def get_result(self, block=True, timeout=None):
        return self._results_queue.get(block=block, timeout=timeout)


    def has_result(self):
        return not self._results_queue.empty()
    

    def has_jobs(self):
        return bool(self._futures)


    def shutdown(self, wait=True, cancel_futures=True):
        self.executor.shutdown(wait=wait, cancel_futures=cancel_futures)
        self._stop_event.set()
        self._insert_thread.join()
        self._monitor_thread.join()