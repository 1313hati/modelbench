import importlib.util
import sys

spec = importlib.util.spec_from_file_location("sol", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
f = mod.parse_query

checks = []


def check(name, fn):
    checks.append((name, fn))


check("single", lambda: f("a=1") == {"a": ["1"]})
check("duplicates keep order", lambda: f("a=1&a=2&a=3") == {"a": ["1", "2", "3"]})
check("two keys", lambda: f("a=1&b=2") == {"a": ["1"], "b": ["2"]})
check("empty segments", lambda: f("a=1&&b=2&") == {"a": ["1"], "b": ["2"]})
check("only separators", lambda: f("&&") == {})
check("empty string", lambda: f("") == {})
check("plus is space", lambda: f("q=a+b") == {"q": ["a b"]})
check("percent space", lambda: f("q=a%20b") == {"q": ["a b"]})
check("utf8 percent", lambda: f("q=caf%C3%A9") == {"q": ["café"]})
check("encoded key", lambda: f("%61=1") == {"a": ["1"]})
check("equals in value", lambda: f("a=b=c") == {"a": ["b=c"]})
check("bare key", lambda: f("a&b=2") == {"a": [""], "b": ["2"]})
check("empty value", lambda: f("a=&b=2") == {"a": [""], "b": ["2"]})
check("case sensitive", lambda: f("A=1&a=2") == {"A": ["1"], "a": ["2"]})
check("percent-encoded amp", lambda: f("a=%26") == {"a": ["&"]})


def malformed():
    for bad in ("a=%ZZ", "a=%2", "a=%a"):
        try:
            f(bad)
        except ValueError:
            continue
        except Exception:  # noqa: BLE001
            return False
        return False
    return True


check("malformed escapes raise", malformed)


def no_global_state():
    a = f("a=1")
    b = f("b=2")
    return a == {"a": ["1"]} and b == {"b": ["2"]}


check("independent results", no_global_state)

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
