// LifeClock math, shared by the browser (app.js) and the Node tests. No DOM access in this file.
// pipeline/reference.py implements the same model independently; tests/js/parity.test.mjs compares them.

export const YEAR_MS = 365.2425 * 86400000;
export const WHO_AGES = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85];

// Interpolate y over sorted knots x at point t (clamped to the ends).
function interp(xs, ys, t) {
  if (t <= xs[0]) return ys[0];
  const last = xs.length - 1;
  if (t >= xs[last]) return ys[last];
  let i = 1;
  while (xs[i] < t) i++;
  const f = (t - xs[i - 1]) / (xs[i] - xs[i - 1]);
  return ys[i - 1] + f * (ys[i] - ys[i - 1]);
}

const SSA_AGES = Array.from({ length: 120 }, (_, i) => i);

// SSA single-year table: remaining years at exact age. "all" averages the male and female tables.
export function ssaRemaining(ssa, sex, age) {
  if (sex === "all") return (ssaRemaining(ssa, "female", age) + ssaRemaining(ssa, "male", age)) / 2;
  const ex = sex === "female" ? ssa.female_ex : ssa.male_ex;
  if (age > 119) return Math.max(ex[119] - (age - 119) * 0.05, 0.25);
  return interp(SSA_AGES, ex, age);
}

// WHO table: remaining years at the start of each age group; past 85 the SSA curve's shape carries
// the WHO value at 85 forward (WHO publishes only one "85 and over" figure).
export function whoRemaining(row, ssa, sex, age) {
  const ex = row[sex];
  if (age <= 85) return interp(WHO_AGES, ex, age);
  return ex[ex.length - 1] * (ssaRemaining(ssa, sex, age) / ssaRemaining(ssa, sex, 85));
}

export function remainingYears(tables, { country, sex, age }) {
  if (country === "USA" && tables.ssa) return ssaRemaining(tables.ssa, sex, age);
  const row = tables.who.countries[country] || tables.who.countries.WLD;
  return whoRemaining(row, tables.ssa, sex, age);
}

export function sourceFor(tables, country) {
  if (country === "USA" && tables.ssa) return { name: "U.S. Social Security Administration", year: tables.ssa.table_year };
  return { name: "World Health Organization", year: tables.who.year };
}

// Parse "YYYY-MM-DD" as local midnight; null if invalid.
export function parseDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.getFullYear() === Number(m[1]) && d.getMonth() === Number(m[2]) - 1 && d.getDate() === Number(m[3]) ? d : null;
}

export function validate({ birth, now }) {
  if (!birth) return "Enter your birthday.";
  if (birth > now) return "That birthday is in the future.";
  if ((now - birth) / YEAR_MS > 120) return "Enter a birthday within the last 120 years.";
  return null;
}

// The clock: the average end date is fixed when you start it, then each second counts down to it.
export function lifeClock(tables, { birth, sex, country, now }) {
  const age = (now - birth) / YEAR_MS;
  const years = remainingYears(tables, { country, sex, age });
  const end = new Date(now.getTime() + years * YEAR_MS);
  return { age, years, end, source: sourceFor(tables, country) };
}

export function secondsBetween(a, b) {
  return Math.max(0, Math.floor((b - a) / 1000));
}

// Everyday units for a span of seconds.
export function units(seconds) {
  const days = seconds / 86400;
  return {
    years: days / 365.2425,
    days,
    weekends: days / 7,
    fullMoons: days / 29.530589,
    sunrises: days,
  };
}

// Billion-second birthdays: the next few, as dates.
export function milestones(birth, now, count = 3) {
  const out = [];
  for (let n = 1; out.length < count && n <= 4; n += 0.5) {
    const at = new Date(birth.getTime() + n * 1e9 * 1000);
    if (at > now) out.push({ seconds: n * 1e9, at });
  }
  return out;
}

export function lastMilestone(birth, now) {
  let best = null;
  for (let n = 0.5; n <= 4; n += 0.5) {
    const at = new Date(birth.getTime() + n * 1e9 * 1000);
    if (at <= now) best = { seconds: n * 1e9, at };
  }
  return best;
}

// Desk mode keeps its settings after the "#", which browsers never send to a server.
export function buildHash({ birth, sex, country, mode }) {
  const p = new URLSearchParams();
  p.set("b", `${birth.getFullYear()}-${String(birth.getMonth() + 1).padStart(2, "0")}-${String(birth.getDate()).padStart(2, "0")}`);
  p.set("s", sex);
  p.set("c", country);
  p.set("m", mode);
  return "#" + p.toString();
}

export function readHash(hash, countries) {
  const p = new URLSearchParams(String(hash || "").replace(/^#/, ""));
  const birth = parseDate(p.get("b"));
  const sex = ["female", "male", "all"].includes(p.get("s")) ? p.get("s") : null;
  const country = countries.includes(p.get("c")) ? p.get("c") : null;
  const mode = p.get("m") === "up" ? "up" : "down";
  return birth && sex && country ? { birth, sex, country, mode } : null;
}

// Country from the browser's language tag ("en-GB" -> "GB" -> "GBR"), else the world average.
export function guessCountry(languages, iso2to3) {
  for (const tag of languages || []) {
    const m = /-([A-Za-z]{2})\b/.exec(tag);
    if (m && iso2to3[m[1].toUpperCase()]) return iso2to3[m[1].toUpperCase()];
  }
  return "WLD";
}

export function formatInt(n, locale) {
  return Math.round(n).toLocaleString(locale || "en-US");
}
