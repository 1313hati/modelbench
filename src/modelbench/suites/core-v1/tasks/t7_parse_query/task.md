Write `parse_query(query: str) -> dict[str, list[str]]` in Python, a query-string parser.

Rules:
- Segments are separated by `&`. Empty segments are ignored, so `"a=1&&b=2&"` has two parameters.
- A segment splits on its FIRST `=`. A segment with no `=` is a bare key with the value `""`.
- Keys and values are percent-decoded: `+` becomes a space, `%HH` becomes that byte, and the result is
  decoded as UTF-8. A malformed escape (`"%ZZ"`, `"%2"`, `"%a"`) raises `ValueError`.
- Keys are case sensitive and every occurrence is kept, in encounter order: `"a=1&a=2"` gives
  `{"a": ["1", "2"]}`.
- An empty query, `"&&"` or `"&"` gives `{}`. `"a=b=c"` gives `{"a": ["b=c"]}`.
- No I/O, standard library only.

Return the complete file.
