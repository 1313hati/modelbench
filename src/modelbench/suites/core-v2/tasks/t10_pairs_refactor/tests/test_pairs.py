from __future__ import annotations

import os
import random
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
path = solution_arg()

mod = {}
try:
    with open(path, encoding="utf-8") as fh:
        exec(compile(fh.read(), path, "exec"), mod)
    fn = mod["count_pairs"]
except Exception as exc:  # noqa: BLE001
    C.check("import count_pairs", lambda: (_ for _ in ()).throw(exc))
    C.report()

C.eq("empty", fn([], 5), 0)
C.eq("one element", fn([1], 1), 0)
C.eq("basic", fn([1, 2, 3, 4], 5), 2)
C.eq("duplicates", fn([1, 1, 1], 2), 3)
C.eq("negatives", fn([-3, 1, 2, 4, -1], 1), 2)
C.eq("zeros", fn([0, 0, 0, 0], 0), 6)
C.eq("same value distinct indices", fn([2, 2, 2], 4), 3)
C.eq("no pairs", fn([1, 2, 3], 100), 0)
C.eq("negative target", fn([-5, 3, -2, 7], -7), 1)
C.eq("returns int", type(fn([1, 2], 3)), int)

copy = [3, 1, 2]
fn(copy, 4)
C.eq("input not mutated", copy, [3, 1, 2])


def reference(nums, target):
    counts = Counter()
    total = 0
    for value in nums:
        total += counts.get(target - value, 0)
        counts[value] += 1
    return total


def random_cases():
    rng = random.Random(11)
    for _ in range(100):
        nums = [rng.randint(-20, 20) for _ in range(rng.randint(0, 30))]
        target = rng.randint(-30, 30)
        got, want = fn(list(nums), target), reference(nums, target)
        if got != want:
            raise AssertionError(f"{nums} target {target}: got {got}, want {want}")


C.check("100 random cases", random_cases)


def perf():
    nums = [0] * 200_000
    t0 = time.perf_counter()
    got = fn(nums, 0)
    dt = time.perf_counter() - t0
    want = 200_000 * 199_999 // 2
    if got != want:
        raise AssertionError(f"got {got}, want {want}")
    if dt > 1.5:
        raise AssertionError(f"too slow: {dt:.2f}s")


C.check("200k zeros under 1.5s", perf)

C.report()
