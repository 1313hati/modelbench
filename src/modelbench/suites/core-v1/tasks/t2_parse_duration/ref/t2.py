import re

_UNITS = {"h": 3600, "m": 60, "s": 1}
_ORDER = ["h", "m", "s"]
_TOKEN = re.compile(r"^(\d+[hms])+$")
_PART = re.compile(r"(\d+)([hms])")


def parse_duration(text):
    if not isinstance(text, str) or not text or not _TOKEN.match(text):
        raise ValueError(f"invalid duration: {text!r}")
    total = 0
    seen = []
    for num, unit in _PART.findall(text):
        if unit in seen:
            raise ValueError(f"repeated unit {unit!r} in {text!r}")
        seen.append(unit)
        total += int(num) * _UNITS[unit]
    if seen != [u for u in _ORDER if u in seen]:
        raise ValueError(f"units out of order in {text!r}")
    return total
