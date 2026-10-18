import importlib.util
import sys

spec = importlib.util.spec_from_file_location("sol", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
LRU = mod.LRUCache

checks = []


def check(name, fn):
    checks.append((name, fn))


def basic():
    c = LRU(2)
    c.put(1, 1)
    c.put(2, 2)
    return c.get(1) == 1


def eviction():
    c = LRU(2)
    c.put(1, 1)
    c.put(2, 2)
    c.put(3, 3)
    return c.get(2) == 2 and c.get(3) == 3 and c.get(1) == -1


def get_refreshes():
    c = LRU(2)
    c.put(1, 1)
    c.put(2, 2)
    c.get(1)
    c.put(3, 3)
    return c.get(2) == -1 and c.get(1) == 1 and c.get(3) == 3


def update_refreshes():
    c = LRU(2)
    c.put(1, 1)
    c.put(2, 2)
    c.put(1, 10)
    c.put(3, 3)
    return c.get(2) == -1 and c.get(1) == 10 and c.get(3) == 3


def update_no_evict():
    c = LRU(2)
    c.put(1, 1)
    c.put(2, 2)
    c.put(1, 5)
    return c.get(2) == 2 and c.get(1) == 5


def capacity_one():
    c = LRU(1)
    c.put(1, 1)
    c.put(2, 2)
    return c.get(1) == -1 and c.get(2) == 2


def missing_key():
    c = LRU(2)
    return c.get(42) == -1


def bad_capacity():
    for bad in (0, -1, True, False, 1.5, "2", None):
        try:
            LRU(bad)
        except ValueError:
            continue
        except Exception:  # noqa: BLE001
            return False
        return False
    return True


check("basic put/get", basic)
check("evicts lru", eviction)
check("get refreshes recency", get_refreshes)
check("update refreshes recency", update_refreshes)
check("update does not evict", update_no_evict)
check("capacity 1", capacity_one)
check("missing key -> -1", missing_key)
check("bad capacity -> ValueError", bad_capacity)

passed = 0
for name, fn in checks:
    try:
        ok = bool(fn())
    except Exception as exc:  # noqa: BLE001
        ok = False
        name = f"{name} [raised {type(exc).__name__}: {exc}]"
    print(("PASS " if ok else "FAIL ") + name)
    passed += ok

print(f"RESULT {passed}/{len(checks)}")
