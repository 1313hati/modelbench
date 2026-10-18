const path = require("path");
const mod = require(path.resolve(process.argv[2]));
const mapLimit = mod.mapLimit;

const checks = [];
const check = (name, fn) => checks.push([name, fn]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

check("preserves order", async () => {
  const out = await mapLimit([3, 1, 2, 0], 2, async (n) => {
    await sleep(n * 5 + 1);
    return n * 10;
  });
  return JSON.stringify(out) === JSON.stringify([30, 10, 20, 0]);
});

check("respects limit", async () => {
  let active = 0;
  let peak = 0;
  await mapLimit([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 3, async () => {
    active += 1;
    peak = Math.max(peak, active);
    await sleep(6);
    active -= 1;
    return 1;
  });
  return peak === 3;
});

check("limit above length", async () => {
  let active = 0;
  let peak = 0;
  await mapLimit([1, 2], 5, async (n) => {
    active += 1;
    peak = Math.max(peak, active);
    await sleep(4);
    active -= 1;
    return n;
  });
  return peak === 2;
});

check("passes index", async () => {
  const out = await mapLimit(["a", "b"], 2, (v, i) => `${i}${v}`);
  return JSON.stringify(out) === JSON.stringify(["0a", "1b"]);
});

check("calls once per item", async () => {
  let calls = 0;
  const out = await mapLimit([1, 2, 3, 4], 2, async (n) => {
    calls += 1;
    return n;
  });
  return calls === 4 && out.length === 4;
});

check("empty resolves", async () => {
  const out = await mapLimit([], 2, () => 1);
  return Array.isArray(out) && out.length === 0;
});

check("rejects on error", async () => {
  try {
    await mapLimit([1, 2, 3], 2, async (n) => {
      if (n === 2) throw new Error("boom");
      return n;
    });
  } catch (e) {
    await sleep(30);
    return e && e.message === "boom";
  }
  return false;
});

check("bad limit throws TypeError", () => {
  for (const bad of [0, -1, 1.5, "2", null, undefined, NaN, true]) {
    try {
      mapLimit([1], bad, (x) => x);
      return false;
    } catch (e) {
      if (!(e instanceof TypeError)) return false;
    }
  }
  return true;
});

(async () => {
  let passed = 0;
  for (const [name, fn] of checks) {
    let ok = false;
    let label = name;
    try {
      ok = Boolean(await fn());
    } catch (e) {
      label = `${name} [raised ${e && e.message}]`;
    }
    console.log(`${ok ? "PASS" : "FAIL"} ${label}`);
    passed += ok ? 1 : 0;
  }
  console.log(`RESULT ${passed}/${checks.length}`);
})();
