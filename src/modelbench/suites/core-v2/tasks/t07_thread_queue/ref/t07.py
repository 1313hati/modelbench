import threading
import time


class QueueClosed(Exception):
    pass


class BoundedQueue:
    def __init__(self, capacity):
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be an integer >= 1")
        self._capacity = capacity
        self._items = []
        self._closed = False
        self._cond = threading.Condition()

    @staticmethod
    def _check_timeout(timeout):
        if timeout is not None:
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0:
                raise ValueError("timeout must be None or a number >= 0")

    def put(self, item, timeout=None):
        self._check_timeout(timeout)
        with self._cond:
            if self._closed:
                raise QueueClosed()
            if timeout is None:
                while len(self._items) >= self._capacity and not self._closed:
                    self._cond.wait()
            else:
                deadline = time.monotonic() + timeout
                while len(self._items) >= self._capacity and not self._closed:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    self._cond.wait(remaining)
            if self._closed:
                raise QueueClosed()
            self._items.append(item)
            self._cond.notify_all()

    def get(self, timeout=None):
        self._check_timeout(timeout)
        with self._cond:
            if timeout is None:
                while not self._items and not self._closed:
                    self._cond.wait()
            else:
                deadline = time.monotonic() + timeout
                while not self._items and not self._closed:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    self._cond.wait(remaining)
            if self._items:
                item = self._items.pop(0)
                self._cond.notify_all()
                return item
            raise QueueClosed()

    def qsize(self):
        with self._cond:
            return len(self._items)

    def empty(self):
        with self._cond:
            return not self._items

    def full(self):
        with self._cond:
            return len(self._items) >= self._capacity

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    @property
    def closed(self):
        with self._cond:
            return self._closed
