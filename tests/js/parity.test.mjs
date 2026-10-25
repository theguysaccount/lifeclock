// The browser model (core.js) must match the independent Python model (pipeline/reference.py).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { remainingYears } from "../../site/assets/core.js";

const root = new URL("../../", import.meta.url);
const tables = {
  ssa: JSON.parse(readFileSync(new URL("data/ssa.json", root))),
  who: JSON.parse(readFileSync(new URL("data/who.json", root))),
};
const py = JSON.parse(execFileSync("python3", ["pipeline/reference.py", "grid"], { cwd: root, encoding: "utf8" }));

test("python and js give the same remaining years", () => {
  assert.ok(Object.keys(py).length > 200);
  for (const [key, want] of Object.entries(py)) {
    const [country, sex, age] = key.split("|");
    const got = remainingYears(tables, { country, sex, age: Number(age) });
    assert.ok(Math.abs(got - want) < 1e-9, `${key}: js ${got}, python ${want}`);
  }
});
