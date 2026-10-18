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
    enc = mod["encode_varints"]
    dec = mod["decode_varints"]
except Exception as exc:  # noqa: BLE001
    C.check("import encode_varints/decode_varints", lambda: (_ for _ in ()).throw(exc))
    C.report()

MIN = -(2**63)
MAX = 2**63 - 1

C.eq("encode empty", enc([]), b"")
C.eq("decode empty", dec(b""), [])
C.eq("zero", enc([0]), b"\x00")
C.eq("minus one", enc([-1]), b"\x01")
C.eq("one", enc([1]), b"\x02")
C.eq("minus two", enc([-2]), b"\x03")
C.eq("two", enc([2]), b"\x04")
C.eq("63", enc([63]), b"\x7e")
C.eq("minus 64", enc([-64]), b"\x7f")
C.eq("64", enc([64]), b"\x80\x01")
C.eq("minus 65", enc([-65]), b"\x81\x01")
C.eq("128", enc([128]), b"\x80\x02")
C.eq("127", enc([127]), b"\xfe\x01")
C.eq("max int64", enc([MAX]), b"\xfe\xff\xff\xff\xff\xff\xff\xff\xff\x01")
C.eq("min int64", enc([MIN]), b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01")
C.eq("decode known", dec(b"\x00\x01\x02\x03\x04"), [0, -1, 1, -2, 2])
C.eq("roundtrip extremes", dec(enc([MIN, -1, 0, 1, MAX])), [MIN, -1, 0, 1, MAX])
C.eq(
    "roundtrip assorted",
    dec(enc([0, 1, -1, 63, 64, -64, -65, 127, 128, 1000000, -1000000])),
    [0, 1, -1, 63, 64, -64, -65, 127, 128, 1000000, -1000000],
)
C.eq("concatenated streams", dec(enc([1, 2]) + enc([-3])), [1, 2, -3])
C.eq("decode bytearray", dec(bytearray(enc([5, -6]))), [5, -6])

C.raises("truncated one byte", ValueError, lambda: dec(b"\x80"))
C.raises("truncated long", ValueError, lambda: dec(b"\xff\xff"))
C.raises("non-canonical zero", ValueError, lambda: dec(b"\x80\x00"))
C.raises("non-canonical one", ValueError, lambda: dec(b"\x81\x00"))
C.raises("overflow 10th byte 2", ValueError, lambda: dec(b"\xff" * 9 + b"\x02"))
C.raises("overflow all ff", ValueError, lambda: dec(b"\xff" * 10))
C.raises("too many bytes", ValueError, lambda: dec(b"\xff" * 10 + b"\x00"))
C.raises("decode text", ValueError, lambda: dec("abc"))
C.raises("encode too large", ValueError, lambda: enc([2**63]))
C.raises("encode too small", ValueError, lambda: enc([-(2**63) - 1]))
C.raises("encode float", ValueError, lambda: enc([1.0]))
C.raises("encode string", ValueError, lambda: enc(["1"]))

C.report()
