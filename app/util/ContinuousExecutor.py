import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor


class ContinuousExecutor:
    def __init__(self, max_workers=5, poll_interval=0.1):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures = []
        self._results_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._poll_interval = poll_interval

        # Start a background thread that checks for completed futures
        self._monitor_thread = threading.Thread(
            target=self._monitor_futures, daemon=True
        )
        self._monitor_thread.start()

    def submit(self, func, *args, **kwargs):
        future = self.executor.submit(func, *args, **kwargs)
        self._futures.append(future)
        return future

    def _monitor_futures(self):
        while not self._stop_event.is_set():
            pending = []
            for fut in self._futures:
                if fut.done():
                    try:
                        result = fut.result()
                        self._results_queue.put(result)
                    except Exception as ex:
                        self._results_queue.put(ex)
                else:
                    pending.append(fut)
            self._futures = pending
            time.sleep(self._poll_interval)

    def get_result(self, block=True, timeout=None):
        return self._results_queue.get(block=block, timeout=timeout)

    def has_result(self):
        return not self._results_queue.empty()

    def shutdown(self, wait=True, cancel_futures=True):
        self._stop_event.set()
        self._monitor_thread.join()
        self.executor.shutdown(wait=wait, cancel_futures=cancel_futures)