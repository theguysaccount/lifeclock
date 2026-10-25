// LifeClock math: run with `node --test tests/js/*.test.mjs`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  YEAR_MS, parseDate, validate, lifeClock, remainingYears, secondsBetween, units, milestones, lastMilestone,
  buildHash, readHash, guessCountry, formatInt, WHO_AGES,
} from "../../site/assets/core.js";

const tables = {
  ssa: JSON.parse(readFileSync(new URL("../../data/ssa.json", import.meta.url))),
  who: JSON.parse(readFileSync(new URL("../../data/who.json", import.meta.url))),
};

test("dates", () => {
  assert.equal(parseDate("1990-06-15").getMonth(), 5);
  assert.equal(parseDate("1990-02-30"), null);
  assert.equal(parseDate("15/06/1990"), null);
  assert.equal(parseDate(""), null);
  const now = new Date(2026, 9, 25);
  assert.equal(validate({ birth: null, now }), "Enter your birthday.");
  assert.match(validate({ birth: new Date(2027, 0, 1), now }), /future/);
  assert.match(validate({ birth: new Date(1890, 0, 1), now }), /120 years/);
  assert.equal(validate({ birth: new Date(1990, 5, 15), now }), null);
});

test("the clock counts down to now + remaining years", () => {
  const now = new Date(2026, 9, 25, 12);
  const birth = new Date(1996, 9, 25, 12); // exactly 30 years minus leap-day drift
  const c = lifeClock(tables, { birth, sex: "female", country: "USA", now });
  assert.ok(Math.abs(c.age - 30) < 0.01);
  assert.ok(Math.abs(c.years - remainingYears(tables, { country: "USA", sex: "female", age: c.age })) < 1e-12);
  assert.equal(c.end.getTime(), now.getTime() + c.years * YEAR_MS);
  assert.equal(c.source.name, "U.S. Social Security Administration");
  assert.equal(lifeClock(tables, { birth, sex: "all", country: "JPN", now }).source.name, "World Health Organization");
  assert.equal(secondsBetween(now, new Date(now.getTime() + 5500)), 5);
  assert.equal(secondsBetween(new Date(now.getTime() + 5000), now), 0);
});

test("older ages reach further, and stay positive", () => {
  let prevEnd = 0;
  for (const age of [0, 20, 40, 60, 80, 90, 100, 110]) {
    const y = remainingYears(tables, { country: "WLD", sex: "all", age });
    assert.ok(y > 0);
    assert.ok(age + y > prevEnd - 1e-9, `end age rises: ${age}`);
    prevEnd = age + y;
  }
  assert.equal(WHO_AGES.length, tables.who.countries.WLD.all.length);
});

test("billion-second birthdays", () => {
  const birth = new Date(1990, 5, 15);
  const next = milestones(birth, new Date(2026, 9, 25), 2);
  assert.equal(next[0].seconds, 1.5e9);
  assert.equal(next[0].at.getTime(), birth.getTime() + 1.5e12);
  assert.equal(next[1].seconds, 2e9);
  assert.equal(lastMilestone(birth, new Date(2026, 9, 25)).seconds, 1e9);
  assert.equal(lastMilestone(new Date(2020, 0, 1), new Date(2026, 9, 25)), null);
});

test("desk-mode hash round-trips and rejects junk", () => {
  const s = { birth: new Date(1990, 5, 15), sex: "male", country: "JPN", mode: "up" };
  const h = buildHash(s);
  assert.equal(h, "#b=1990-06-15&s=male&c=JPN&m=up");
  const back = readHash(h, ["JPN", "USA"]);
  assert.equal(back.birth.getTime(), s.birth.getTime());
  assert.deepEqual([back.sex, back.country, back.mode], ["male", "JPN", "up"]);
  assert.equal(readHash("#b=1990-06-15&s=robot&c=JPN", ["JPN"]), null);
  assert.equal(readHash("#b=1990-06-15&s=male&c=XXX", ["JPN"]), null);
  assert.equal(readHash("", ["JPN"]), null);
});

test("country from the browser language", () => {
  const iso2 = { US: "USA", GB: "GBR", JP: "JPN" };
  assert.equal(guessCountry(["en-GB", "en"], iso2), "GBR");
  assert.equal(guessCountry(["ja", "ja-JP"], iso2), "JPN");
  assert.equal(guessCountry(["fr"], iso2), "WLD");
  assert.equal(guessCountry([], iso2), "WLD");
});

test("units and formatting", () => {
  const u = units(86400 * 365.2425);
  assert.ok(Math.abs(u.years - 1) < 1e-12);
  assert.ok(Math.abs(u.weekends - 52.177) < 0.001);
  assert.equal(formatInt(1453133934), "1,453,133,934");
});
