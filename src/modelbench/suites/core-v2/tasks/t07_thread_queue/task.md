Write `BoundedQueue` in Python: a thread-safe, bounded FIFO queue.

```python
class QueueClosed(Exception):
    pass

class BoundedQueue:
    def __init__(self, capacity): ...
    def put(self, item, timeout=None): ...
    def get(self, timeout=None): ...
    def qsize(self): ...
    def empty(self): ...
    def full(self): ...
    def close(self): ...
    @property
    def closed(self): ...
```

Semantics:
- `capacity` must be an `int >= 1`, else `ValueError`.
- `put` appends and returns `None`; it blocks while the queue is full. `timeout`
  is `None` (wait forever) or a number of seconds `>= 0`, else `ValueError`.
  On timeout raise the built-in `TimeoutError`.
- `get` removes and returns the oldest item; blocks while empty, with the same
  timeout rules. On timeout raise `TimeoutError`.
- `close()` is idempotent and wakes every blocked thread. After close, `put`
  raises `QueueClosed`. `get` still drains items that were queued before close,
  and raises `QueueClosed` only once the queue is empty.
- If a thread is blocked in `put`/`get` when `close()` happens, it must raise
  `QueueClosed` immediately, not `TimeoutError`.
- `qsize`, `empty`, `full` and `closed` must be safe to call from any thread.
- FIFO order, no lost or duplicated items, arbitrary item values including `None`.

Return the complete file. Standard library only.
