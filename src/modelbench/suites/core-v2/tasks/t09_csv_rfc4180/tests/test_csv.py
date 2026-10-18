from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
path = solution_arg()

mod = {}
try:
    with open(path, encoding="utf-8") as fh:
        exec(compile(fh.read(), path, "exec"), mod)
    parse_csv = mod["parse_csv"]
    write_csv = mod["write_csv"]
except Exception as exc:  # noqa: BLE001
    C.check("import parse_csv and write_csv", lambda: (_ for _ in ()).throw(exc))
    C.report()

C.eq("empty input", parse_csv(""), [])
C.eq("single field", parse_csv("abc"), [["abc"]])
C.eq("trailing LF", parse_csv("a,b\n"), [["a", "b"]])
C.eq("LF rows", parse_csv("a,b\nc,d\n"), [["a", "b"], ["c", "d"]])
C.eq("CRLF rows", parse_csv("a,b\r\nc,d\r\n"), [["a", "b"], ["c", "d"]])
C.eq("no final newline", parse_csv("a,b\r\nc,d"), [["a", "b"], ["c", "d"]])
C.eq("blank line is empty field", parse_csv("a\n\nb"), [["a"], [""], ["b"]])
C.eq("only newline", parse_csv("\n"), [[""]])
C.eq("empty fields", parse_csv("a,,b,"), [["a", "", "b", ""]])
C.eq("only comma", parse_csv(","), [["", ""]])
C.eq("quoted comma", parse_csv('"a,b",c'), [["a,b", "c"]])
C.eq("quoted newline", parse_csv('"a\nb",c'), [["a\nb", "c"]])
C.eq("quoted CRLF", parse_csv('"a\r\nb"'), [["a\r\nb"]])
C.eq("escaped quotes", parse_csv('"a""b",c'), [['a"b', "c"]])
C.eq("quoted empty", parse_csv('""'), [[""]])
C.eq("quoted empty plus field", parse_csv('"",x'), [["", "x"]])
C.eq("spaces preserved", parse_csv(" a , b "), [[" a ", " b "]])
C.eq("quoted spaces", parse_csv('" a "," b "'), [[" a ", " b "]])
C.eq("write empty", write_csv([]), "")
C.eq("write minimal", write_csv([["a", "b"], ["c", "d"]]), "a,b\r\nc,d\r\n")
C.eq(
    "write quotes when needed",
    write_csv([["a", "b,c", 'd"e', "f\ng", "h\r\ni"]]),
    'a,"b,c","d""e","f\ng","h\r\ni"\r\n',
)
C.eq("write empty fields", write_csv([["", ""]]), ",\r\n")
C.eq("write empty row field", write_csv([[""]]), "\r\n")

C.raises("unclosed quote", ValueError, lambda: parse_csv('"abc'))
C.raises("text after closing quote", ValueError, lambda: parse_csv('"a"x'))
C.raises("space after closing quote", ValueError, lambda: parse_csv('"a" ,b'))
C.raises("quote in unquoted field", ValueError, lambda: parse_csv('a"b'))
C.raises("bare CR", ValueError, lambda: parse_csv("a\rb"))
C.raises("bare CR mid row", ValueError, lambda: parse_csv("a,b\rc,d"))
C.raises("write non-list", ValueError, lambda: write_csv("abc"))
C.raises("write empty row", ValueError, lambda: write_csv([[]]))
C.raises("write non-string field", ValueError, lambda: write_csv([["a", 1]]))

rows = [["plain", "with,comma", 'with"quote', "with\nnewline", "", " padded "], ["", "x"]]
C.eq("roundtrip", parse_csv(write_csv(rows)), rows)

C.report()
