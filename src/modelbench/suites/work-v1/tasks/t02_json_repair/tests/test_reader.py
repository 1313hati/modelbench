#!/usr/bin/env python3
"""Grade the lenient reader against the dialect spec, values first, errors second."""

from __future__ import annotations

import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
path = solution_arg()
source = ""
try:
    source = open(path, encoding="utf-8", errors="replace").read()
except OSError as exc:
    C.check("solution file is readable", lambda: (_ for _ in ()).throw(exc))

module = None
load_error: Exception | None = None
try:
    spec = importlib.util.spec_from_file_location("candidate_reader", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(getattr(module, "loads_lenient", None)), "no callable loads_lenient"
except Exception as exc:  # noqa: BLE001 - a broken module fails checks, not the grader
    load_error = exc


def call(text: str):
    if load_error is not None:
        raise AssertionError(f"could not load a working loads_lenient: {load_error}")
    return module.loads_lenient(text)


def expect_error(name: str, text: str, needle: str | None = None) -> None:
    def run() -> None:
        try:
            call(text)
        except ValueError as exc:
            message = str(exc)
            if needle and needle not in message:
                raise AssertionError(f"message {message!r} does not contain {needle!r}") from None
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(f"raised {type(exc).__name__}: {exc}; want ValueError") from None
        else:
            raise AssertionError("did not raise ValueError")

    C.check(name, run)


C.eq("bare keys and mixed quoting", call("{name: 'ada', role: \"admin\"}"), {"name": "ada", "role": "admin"})
C.eq("trailing commas in objects and arrays", call("{a: [1, 2,], b: {c: 3,},}"), {"a": [1, 2], "b": {"c": 3}})
C.eq("comments are ignored", call("{a: 1, # trailing\nb: 2}"), {"a": 1, "b": 2})
C.eq("python literals", call("[True, False, None]"), [True, False, None])
C.eq("escapes", call(r"'a\nb\tc\\d\'e\u00e9'"), "a\nb\tc\\d'e\u00e9")
C.eq("numbers", call("[-0, 12, -3.5, 1e3, 2.5E-2, 0.0]"), [0, 12, -3.5, 1000.0, 0.025, 0.0])
C.eq("nested structure", call("{a: [{b: [1, {c: 'd'}]}]}"), {"a": [{"b": [1, {"c": "d"}]}]})
C.eq("empty containers", call("{a: {}, b: []}"), {"a": {}, "b": []})
C.true(
    "int stays int, float stays float, true is bool",
    type(call("1")) is int and type(call("1.0")) is float and call("true") is True,
)
expect_error("duplicate key is rejected", '{"a": 1, "a": 2}', "duplicate key: a")
expect_error("unterminated string names the line", '{"a": "oops}', "line 1")
expect_error("error on line 4 reports line 4", '{\n  a: 1,\n  b: 2,\n  c: ?\n}', "line 4")
expect_error("leading zero is rejected", "[01]")
expect_error("unknown escape is rejected", r'["a\qb"]')
expect_error("trailing data is rejected", "{a: 1} {b: 2}")
expect_error("missing colon is rejected", "{a 1}")
expect_error("NaN is not a literal", "[NaN,]")
C.true(
    "no json/eval shortcuts in the source",
    not any(token in source for token in ("import json", "json.loads", "ast.literal_eval", "eval(", "exec(")),
)

C.report()
