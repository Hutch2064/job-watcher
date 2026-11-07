import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
if (!globalThis.navigator)
  Object.defineProperty(globalThis, "navigator", {
    value: {},
    configurable: true,
  });
const source = await readFile(new URL("../common.js", import.meta.url), "utf8");
const common = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64")
);
assert.deepEqual(
  common.parseCSV('title,location\n"Analyst, Portfolio","New York, NY"\n'),
  [{ title: "Analyst, Portfolio", location: "New York, NY" }],
);
assert.equal(
  common.normalizeLocation("New York, New York, United States"),
  "New York, NY",
);
assert.equal(common.dayDiff("2026-11-01", "2026-11-07"), 6);
assert.equal(common.relativeDate("2026-11-06", "2026-11-07"), "1 day ago");
assert.match(
  common.job(
    {
      title: "<script>",
      url: "https://example.com",
      employer: "A",
      location: "",
      first_seen: "2026-11-07",
      posting_id: "a",
      experience: "early",
    },
    new Set(),
    "2026-11-07",
  ),
  /&lt;script&gt;/,
);
console.log("Frontend helper tests passed.");
