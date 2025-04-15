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
        self._results_queue = queue.Queue()
        self._futures = []
        self._futures_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._poll_interval = poll_interval
        self._next_id = 0

        # Start a background thread that checks for completed futures
        self._monitor_thread = threading.Thread(target=self._monitor_futures)
        self._monitor_thread.start()


    def submit(self, func, *args, **kwargs):
        future = self.executor.submit(func, *args, **kwargs)
        job = (self._next_id, future)
        self._next_id = self._next_id + 1
        with self._futures_lock:
            self._futures.append(job)
        return future


    def _monitor_futures(self):
        logger.debug("Starting ThreadPool Mon thread")
        while not self._stop_event.is_set():
            with self._futures_lock:
                pending = self._futures

            completed = []
            for entry in pending:
                id_val, fut = entry
                logger.debug(f"Future [{id_val}] state: running={fut.running()}, done={fut.done()}")
                if fut.done():
                    try:
                        result = fut.result()
                        self._results_queue.put(result)
                        logger.debug("Job Completed, added result to queue")
                    except Exception as ex:
                        logger.warning(f"Thread in ThreadPool error - {ex}")
                        self._results_queue.put(ex)

                    completed.append(entry)
            
            for entry in completed:
                pending.remove(entry)

            with self._futures_lock:
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
        #self._insert_thread.join()
        self._monitor_thread.join()