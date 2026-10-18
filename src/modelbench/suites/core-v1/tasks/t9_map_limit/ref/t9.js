function mapLimit(items, limit, fn) {
  if (typeof limit !== "number" || !Number.isInteger(limit) || limit < 1) {
    throw new TypeError("limit must be an integer >= 1");
  }

  return new Promise((resolve, reject) => {
    const results = new Array(items.length);
    let next = 0;
    let active = 0;
    let done = 0;
    let failed = false;

    if (items.length === 0) {
      resolve(results);
      return;
    }

    const launch = () => {
      while (!failed && active < limit && next < items.length) {
        const index = next;
        next += 1;
        active += 1;
        Promise.resolve()
          .then(() => fn(items[index], index))
          .then(
            (value) => {
              results[index] = value;
              active -= 1;
              done += 1;
              if (done === items.length) resolve(results);
              else launch();
            },
            (error) => {
              if (failed) return;
              failed = true;
              active -= 1;
              reject(error);
            }
          );
      }
    };

    launch();
  });
}

module.exports = { mapLimit };
