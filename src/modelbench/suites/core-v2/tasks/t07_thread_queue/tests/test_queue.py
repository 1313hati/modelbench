from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
path = solution_arg()

mod = {}
try:
    with open(path, encoding="utf-8") as fh:
        exec(compile(fh.read(), path, "exec"), mod)
    BoundedQueue = mod["BoundedQueue"]
    QueueClosed = mod["QueueClosed"]
except Exception as exc:  # noqa: BLE001
    C.check("import BoundedQueue and QueueClosed", lambda: (_ for _ in ()).throw(exc))
    C.report()


def start(fn):
    out = {}

    def wrapped():
        try:
            out["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            out["error"] = exc

    t = threading.Thread(target=wrapped, daemon=True)
    t.start()
    return t, out


C.raises("zero capacity", ValueError, lambda: BoundedQueue(0))
C.raises("negative capacity", ValueError, lambda: BoundedQueue(-1))
C.raises("non-int capacity", ValueError, lambda: BoundedQueue("2"))

q = BoundedQueue(3)
C.eq("starts empty", q.empty(), True)
C.eq("starts not full", q.full(), False)
C.eq("starts size 0", q.qsize(), 0)
q.put("a")
q.put("b")
q.put(None)
C.eq("size after puts", q.qsize(), 3)
C.eq("is full", q.full(), True)
C.eq("fifo 1", q.get(), "a")
C.eq("fifo 2", q.get(), "b")
C.eq("none item round-trips", q.get(), None)
C.eq("empty again", q.empty(), True)


def get_timeout():
    q2 = BoundedQueue(1)
    t0 = time.perf_counter()
    try:
        q2.get(timeout=0.1)
    except TimeoutError:
        dt = time.perf_counter() - t0
        assert 0.05 <= dt < 2.0, f"timeout after {dt:.3f}s"
        return
    raise AssertionError("expected TimeoutError")


def put_timeout():
    q2 = BoundedQueue(1)
    q2.put(1)
    t0 = time.perf_counter()
    try:
        q2.put(2, timeout=0.1)
    except TimeoutError:
        dt = time.perf_counter() - t0
        assert 0.05 <= dt < 2.0, f"timeout after {dt:.3f}s"
        return
    raise AssertionError("expected TimeoutError")


C.check("get timeout on empty", get_timeout)
C.check("put timeout on full", put_timeout)
C.raises("negative get timeout", ValueError, lambda: BoundedQueue(1).get(timeout=-1))
C.raises("negative put timeout", ValueError, lambda: BoundedQueue(1).put(1, timeout=-1))


def put_unblocks():
    q2 = BoundedQueue(1)
    q2.put(1)
    t, out = start(lambda: q2.put(2, timeout=2))
    time.sleep(0.1)
    assert t.is_alive(), "put should still be blocked"
    assert q2.get() == 1
    t.join(2)
    assert not t.is_alive() and "error" not in out
    assert q2.get() == 2


def get_unblocks():
    q2 = BoundedQueue(1)
    t, out = start(lambda: q2.get(timeout=2))
    time.sleep(0.1)
    assert t.is_alive(), "get should still be blocked"
    q2.put("x")
    t.join(2)
    assert not t.is_alive() and out.get("value") == "x"


C.check("put wakes when space appears", put_unblocks)
C.check("get wakes when item arrives", get_unblocks)


def close_wakes_put():
    q2 = BoundedQueue(1)
    q2.put(1)
    t, out = start(lambda: q2.put(2))
    time.sleep(0.1)
    assert t.is_alive()
    q2.close()
    t.join(2)
    assert not t.is_alive(), "put did not wake"
    assert isinstance(out.get("error"), QueueClosed), out


def close_wakes_get():
    q2 = BoundedQueue(1)
    t, out = start(lambda: q2.get())
    time.sleep(0.1)
    assert t.is_alive()
    q2.close()
    t.join(2)
    assert not t.is_alive(), "get did not wake"
    assert isinstance(out.get("error"), QueueClosed), out


C.check("close wakes blocked put", close_wakes_put)
C.check("close wakes blocked get", close_wakes_get)


def drain_after_close():
    q2 = BoundedQueue(4)
    for x in (1, 2, 3):
        q2.put(x)
    q2.close()
    assert q2.closed is True
    assert [q2.get(), q2.get(), q2.get()] == [1, 2, 3]
    try:
        q2.get()
    except QueueClosed:
        return
    raise AssertionError("expected QueueClosed after drain")


def put_after_close():
    q2 = BoundedQueue(2)
    q2.close()
    q2.close()
    try:
        q2.put(1)
    except QueueClosed:
        return
    raise AssertionError("expected QueueClosed")


C.check("drain then QueueClosed", drain_after_close)
C.check("put after close / idempotent close", put_after_close)


def stress():
    q2 = BoundedQueue(16)
    nprod, per = 4, 1500
    seen = []
    errors = []
    lock = threading.Lock()

    def producer(base):
        try:
            for i in range(per):
                q2.put((base, i))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def consumer():
        while True:
            try:
                item = q2.get(timeout=0.2)
            except TimeoutError:
                if q2.closed and q2.empty():
                    return
                continue
            except QueueClosed:
                return
            with lock:
                seen.append(item)

    cons = [threading.Thread(target=consumer, daemon=True) for _ in range(4)]
    prods = [threading.Thread(target=producer, args=(p,), daemon=True) for p in range(nprod)]
    for t in cons:
        t.start()
    for t in prods:
        t.start()
    for t in prods:
        t.join(10)
    q2.close()
    for t in cons:
        t.join(5)
    assert not errors, errors
    assert len(seen) == nprod * per, f"{len(seen)} != {nprod * per}"
    assert len(set(seen)) == nprod * per, "duplicates observed"
    assert all(not t.is_alive() for t in cons), "consumer hung"


C.check("4 producers / 4 consumers, 6000 items", stress)

C.report()
