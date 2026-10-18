import re
from urllib.parse import unquote

_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _decode(part):
    if _BAD_ESCAPE.search(part):
        raise ValueError(f"malformed percent escape in {part!r}")
    return unquote(part.replace("+", " "), encoding="utf-8", errors="strict")


def parse_query(query):
    params = {}
    for segment in query.split("&"):
        if not segment:
            continue
        if "=" in segment:
            key, value = segment.split("=", 1)
        else:
            key, value = segment, ""
        key = _decode(key)
        value = _decode(value)
        params.setdefault(key, []).append(value)
    return params
