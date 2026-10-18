import importlib.util
import random
import sys
import time

spec = importlib.util.spec_from_file_location("sol", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
f = mod.has_duplicate_within_k

checks = []


def check(name, fn):
    checks.append((name, fn))


check("doc true", lambda: f([1, 2, 3, 1], 3) is True)
check("doc false", lambda: f([1, 2, 3, 1], 2) is False)
check("k = 1 adjacent", lambda: f([1, 1, 2], 1) is True)
check("k = 1 apart", lambda: f([1, 2, 1], 1) is False)
check("no duplicates", lambda: f(list(range(100)), 5) is False)
check("empty", lambda: f([], 3) is False)
check("single", lambda: f([7], 3) is False)
check("negative values", lambda: f([-1, 5, -1], 2) is True)


def rejects_bad_k():
    for bad in (0, -3):
        try:
            f([1, 1], bad)
        except ValueError:
            continue
        except Exception:  # noqa: BLE001
            return False
        return False
    return True


check("bad k -> ValueError", rejects_bad_k)


def brute_agree():
    rnd = random.Random(11)
    naive = lambda a, k: any(a[i] == a[j] for i in range(len(a)) for j in range(i + 1, min(len(a), i + k + 1)))
    for _ in range(80):
        nums = [rnd.randint(0, 6) for _ in range(rnd.randint(0, 25))]
        k = rnd.randint(1, 8)
        if f(nums, k) != naive(nums, k):
            return False
    return True


check("matches brute force", brute_agree)


def no_mutation():
    nums = [1, 2, 1]
    f(nums, 2)
    return nums == [1, 2, 1]


check("input untouched", no_mutation)


def fast():
    rnd = random.Random(3)
    big = [rnd.randrange(100_000) for _ in range(200_000)]
    t0 = time.perf_counter()
    got = f(big, 10)
    dt = time.perf_counter() - t0
    ok = isinstance(got, bool) and dt < 2.0
    print(f"     200k in {dt * 1000:.0f} ms")
    return ok


check("200k under 2s", fast)

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
