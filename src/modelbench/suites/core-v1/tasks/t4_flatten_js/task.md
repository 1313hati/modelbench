Write `flattenObject(obj)` in JavaScript, exported CommonJS style:

```js
module.exports = { flatten: flattenObject };
```

It returns a new flat object whose keys are dot-separated paths to every leaf value.

Rules:
- Plain nested objects flatten with `.`: `{a:{b:1}}` -> `{"a.b":1}`.
- Arrays flatten with numeric indices: `{a:[{b:1},2]}` -> `{"a.0.b":1,"a.1":2}`.
- Empty objects and empty arrays produce no keys at all.
- `null` is a leaf value and is kept as-is.
- Keys are converted with `String(key)`.
- Throw a `TypeError` if `obj` is not a non-null, non-array object.
- Do not mutate the input.

Return the complete file. Node.js only, no third-party packages.
