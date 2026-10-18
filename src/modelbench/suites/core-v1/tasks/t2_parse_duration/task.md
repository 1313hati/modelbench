Write `parse_duration(text: str) -> int` in Python. It converts a compact duration string
into a whole number of seconds.

Rules:
- The string is one or more `<integer><unit>` groups with no spaces, e.g. `"1h30m"`, `"90s"`, `"2h"`, `"1h2m3s"`.
- Units are `h`, `m`, `s` (hours, minutes, seconds), each used at most once, and they must appear in
  descending order: hours, then minutes, then seconds. `"1m1h"` is invalid.
- Values may exceed their natural range: `"90m"` is 5400, `"100h"` is 360000.
- `"0s"` is 0 and valid. Upper case units (`"1H"`) are invalid.
- Anything else raises `ValueError`: empty string, `"h"`, `"10"` (no unit), `"1h1h"` (repeated unit),
  `"1x"` (unknown unit), `"1.5h"`, `"-1h"`, `" 1h"`, `"1h "`, `"1h 30m"`.

Return the complete file. No I/O, no third-party imports.
