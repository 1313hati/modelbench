Write `parse_csv(text)` and `write_csv(rows)` in Python: strict RFC 4180-style
CSV with no header handling.

`parse_csv(text) -> list[list[str]]`:
- Records end at LF or CRLF. A bare CR outside quotes is invalid.
- Fields are separated by commas. A field that begins with `"` is quoted; inside
  it, `""` means a literal quote and commas, CR and LF are data. A quoted field
  must be closed; text other than a comma or record ending may not follow the
  closing quote.
- A quote may not appear in an unquoted field.
- Preserve all text exactly. No type conversion.
- `""` parses to `[[""]]`. An empty line is a record with one empty field.
  A trailing record separator does not create an extra record. Empty input is `[]`.
- Invalid input raises `ValueError`.

`write_csv(rows) -> str`:
- Rows are lists/tuples of strings; anything else raises `ValueError`.
- Quote a field only when it contains a comma, a double quote, CR or LF; escape
  embedded quotes by doubling them.
- Use CRLF between records and after the last record. Empty `rows` gives `""`.
- A row with zero fields is invalid.
- `parse_csv(write_csv(rows)) == rows` for every valid row set.

Return the complete file. Standard library only.
