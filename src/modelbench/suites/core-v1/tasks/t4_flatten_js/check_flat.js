const path = require("path");
const mod = require(path.resolve(process.argv[2]));
const flatten = mod.flatten || mod.flattenObject;

const norm = (o) => JSON.stringify(Object.fromEntries(Object.entries(o).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))));

const checks = [];
const check = (name, fn) => checks.push([name, fn]);

check("nested objects", () => norm(flatten({ a: { b: 1 } })) === norm({ "a.b": 1 }));
check("deep chain", () => norm(flatten({ a: { b: { c: 2 } } })) === norm({ "a.b.c": 2 }));
check("array indices", () => norm(flatten({ a: [{ b: 1 }, 2] })) === norm({ "a.0.b": 1, "a.1": 2 }));
check("mixed", () => norm(flatten({ a: { b: [1, { c: 2 }] }, d: 3 })) === norm({ "a.b.0": 1, "a.b.1.c": 2, d: 3 }));
check("empty containers", () => norm(flatten({ a: {}, b: [], c: 1 })) === norm({ c: 1 }));
check("null leaf", () => norm(flatten({ a: null })) === norm({ a: null }));
check("numeric keys", () => norm(flatten({ 1: { 2: "x" } })) === norm({ "1.2": "x" }));
check("no mutation", () => {
  const src = { a: { b: [1] } };
  const before = JSON.stringify(src);
  flatten(src);
  return JSON.stringify(src) === before;
});
check("rejects arrays", () => {
  try { flatten([1, 2]); } catch (e) { return e instanceof TypeError; }
  return false;
});
check("rejects null", () => {
  try { flatten(null); } catch (e) { return e instanceof TypeError; }
  return false;
});
check("rejects primitives", () => {
  for (const v of [1, "s", true, undefined]) {
    try { flatten(v); return false; } catch (e) { if (!(e instanceof TypeError)) return false; }
  }
  return true;
});

let passed = 0;
for (const [name, fn] of checks) {
  let ok = false;
  let label = name;
  try { ok = Boolean(fn()); } catch (e) { label = `${name} [raised ${e && e.message}]`; }
  console.log(`${ok ? "PASS" : "FAIL"} ${label}`);
  passed += ok ? 1 : 0;
}
console.log(`RESULT ${passed}/${checks.length}`);
