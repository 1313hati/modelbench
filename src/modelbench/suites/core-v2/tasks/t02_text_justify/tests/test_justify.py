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
    fn = mod["justify"]
except Exception as exc:  # noqa: BLE001
    C.check("import and justify exists", lambda: (_ for _ in ()).throw(exc))
    C.report()

C.eq("empty", fn([], 10), [])
C.eq(
    "newsroom example",
    fn(["This", "is", "an", "example", "of", "text", "justification."], 16),
    ["This    is    an", "example  of text", "justification."],
)
C.eq("single word", fn(["hello"], 5), ["hello"])
C.eq("single word narrow", fn(["a"], 1), ["a"])
C.eq(
    "spaces distributed left to right",
    fn(["a", "b", "c", "d"], 6),
    ["a  b c", "d"],
)
C.eq(
    "last line packed",
    fn(["one", "two", "three", "four"], 7),
    ["one two", "three", "four"],
)
C.eq(
    "exact fit no padding",
    fn(["abc", "de"], 6),
    ["abc de"],
)
C.eq(
    "two lines full and ragged",
    fn(["aa", "bb", "cc", "dd", "ee"], 5),
    ["aa bb", "cc dd", "ee"],
)
C.eq(
    "one word per line",
    fn(["aa", "bb", "cc"], 2),
    ["aa", "bb", "cc"],
)
C.eq(
    "long text",
    fn(["The", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog."], 11),
    ["The   quick", "brown   fox", "jumps  over", "the    lazy", "dog."],
)
C.raises("width zero", ValueError, lambda: fn(["a"], 0))
C.raises("width negative", ValueError, lambda: fn(["a"], -3))
C.raises("width not int", ValueError, lambda: fn(["a"], "5"))
C.raises("word too long", ValueError, lambda: fn(["abcdef"], 5))
C.raises("empty word", ValueError, lambda: fn(["a", ""], 5))
C.raises("word with space", ValueError, lambda: fn(["a b"], 5))
C.raises("word with newline", ValueError, lambda: fn(["a\nb"], 5))
C.eq("does not mutate input", (lambda w: (fn(w, 8), w)[1])(["a", "b", "c"]), ["a", "b", "c"])

C.report()
