Write `mapLimit(items, limit, fn)` in JavaScript, exported CommonJS style:

```js
module.exports = { mapLimit };
```

It maps `fn` over `items` with at most `limit` calls in flight and returns a Promise.

Rules:
- Resolves with an array of results in the same order as `items`, regardless of completion order.
- `fn(item, index)` may return a value or a Promise.
- Never run more than `limit` invocations at the same time.
- The first rejection rejects the returned Promise with that error; it must not be swallowed or
  produce unhandled rejections. Already running calls may finish.
- `limit` must be an integer >= 1, otherwise throw a `TypeError` synchronously.
- An empty `items` array resolves to `[]`.

Return the complete file. Node.js only, no third-party packages.
