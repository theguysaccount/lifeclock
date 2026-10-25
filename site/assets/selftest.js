// End-to-end self-test, loaded only with ?selftest=1. It drives the real page and checks the
// numbers against the life tables independently of core.js. scripts/e2e.sh reads the result from
// <body data-selftest="pass|fail: ...">.
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const YEAR_S = 365.2425 * 86400;

async function until(fn, what, ms = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const v = fn();
    if (v) return v;
    await wait(25);
  }
  throw new Error("timed out waiting for " + what);
}

const value = (root = document) => Number(root.querySelector("[data-counter]").dataset.value);
const lerp = (xs, ys, t) => {
  let i = 1;
  while (i < xs.length - 1 && xs[i] < t) i++;
  return ys[i - 1] + ((t - xs[i - 1]) / (xs[i] - xs[i - 1])) * (ys[i] - ys[i - 1]);
};

async function tables() {
  const cfg = JSON.parse(document.getElementById("site-config").textContent);
  return fetch(cfg.root + "data/tables.json").then((r) => r.json());
}

async function home(log) {
  const form = document.querySelector("#clock-form");
  await until(() => form.elements.country.options.length > 100, "country list");
  form.elements.birth.value = "1990-06-15";
  form.querySelector('input[name="sex"][value="female"]').checked = true;
  form.elements.country.value = "USA";
  form.querySelector('input[name="mode"][value="down"]').checked = true;
  form.requestSubmit();
  await until(() => !document.querySelector("#result").hidden && value(), "the clock");
  const t = await tables();
  const birth = new Date(1990, 5, 15).getTime();
  const age = (Date.now() - birth) / 1000 / YEAR_S;
  const ex = t.ssa.female_ex;
  const expected = (ex[Math.floor(age)] + (age - Math.floor(age)) * (ex[Math.floor(age) + 1] - ex[Math.floor(age)])) * YEAR_S;
  const shown = value();
  log.push(`US woman born 1990-06-15: ${shown} s shown, ${Math.round(expected)} expected`);
  if (Math.abs(shown - expected) > 5) throw new Error(`countdown ${shown}, expected about ${Math.round(expected)}`);
  await wait(1600);
  const later = value();
  if (!(later < shown && shown - later <= 3)) throw new Error(`not counting down: ${shown} then ${later}`);
  if (!/Social Security/.test(document.querySelector("[data-basis]").textContent)) throw new Error("basis doesn't name SSA");
  document.querySelector("[data-toggle]").click();
  await wait(50);
  const lived = value();
  if (Math.abs(lived - (Date.now() - birth) / 1000) > 3) throw new Error(`time lived ${lived}`);
  await wait(1600);
  if (!(value() > lived)) throw new Error("not counting up");
  const desk = document.querySelector("[data-desk]").getAttribute("href");
  if (!desk.endsWith("#b=1990-06-15&s=female&c=USA&m=up")) throw new Error("desk link " + desk);
  document.querySelector("[data-card]").click();
  const size = Number(await until(() => document.querySelector("[data-cardbox]").dataset.ready, "share card"));
  if (size < 10000) throw new Error("share card too small: " + size);
  log.push(`count up ok, desk link ok, card ${size} bytes`);
}

async function desk(log) {
  const box = document.querySelector("#desk");
  await until(() => !box.hidden && value(box), "desk clock");
  const t = await tables();
  // The e2e script opens #b=1990-06-15&s=male&c=JPN&m=down.
  const age = (Date.now() - new Date(1990, 5, 15).getTime()) / 1000 / YEAR_S;
  const expected = lerp(t.whoAges, t.who.countries.JPN.male, age) * YEAR_S;
  const shown = value(box);
  log.push(`Japanese man born 1990-06-15: ${shown} s shown, ${Math.round(expected)} expected`);
  if (Math.abs(shown - expected) > 5) throw new Error(`desk countdown ${shown}, expected about ${Math.round(expected)}`);
  if (!/World Health Organization/.test(box.querySelector("[data-basis]").textContent)) throw new Error("basis doesn't name WHO");
}

async function billion(log) {
  const form = document.querySelector("#billion-form");
  form.elements.birth.value = "1990-06-15";
  form.requestSubmit();
  const result = document.querySelector("#result");
  await until(() => !result.hidden && result.dataset.next, "milestones");
  const want = new Date(new Date(1990, 5, 15).getTime() + 1.5e12).toISOString();
  if (result.dataset.next !== want) throw new Error(`next milestone ${result.dataset.next}, expected ${want}`);
  if (Math.abs(value(result) - (Date.now() - new Date(1990, 5, 15).getTime()) / 1000) > 3) throw new Error("seconds lived");
  log.push(`next milestone ${want}`);
}

export async function run(page) {
  const log = [];
  try {
    if (page === "home") await home(log);
    else if (page === "desk") await desk(log);
    else if (page === "billion") await billion(log);
    if (document.body.dataset.error) throw new Error("page error: " + document.body.dataset.error);
    for (const el of document.querySelectorAll("button:not([hidden])")) {
      if (el.offsetParent && !el.textContent.trim()) throw new Error("a visible button has no label");
    }
    document.body.dataset.selftest = "pass";
  } catch (e) {
    document.body.dataset.selftest = "fail: " + e.message;
  }
  const pre = document.createElement("pre");
  pre.id = "selftest";
  pre.textContent = document.body.dataset.selftest + "\n" + log.join("\n");
  document.body.appendChild(pre);
}
