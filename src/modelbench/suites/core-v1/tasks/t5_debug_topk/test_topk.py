import importlib.util
import random
import sys

spec = importlib.util.spec_from_file_location("sol", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
f = mod.top_k_frequent

checks = []


def check(name, fn):
    checks.append((name, fn))


check("doc example", lambda: f([1, 1, 1, 2, 2, 3], 2) == [1, 2])
check("k = 1", lambda: f([4, 4, 9, 9, 9], 1) == [9])
check("tie by value", lambda: f([3, 3, 1, 1, 2, 2], 2) == [1, 2])
check("all distinct", lambda: f([5, 4, 3], 3) == [3, 4, 5])
check("negatives", lambda: f([-1, -1, -2, 7, 7, 7], 2) == [7, -1])
check("single", lambda: f([8], 1) == [8])


def brute_agree():
    rnd = random.Random(7)
    for _ in range(60):
        nums = [rnd.randint(-5, 5) for _ in range(rnd.randint(1, 40))]
        k = rnd.randint(1, len(set(nums)))
        want = sorted(set(nums), key=lambda v: (-nums.count(v), v))[:k]
        if f(nums, k) != want:
            return False
    return True


check("matches brute force", brute_agree)


def no_mutation():
    nums = [2, 2, 1]
    f(nums, 1)
    return nums == [2, 2, 1]


check("input untouched", no_mutation)

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
