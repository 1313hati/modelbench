Write `parse_json(text)` in Python: a JSON parser built from scratch.

Return the Python value for a valid JSON document, and raise `ValueError` for
invalid input. Support objects, arrays, strings, numbers, `true`, `false`, `null`
and top-level scalars. Object keys must be strings; if a key repeats, the last
value wins.

Details that must be exact:
- Whitespace is only space, tab, CR and LF. Anything else is data or invalid.
- Strings use double quotes. Recognise the escapes `\" \\ \/ \b \f \n \r \t` and
  `\uXXXX`. A valid surrogate pair must combine into one character; a lone
  surrogate is invalid. Raw control characters below U+0020 inside strings are
  invalid.
- Numbers follow `-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?`. Values without
  a fraction or exponent are `int`, otherwise `float`. Leading `+`, leading
  zeros, `.5`, `1.` and `NaN`/`Infinity` are invalid.
- Trailing non-whitespace after the value is invalid. An empty document is invalid.
- No trailing commas, no comments, no single-quoted strings.

You must implement the parser yourself: do not import `json` or `ast`, and do
not use `eval`/`exec`. Standard library modules other than those are fine.

Return the complete file.
