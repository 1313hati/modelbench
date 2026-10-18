"use strict";

function mapRetry(items, limit, fn, options = {}) {
  if (!Array.isArray(items)) throw new TypeError("items must be an array");
  if (!Number.isInteger(limit) || limit < 1) throw new TypeError("limit must be an integer >= 1");
  if (typeof fn !== "function") throw new TypeError("fn must be a function");
  const retries = options.retries === undefined ? 0 : options.retries;
  if (!Number.isInteger(retries) || retries < 0) throw new TypeError("retries must be an integer >= 0");

  const n = items.length;
  const results = new Array(n);
  let next = 0;
  let failed = false;
  let done = 0;

  return new Promise((resolve, reject) => {
    if (n === 0) {
      resolve([]);
      return;
    }

    const finishItem = () => {
      done++;
      if (!failed && done === n) resolve(results);
    };

    const worker = async () => {
      while (!failed) {
        const index = next++;
        if (index >= n) return;
        let lastError;
        let ok = false;
        for (let attempt = 0; attempt <= retries; attempt++) {
          if (failed) return;
          try {
            results[index] = await fn(items[index], index);
            ok = true;
            break;
          } catch (err) {
            lastError = err;
          }
        }
        if (!ok) {
          if (!failed) {
            failed = true;
            reject(lastError);
          }
          return;
        }
        finishItem();
      }
    };

    const workers = Math.min(limit, n);
    for (let i = 0; i < workers; i++) worker();
  });
}

module.exports = { mapRetry };
