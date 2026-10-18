Write `mapRetry(items, limit, fn, options)` in Node.js (CommonJS:
`module.exports = { mapRetry }`).

It runs `fn(item, index)` for every item with at most `limit` calls in flight at
any moment (retries count toward the limit), and resolves to an array of results
in the same order as `items`.

- `fn` may return a value or a promise; a synchronous throw counts as a rejection.
- `options.retries` is the number of **additional** attempts after the first
  (default 0). Retry immediately, with no delay.
- If an item still fails, the returned promise rejects with that item's last
  error. Once a failure is known, no new items may be started; attempts already
  in flight may finish.
- Validate arguments synchronously by throwing `TypeError`: `items` must be an
  array, `limit` an integer >= 1, `retries` an integer >= 0, `fn` a function.
  (Do not return a rejected promise for bad arguments.)
- `mapRetry([], 3, fn)` resolves to `[]` without calling `fn`.
- Do not mutate `items`. Never leak an unhandled rejection.

Return the complete file. No third-party packages.
