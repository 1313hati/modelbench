import re

_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_HEX = set("0123456789abcdefABCDEF")


class _Parser:
    def __init__(self, text):
        if not isinstance(text, str):
            raise ValueError("input must be text")
        self.text = text
        self.pos = 0
        self.n = len(text)

    def parse(self):
        self.ws()
        if self.pos >= self.n:
            raise ValueError("empty document")
        value = self.value()
        self.ws()
        if self.pos != self.n:
            raise ValueError(f"trailing data at {self.pos}")
        return value

    def ws(self):
        while self.pos < self.n and self.text[self.pos] in " \t\r\n":
            self.pos += 1

    def value(self):
        if self.pos >= self.n:
            raise ValueError("unexpected end")
        ch = self.text[self.pos]
        if ch == "{":
            return self.obj()
        if ch == "[":
            return self.arr()
        if ch == '"':
            return self.string()
        if ch == "t":
            return self.literal("true", True)
        if ch == "f":
            return self.literal("false", False)
        if ch == "n":
            return self.literal("null", None)
        if ch == "-" or ch.isdigit():
            return self.number()
        raise ValueError(f"unexpected character {ch!r} at {self.pos}")

    def literal(self, word, value):
        if self.text.startswith(word, self.pos):
            self.pos += len(word)
            return value
        raise ValueError(f"invalid literal at {self.pos}")

    def number(self):
        match = _NUMBER.match(self.text, self.pos)
        if not match:
            raise ValueError(f"invalid number at {self.pos}")
        token = match.group(0)
        self.pos = match.end()
        if "." in token or "e" in token or "E" in token:
            return float(token)
        return int(token)

    def string(self):
        self.pos += 1
        out = []
        while self.pos < self.n:
            ch = self.text[self.pos]
            self.pos += 1
            if ch == '"':
                return "".join(out)
            if ch == "\\":
                out.append(self.escape())
            elif ord(ch) < 0x20:
                raise ValueError("raw control character in string")
            else:
                out.append(ch)
        raise ValueError("unterminated string")

    def escape(self):
        if self.pos >= self.n:
            raise ValueError("unterminated escape")
        ch = self.text[self.pos]
        self.pos += 1
        simple = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
        if ch in simple:
            return simple[ch]
        if ch != "u":
            raise ValueError(f"invalid escape \\{ch}")
        code = self.hex4()
        if 0xDC00 <= code <= 0xDFFF:
            raise ValueError("lone low surrogate")
        if 0xD800 <= code <= 0xDBFF:
            if not self.text.startswith("\\u", self.pos):
                raise ValueError("lone high surrogate")
            self.pos += 2
            low = self.hex4()
            if not 0xDC00 <= low <= 0xDFFF:
                raise ValueError("invalid low surrogate")
            return chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00))
        return chr(code)

    def hex4(self):
        if self.pos + 4 > self.n:
            raise ValueError("short unicode escape")
        digits = self.text[self.pos:self.pos + 4]
        if any(ch not in _HEX for ch in digits):
            raise ValueError("invalid unicode escape")
        self.pos += 4
        return int(digits, 16)

    def arr(self):
        self.pos += 1
        self.ws()
        out = []
        if self.pos < self.n and self.text[self.pos] == "]":
            self.pos += 1
            return out
        while True:
            self.ws()
            out.append(self.value())
            self.ws()
            if self.pos >= self.n:
                raise ValueError("unterminated array")
            ch = self.text[self.pos]
            self.pos += 1
            if ch == "]":
                return out
            if ch != ",":
                raise ValueError("expected comma or closing bracket")

    def obj(self):
        self.pos += 1
        self.ws()
        out = {}
        if self.pos < self.n and self.text[self.pos] == "}":
            self.pos += 1
            return out
        while True:
            self.ws()
            if self.pos >= self.n or self.text[self.pos] != '"':
                raise ValueError("object key must be a string")
            key = self.string()
            self.ws()
            if self.pos >= self.n or self.text[self.pos] != ":":
                raise ValueError("expected colon")
            self.pos += 1
            self.ws()
            out[key] = self.value()
            self.ws()
            if self.pos >= self.n:
                raise ValueError("unterminated object")
            ch = self.text[self.pos]
            self.pos += 1
            if ch == "}":
                return out
            if ch != ",":
                raise ValueError("expected comma or closing brace")


def parse_json(text):
    return _Parser(text).parse()
