import importlib.util
import sys

spec = importlib.util.spec_from_file_location("sol", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
f = mod.parse_duration

valid = [
    ("1h30m", 5400),
    ("90s", 90),
    ("2h", 7200),
    ("1h2m3s", 3723),
    ("0s", 0),
    ("59m59s", 3599),
    ("90m", 5400),
    ("100h", 360000),
    ("1s", 1),
]

invalid = ["", "h", "10", "1h1h", "1x", "1.5h", "-1h", " 1h", "1h ", "1h 30m", "1m1h", "1H", "1h2h"]

passed = 0
total = len(valid) + len(invalid)

for text, want in valid:
    try:
        got = f(text)
        ok = got == want and isinstance(got, int) and not isinstance(got, bool)
        label = f"{text!r} -> {got!r} (want {want!r})"
    except Exception as exc:  # noqa: BLE001
        ok = False
        label = f"{text!r} raised {type(exc).__name__}: {exc}"
    print(("PASS " if ok else "FAIL ") + label)
    passed += ok

for text in invalid:
    try:
        got = f(text)
        ok = False
        label = f"{text!r} should raise ValueError, returned {got!r}"
    except ValueError:
        ok = True
        label = f"{text!r} raised ValueError"
    except Exception as exc:  # noqa: BLE001
        ok = False
        label = f"{text!r} raised {type(exc).__name__} (want ValueError)"
    print(("PASS " if ok else "FAIL ") + label)
    passed += ok

print(f"RESULT {passed}/{total}")
