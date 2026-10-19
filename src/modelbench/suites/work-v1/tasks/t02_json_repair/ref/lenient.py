"""A reader for the vendor's almost-JSON dialect. Standard library only."""

from __future__ import annotations


class _Parser:
    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0
        self.n = len(text)

    # -- helpers --------------------------------------------------------- #
    def line(self, pos: int | None = None) -> int:
        return self.s.count("\n", 0, self.i if pos is None else pos) + 1

    def fail(self, message: str, pos: int | None = None) -> None:
        raise ValueError(f"{message} on line {self.line(pos)}")

    def skip(self) -> None:
        while self.i < self.n:
            ch = self.s[self.i]
            if ch in " \t\r\n":
                self.i += 1
            elif ch == "#":
                while self.i < self.n and self.s[self.i] not in "\r\n":
                    self.i += 1
            else:
                return

    def peek(self) -> str:
        self.skip()
        return self.s[self.i] if self.i < self.n else ""

    def take(self, ch: str, what: str) -> None:
        if self.peek() != ch:
            self.fail(f"expected {what}")
        self.i += 1

    # -- values ----------------------------------------------------------- #
    def value(self):
        ch = self.peek()
        if not ch:
            self.fail("unexpected end of input")
        if ch == "{":
            return self.object()
        if ch == "[":
            return self.array()
        if ch in "'\"":
            return self.string()
        if ch == "-" or ch.isdigit():
            return self.number()
        for word, literal in (("true", True), ("false", False), ("null", None),
                              ("True", True), ("False", False), ("None", None)):
            if self.s.startswith(word, self.i):
                end = self.i + len(word)
                if end < self.n and (self.s[end].isalnum() or self.s[end] == "_"):
                    continue
                self.i = end
                return literal
        self.fail(f"unexpected character {ch!r}")

    def object(self):
        self.take("{", "'{'")
        out: dict = {}
        while True:
            if self.peek() == "}":
                self.i += 1
                return out
            key = self.key()
            if key in out:
                raise ValueError(f"duplicate key: {key}")
            self.take(":", "':'")
            out[key] = self.value()
            ch = self.peek()
            if ch == ",":
                self.i += 1
                continue
            if ch == "}":
                self.i += 1
                return out
            self.fail("expected ',' or '}'")

    def array(self):
        self.take("[", "'['")
        out: list = []
        while True:
            if self.peek() == "]":
                self.i += 1
                return out
            out.append(self.value())
            ch = self.peek()
            if ch == ",":
                self.i += 1
                continue
            if ch == "]":
                self.i += 1
                return out
            self.fail("expected ',' or ']'")

    def key(self) -> str:
        ch = self.peek()
        if ch in "'\"":
            return self.string()
        start = self.i
        if not (ch.isalpha() or ch == "_"):
            self.fail("expected a key")
        self.i += 1
        while self.i < self.n and (self.s[self.i].isalnum() or self.s[self.i] == "_"):
            self.i += 1
        return self.s[start:self.i]

    def string(self) -> str:
        quote = self.s[self.i]
        start = self.i
        self.i += 1
        out: list[str] = []
        escapes = {"\\": "\\", '"': '"', "'": "'", "n": "\n", "t": "\t"}
        while True:
            if self.i >= self.n:
                self.fail("unterminated string", start)
            ch = self.s[self.i]
            if ch == quote:
                self.i += 1
                return "".join(out)
            if ch == "\\":
                self.i += 1
                if self.i >= self.n:
                    self.fail("unterminated escape", start)
                esc = self.s[self.i]
                if esc in escapes:
                    out.append(escapes[esc])
                    self.i += 1
                elif esc == "u":
                    digits = self.s[self.i + 1:self.i + 5]
                    if len(digits) != 4 or any(c not in "0123456789abcdefABCDEF" for c in digits):
                        self.fail("bad \\u escape")
                    out.append(chr(int(digits, 16)))
                    self.i += 5
                else:
                    self.fail(f"unknown escape \\{esc}")
            else:
                out.append(ch)
                self.i += 1

    def number(self):
        start = self.i
        if self.s[self.i] == "-":
            self.i += 1
        if self.i >= self.n or not self.s[self.i].isdigit():
            self.fail("malformed number", start)
        if self.s[self.i] == "0":
            self.i += 1
            if self.i < self.n and self.s[self.i].isdigit():
                self.fail("leading zero in number", start)
        else:
            while self.i < self.n and self.s[self.i].isdigit():
                self.i += 1
        is_float = False
        if self.i < self.n and self.s[self.i] == ".":
            is_float = True
            self.i += 1
            if self.i >= self.n or not self.s[self.i].isdigit():
                self.fail("malformed fraction", start)
            while self.i < self.n and self.s[self.i].isdigit():
                self.i += 1
        if self.i < self.n and self.s[self.i] in "eE":
            is_float = True
            self.i += 1
            if self.i < self.n and self.s[self.i] in "+-":
                self.i += 1
            if self.i >= self.n or not self.s[self.i].isdigit():
                self.fail("malformed exponent", start)
            while self.i < self.n and self.s[self.i].isdigit():
                self.i += 1
        text = self.s[start:self.i]
        return float(text) if is_float else int(text)


def loads_lenient(text: str):
    """Parse the vendor dialect; raises ValueError on anything unexpected."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    parser = _Parser(text)
    value = parser.value()
    parser.skip()
    if parser.i != parser.n:
        parser.fail("unexpected data after the value")
    return value
