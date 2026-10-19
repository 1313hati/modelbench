# Clean up the export

A vendor sends configuration files that are *almost* JSON: their generator
allows comments, trailing commas, single quotes, bare keys and Python literals.
Write a reader that accepts exactly that dialect and rejects everything else.

Implement `loads_lenient(text)` in a single Python module using the standard
library only. It returns the parsed Python value. **Do not use `json`, `ast`,
`eval` or `exec`** — the point is the parser.

## Accepted grammar

- **Objects**: `{ ... }`. A key is a double-quoted string, a single-quoted
  string, or a bare identifier matching `[A-Za-z_][A-Za-z0-9_]*`.
- **Arrays**: `[ ... ]`.
- **Strings**: single or double quoted. The only escapes are `\\`, `\"`,
  `\'`, `\n`, `\t` and `\uXXXX` (exactly four hex digits). Any other escape
  is an error.
- **Numbers**: optional `-`, then `0` or a digit sequence without a leading zero,
  an optional fraction, an optional exponent. `01`, `.5`, `5.` and `+1` are
  errors. Values with a fraction or exponent become `float`, others `int`.
- **Literals**: `true`, `false`, `null` and also `True`, `False`, `None`
  (mapped to `True`, `False`, `None`).
- **Trailing commas** are allowed in objects and arrays: `[1, 2,]`.
- **Comments**: `#` to the end of the line, anywhere outside a string.

## Errors

Anything else raises `ValueError`. The message must name the 1-based line:
`... on line 3`. A duplicate key in the same object raises
`ValueError("duplicate key: <name>")` (the line does not matter for that one).
A value followed by anything other than whitespace or a comment is an error.

## Examples

```python
loads_lenient("{name: 'ada', active: True, tags: ['x', 'y',],} # note")
# {'name': 'ada', 'active': True, 'tags': ['x', 'y']}

loads_lenient('{"a": 1, "a": 2}')      # ValueError: duplicate key: a
loads_lenient('{"a": 01}')             # ValueError: ... on line 1
```

Return the complete module in a ```python fence.
