const assert = require("assert");
const path = process.argv[2];

let mapRetry;
try {
  ({ mapRetry } = require(path));
} catch (err) {
  console.log(`FAIL load module: ${err && err.message}`);
  console.log("RESULT 0/1");
  process.exit(0);
}

const checks = [];
function check(name, fn) {
  checks.push({ name, fn });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

check("empty resolves [] without calls", async () => {
  let calls = 0;
  const out = await mapRetry([], 3, () => { calls++; });
  assert.deepStrictEqual(out, []);
  assert.strictEqual(calls, 0);
});

check("preserves order", async () => {
  const items = [3, 1, 2, 0];
  const out = await mapRetry(items, 2, async (x) => {
    await sleep(x * 5);
    return x * 10;
  });
  assert.deepStrictEqual(out, [30, 10, 20, 0]);
});

check("calls fn with item and index", async () => {
  const seen = [];
  await mapRetry(["a", "b", "c"], 2, (item, index) => {
    seen.push([item, index]);
    return item;
  });
  assert.deepStrictEqual(seen, [["a", 0], ["b", 1], ["c", 2]]);
});

check("retries then succeeds", async () => {
  let calls = 0;
  const out = await mapRetry([7], 1, async () => {
    calls++;
    if (calls < 3) throw new Error("boom" + calls);
    return "ok";
  }, { retries: 2 });
  assert.deepStrictEqual(out, ["ok"]);
  assert.strictEqual(calls, 3);
});

check("exhausted retries rejects with last error", async () => {
  let calls = 0;
  let caught = null;
  try {
    await mapRetry([1], 1, async () => {
      calls++;
      throw new Error("err" + calls);
    }, { retries: 2 });
  } catch (err) {
    caught = err;
  }
  assert(caught instanceof Error);
  assert.strictEqual(caught.message, "err3");
  assert.strictEqual(calls, 3);
});

check("synchronous throw is retried", async () => {
  let calls = 0;
  const out = await mapRetry([1], 1, () => {
    calls++;
    if (calls === 1) throw new Error("sync");
    return 5;
  }, { retries: 1 });
  assert.deepStrictEqual(out, [5]);
  assert.strictEqual(calls, 2);
});

check("respects concurrency limit", async () => {
  let active = 0;
  let max = 0;
  const resolvers = [];
  const p = mapRetry([0, 1, 2, 3, 4, 5], 2, () => {
    active++;
    max = Math.max(max, active);
    return new Promise((resolve) => {
      resolvers.push(() => { active--; resolve(active); });
    });
  });
  await sleep(20);
  assert.strictEqual(max, 2, `max was ${max}`);
  assert.strictEqual(active, 2);
  while (resolvers.length) {
    resolvers.shift()();
    await sleep(10);
  }
  const out = await p;
  assert.strictEqual(out.length, 6);
  assert(max <= 2, `max was ${max}`);
});

check("retries count toward concurrency", async () => {
  let active = 0;
  let max = 0;
  const fn = async (x) => {
    active++;
    max = Math.max(max, active);
    await sleep(5);
    active--;
    if (x === 0) throw new Error("always");
    return x;
  };
  let failed = false;
  try {
    await mapRetry([0, 1, 2, 3], 2, fn, { retries: 3 });
  } catch {
    failed = true;
  }
  assert(failed);
  assert(max <= 2, `max was ${max}`);
});

check("fail-fast stops starting new items", async () => {
  const called = [];
  let caught = null;
  try {
    await mapRetry([0, 1, 2, 3, 4], 1, async (x) => {
      called.push(x);
      if (x === 1) throw new Error("stop");
      return x;
    });
  } catch (err) {
    caught = err;
  }
  assert(caught && caught.message === "stop");
  assert.deepStrictEqual(called, [0, 1], `called ${called}`);
});

check("invalid arguments throw synchronously", async () => {
  const bad = [
    () => mapRetry("nope", 1, () => 1),
    () => mapRetry([], 0, () => 1),
    () => mapRetry([], 1.5, () => 1),
    () => mapRetry([], 1, null),
    () => mapRetry([], 1, () => 1, { retries: -1 }),
    () => mapRetry([], 1, () => 1, { retries: 1.5 }),
  ];
  for (const fn of bad) {
    let threw = false;
    try { fn(); } catch (err) { threw = err instanceof TypeError; }
    assert(threw, `did not throw TypeError: ${fn}`);
  }
});

check("does not mutate items", async () => {
  const items = [1, 2, 3];
  await mapRetry(items, 2, (x) => x);
  assert.deepStrictEqual(items, [1, 2, 3]);
});

check("successful results are exact", async () => {
  const out = await mapRetry([1, 2, 3, 4], 4, async (x) => ({ v: x }), { retries: 2 });
  assert.deepStrictEqual(out, [{ v: 1 }, { v: 2 }, { v: 3 }, { v: 4 }]);
});

(async () => {
  let passed = 0;
  for (const { name, fn } of checks) {
    try {
      await fn();
      passed++;
    } catch (err) {
      console.log(`FAIL ${name}: ${err && err.stack ? err.stack.split("\n")[0] : err}`);
    }
  }
  console.log(`RESULT ${passed}/${checks.length}`);
  process.exit(0);
})();
