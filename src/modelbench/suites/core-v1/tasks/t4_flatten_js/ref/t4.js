function walk(value, path, out) {
  if (Array.isArray(value)) {
    if (value.length === 0) return;
    value.forEach((item, index) => walk(item, `${path}.${index}`, out));
    return;
  }
  if (value !== null && typeof value === "object") {
    const keys = Object.keys(value);
    if (keys.length === 0) return;
    for (const key of keys) walk(value[key], `${path}.${key}`, out);
    return;
  }
  out[path] = value;
}

function flatten(obj) {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) {
    throw new TypeError("flatten expects a plain object");
  }
  const out = {};
  for (const key of Object.keys(obj)) walk(obj[key], String(key), out);
  return out;
}

module.exports = { flatten };
