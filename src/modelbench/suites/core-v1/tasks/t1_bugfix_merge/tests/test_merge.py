import copy
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("sol", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
f = mod.merge_intervals

cases = []


def case(name, fn):
    cases.append((name, fn))


case("plain overlap", lambda: f([[1, 3], [2, 6], [8, 10], [15, 18]]) == [[1, 6], [8, 10], [15, 18]])
case("touching", lambda: f([[1, 4], [4, 5]]) == [[1, 5]])
case("chain", lambda: f([[1, 2], [2, 3], [3, 4]]) == [[1, 4]])
case("unsorted", lambda: f([[5, 6], [1, 2], [2, 3]]) == [[1, 3], [5, 6]])
case("nested", lambda: f([[1, 10], [2, 3], [4, 5]]) == [[1, 10]])
case("disjoint", lambda: f([[1, 2], [4, 5]]) == [[1, 2], [4, 5]])
case("single", lambda: f([[7, 9]]) == [[7, 9]])
case("empty", lambda: f([]) == [])


def no_mutation():
    data = [[5, 6], [1, 3], [2, 4]]
    original = copy.deepcopy(data)
    result = f(data)
    return data == original and result == [[1, 4], [5, 6]]


case("input untouched", no_mutation)


def output_is_fresh():
    data = [[1, 2]]
    out = f(data)
    out[0][0] = 99
    return data == [[1, 2]]


case("output independent", output_is_fresh)

passed = 0
for name, fn in cases:
    try:
        ok = bool(fn())
    except Exception as exc:  # noqa: BLE001
        ok = False
        name = f"{name} [raised {type(exc).__name__}: {exc}]"
    print(("PASS " if ok else "FAIL ") + name)
    passed += ok

print(f"RESULT {passed}/{len(cases)}")
