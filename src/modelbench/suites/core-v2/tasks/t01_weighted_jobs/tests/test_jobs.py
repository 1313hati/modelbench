from __future__ import annotations

import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
path = solution_arg()

mod = {}
try:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    exec(compile(src, path, "exec"), mod)
    fn = mod["max_profit"]
except Exception as exc:  # noqa: BLE001
    C.check("import and max_profit exists", lambda: (_ for _ in ()).throw(exc))
    C.report()

C.eq("empty", fn([]), 0)
C.eq("single", fn([(1, 5, 10)]), 10)
C.eq("two disjoint", fn([(1, 2, 3), (5, 6, 4)]), 7)
C.eq("two overlapping", fn([(1, 5, 10), (2, 6, 100)]), 100)
C.eq("touching is allowed", fn([(1, 2, 3), (2, 3, 4)]), 7)
C.eq("containment", fn([(1, 10, 5), (2, 3, 100)]), 100)
C.eq("classic", fn([(1, 3, 50), (2, 4, 10), (3, 5, 40)]), 90)
C.eq("unsorted chain", fn([(5, 6, 4), (1, 2, 3), (2, 3, 5)]), 12)
C.eq("duplicate intervals pick one", fn([(1, 4, 7), (1, 4, 9)]), 9)

copy = [(3, 8, 5), (1, 2, 2), (2, 3, 2)]
fn(copy)
C.eq("input not mutated", copy, [(3, 8, 5), (1, 2, 2), (2, 3, 2)])


def brute(jobs):
    best = 0
    n = len(jobs)
    for mask in range(1 << n):
        chosen = [jobs[i] for i in range(n) if mask >> i & 1]
        chosen.sort()
        ok = all(chosen[i][1] <= chosen[i + 1][0] for i in range(len(chosen) - 1))
        if ok:
            best = max(best, sum(j[2] for j in chosen))
    return best


def brute_cases():
    rng = random.Random(7)
    for _ in range(120):
        n = rng.randint(0, 9)
        jobs = []
        for _ in range(n):
            a = rng.randint(0, 12)
            b = rng.randint(a + 1, 15)
            jobs.append((a, b, rng.randint(1, 20)))
        got = fn(list(jobs))
        want = brute(jobs)
        if got != want:
            raise AssertionError(f"{jobs}: got {got}, want {want}")


C.check("120 random cases vs brute force", brute_cases)


def perf():
    n = 200_000
    jobs = [(i, i + 1, 1) for i in range(n)]
    t0 = time.perf_counter()
    got = fn(jobs)
    dt = time.perf_counter() - t0
    if got != n:
        raise AssertionError(f"got {got}, want {n}")
    if dt > 3.0:
        raise AssertionError(f"too slow: {dt:.2f}s")


C.check("200k jobs under 3s and correct", perf)

C.report()
