Implement a compact signed-integer binary format in Python.

`encode_varints(values) -> bytes`
- Accept a list/tuple of signed 64-bit integers. Reject anything outside
  `[-2**63, 2**63 - 1]` or non-integers with `ValueError`.
- Zigzag-map each signed integer to unsigned: `(n << 1) ^ (n >> 63)`.
- Encode the unsigned value as unsigned LEB128 (7 data bits per byte, low bits
  first, high bit set on every byte except the last).
- Concatenate the encodings. An empty input gives `b""`.

`decode_varints(data) -> list[int]`
- Accept `bytes` or `bytearray`; decode the concatenated stream back to signed
  ints via zigzag.
- Raise `ValueError` for truncated input, for values that do not fit in 64 bits,
  and for non-canonical encodings (an overlong encoding whose final byte is
  zero, e.g. `b"\x80\x00"` for zero).
- Empty data gives `[]`.

Exactly 10 bytes are allowed for the largest values, and the 10th byte must be
`0x01`; more than 10 bytes or a larger 10th byte is overflow.

Return the complete file. Standard library only.
