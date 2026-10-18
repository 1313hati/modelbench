from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
path = solution_arg()

src = ""
mod = {}
try:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    exec(compile(src, path, "exec"), mod)
    fn = mod["parse_json"]
except Exception as exc:  # noqa: BLE001
    C.check("import and parse_json exists", lambda: (_ for _ in ()).throw(exc))
    C.report()

C.eq("null", fn("null"), None)
C.eq("true", fn("true"), True)
C.eq("false", fn("false"), False)
C.eq("integer", fn("42"), 42)
C.eq("negative integer", fn("-17"), -17)
C.eq("zero", fn("0"), 0)
C.eq("float", fn("3.25"), 3.25)
C.eq("exponent float", fn("1e3"), 1000.0)
C.eq("fraction exponent", fn("-2.5E-2"), -0.025)
C.eq("string", fn('"hello"'), "hello")
C.eq("empty string", fn('""'), "")
C.eq("simple escapes", fn(r'"a\"b\\c\/d\be\ff\ng\rh\ti"'), 'a"b\\c/d\be\ff\ng\rh\ti')
C.eq("unicode escape", fn(r'"caf\u00e9"'), "café")
C.eq("surrogate pair", fn(r'"\ud83d\ude00"'), "😀")
C.eq("array", fn("[1, 2, 3]"), [1, 2, 3])
C.eq("nested mix", fn('{"a":[1,{"b":null}],"c":true}'), {"a": [1, {"b": None}], "c": True})
C.eq("empty object", fn("{}"), {})
C.eq("empty array", fn("[]"), [])
C.eq("whitespace everywhere", fn(' \t\r\n { "a" : [ 1 , 2 ] } \n'), {"a": [1, 2]})
C.eq("duplicate keys last wins", fn('{"a":1,"a":2}'), {"a": 2})
C.eq("unicode key", fn('{"é":1}'), {"é": 1})

C.raises("empty document", ValueError, lambda: fn(""))
C.raises("whitespace only", ValueError, lambda: fn("  \n\t"))
C.raises("trailing data", ValueError, lambda: fn("1 2"))
C.raises("trailing comma array", ValueError, lambda: fn("[1,2,]"))
C.raises("trailing comma object", ValueError, lambda: fn('{"a":1,}'))
C.raises("single quotes", ValueError, lambda: fn("'a'"))
C.raises("unquoted key", ValueError, lambda: fn("{a:1}"))
C.raises("leading zero", ValueError, lambda: fn("01"))
C.raises("leading plus", ValueError, lambda: fn("+1"))
C.raises("bare fraction", ValueError, lambda: fn(".5"))
C.raises("trailing dot", ValueError, lambda: fn("1."))
C.raises("NaN", ValueError, lambda: fn("NaN"))
C.raises("Infinity", ValueError, lambda: fn("Infinity"))
C.raises("unclosed array", ValueError, lambda: fn("[1,2"))
C.raises("unclosed string", ValueError, lambda: fn('"abc'))
C.raises("bad escape", ValueError, lambda: fn(r'"\x41"'))
C.raises("invalid unicode escape", ValueError, lambda: fn(r'"\u12G4"'))
C.raises("lone high surrogate", ValueError, lambda: fn(r'"\ud83d"'))
C.raises("lone low surrogate", ValueError, lambda: fn(r'"\ude00"'))
C.raises("raw control char", ValueError, lambda: fn('"a\nb"'))
C.raises("single value with comma", ValueError, lambda: fn("1,"))
C.raises("missing colon", ValueError, lambda: fn('{"a" 1}'))
C.raises("object key must be string", ValueError, lambda: fn("{1:2}"))

C.true("no json import", "import json" not in src and "from json" not in src)
C.true("no ast import", "import ast" not in src and "from ast" not in src)
C.true("no eval/exec", "eval(" not in src and "exec(" not in src)

C.report()
