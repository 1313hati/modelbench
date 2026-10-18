import importlib.util
import itertools
import sys

spec = importlib.util.spec_from_file_location("sol", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
f = mod.chunked

checks = []


def check(name, fn):
    checks.append((name, fn))


check("exact fit", lambda: list(f([0, 1, 2, 3], 2)) == [(0, 1), (2, 3)])
check("short tail", lambda: list(f(range(7), 3)) == [(0, 1, 2), (3, 4, 5), (6,)])
check("overlap 1", lambda: list(f(range(5), 3, 1)) == [(0, 1, 2), (2, 3, 4)])
check("starts 0,2,4", lambda: list(f(range(6), 3, 1)) == [(0, 1, 2), (2, 3, 4), (4, 5)])
check("no duplicate-only tail", lambda: list(f(range(3), 3, 1)) == [(0, 1, 2)])
check("size 1", lambda: list(f("abc", 1)) == [("a",), ("b",), ("c",)])
check("max overlap", lambda: list(f(range(4), 4, 3)) == [(0, 1, 2, 3)])
check("empty", lambda: list(f([], 3)) == [])


def generator_input():
    gen = (x * 2 for x in range(5))
    return list(f(gen, 2)) == [(0, 2), (4, 6), (8,)]


check("generator input", generator_input)


def lazy():
    counter = {"n": 0}

    def source():
        for i in itertools.count():
            counter["n"] += 1
            yield i

    got = list(itertools.islice(f(source(), 4, 2), 3))
    return got == [(0, 1, 2, 3), (2, 3, 4, 5), (4, 5, 6, 7)] and counter["n"] <= 12


check("lazy on infinite source", lazy)


def rejects_bad_args():
    bad = [
        (range(5), 0, 0),
        (range(5), -1, 0),
        (range(5), 3, 3),
        (range(5), 3, -1),
        (range(5), True, 0),
        (range(5), 3, False),
        (range(5), 2.0, 0),
        (range(5), 3, 1.0),
        (range(5), "3", 0),
    ]
    for args in bad:
        try:
            list(f(*args))
        except ValueError:
            continue
        except Exception:  # noqa: BLE001
            return False
        return False
    return True


check("bad arguments", rejects_bad_args)


def returns_tuples():
    out = list(f([1, 2, 3], 2))
    return all(isinstance(chunk, tuple) for chunk in out)


check("chunks are tuples", returns_tuples)

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
