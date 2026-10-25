// LifeClock UI. The math lives in core.js; this file only touches the DOM. Nothing is stored:
// no cookies, no localStorage, and the desk-mode settings live after the "#" in the address.
import {
  parseDate, validate, lifeClock, secondsBetween, units, milestones, lastMilestone,
  buildHash, readHash, guessCountry, formatInt,
} from "./core.js";

const CFG = JSON.parse(document.getElementById("site-config").textContent);
const page = document.body.dataset.page;
let tablesPromise = null;
const loadTables = () => (tablesPromise ||= fetch(CFG.root + "data/tables.json").then((r) => {
  if (!r.ok) throw new Error("tables " + r.status);
  return r.json();
}));

function track(name, detail) {
  try {
    if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path: `event/${name}${detail ? "/" + detail : ""}`, title: name, event: true });
  } catch (e) { /* analytics must never break the clock */ }
}

const $ = (sel, el = document) => el.querySelector(sel);
const fmtDate = (d) => d.toLocaleDateString(undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
const fmtShort = (d) => d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
const round1 = (n) => (Math.round(n * 10) / 10).toLocaleString();
const SEX_WORDS = { female: "women", male: "men", all: "people" };

let timer = null;
function tick(fn) {
  clearInterval(timer);
  fn();
  // Align to the next whole second so the digits change on the beat.
  setTimeout(() => { fn(); timer = setInterval(fn, 1000); }, 1000 - (Date.now() % 1000));
}

function readForm(form) {
  const fd = new FormData(form);
  return { birth: parseDate(fd.get("birth")), sex: fd.get("sex") || "all", country: fd.get("country") || "WLD", mode: fd.get("mode") || "down" };
}

function fillCountries(select, tables) {
  if (select.options.length > 1) return;
  const names = Object.entries(tables.names).sort((a, b) => a[1].localeCompare(b[1]));
  select.innerHTML = `<option value="WLD">World average</option>` + names.map(([c, n]) => `<option value="${c}">${n}</option>`).join("");
  const fromQuery = new URLSearchParams(location.search).get("c");
  select.value = tables.names[fromQuery] ? fromQuery : guessCountry(navigator.languages || [navigator.language], tables.iso2);
}

// ---------- the share card (drawn in the browser, never uploaded) ----------
function drawCard(canvas, { big, label, small }) {
  const w = 1080, h = 1080;
  canvas.width = w;
  canvas.height = h;
  const g = canvas.getContext("2d");
  const grad = g.createLinearGradient(0, 0, w, h);
  grad.addColorStop(0, "#14161f");
  grad.addColorStop(1, "#2a2335");
  g.fillStyle = grad;
  g.fillRect(0, 0, w, h);
  g.fillStyle = "#f2b15b";
  g.font = "600 44px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
  g.fillText("◷ LifeClock", 80, 130);
  g.fillStyle = "#ffffff";
  let size = 150;
  g.font = `800 ${size}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`;
  while (g.measureText(big).width > w - 160 && size > 60) {
    size -= 6;
    g.font = `800 ${size}px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`;
  }
  g.fillText(big, 80, 520);
  g.fillStyle = "#e9e3f2";
  g.font = "500 52px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
  wrap(g, label, 80, 610, w - 160, 64);
  g.fillStyle = "#a99fb8";
  g.font = "400 34px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
  wrap(g, small, 80, 900, w - 160, 44);
  g.fillStyle = "#f2b15b";
  g.font = "600 34px system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
  g.fillText(CFG.siteUrl.replace(/^https?:\/\//, ""), 80, 1010);
}

function wrap(g, text, x, y, maxW, lh) {
  let line = "";
  for (const word of text.split(" ")) {
    const test = line ? line + " " + word : word;
    if (g.measureText(test).width > maxW && line) {
      g.fillText(line, x, y);
      line = word;
      y += lh;
    } else line = test;
  }
  if (line) g.fillText(line, x, y);
}

async function shareCard(box, card, text) {
  const canvas = box.querySelector("canvas") || box.appendChild(document.createElement("canvas"));
  drawCard(canvas, card);
  box.hidden = false;
  const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
  const file = new File([blob], "lifeclock.png", { type: "image/png" });
  const url = URL.createObjectURL(blob);
  const dl = box.querySelector("[data-download]");
  dl.href = url;
  const native = box.querySelector("[data-native]");
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    native.hidden = false;
    native.onclick = async () => {
      track("card_share", "native");
      try { await navigator.share({ files: [file], text: `${text} ${CFG.siteUrl}/` }); } catch (e) { /* cancelled */ }
    };
  }
  dl.onclick = () => track("card_share", "download");
  box.querySelector("[data-copy]").onclick = async (ev) => {
    track("card_share", "copy");
    try {
      await navigator.clipboard.writeText(`${text} ${CFG.siteUrl}/`);
      ev.target.textContent = "Copied";
    } catch (e) { window.prompt("Copy this:", `${text} ${CFG.siteUrl}/`); }
  };
  box.dataset.ready = String(blob.size);
}

// ---------- the main clock (home page and desk mode) ----------
function renderClock(root, tables, state, { desk = false } = {}) {
  const now = new Date();
  const clock = lifeClock(tables, { ...state, now });
  const where = state.country === "WLD" ? "worldwide" : `in ${tables.inNames[state.country] || tables.names[state.country]}`;
  const basis = `Average for ${SEX_WORDS[state.sex]} aged ${Math.floor(clock.age)} ${where} (${clock.source.name}, ${clock.source.year}). It's an average across millions of people, not a prediction for you; many live well past it.`;
  const counter = $("[data-counter]", root);
  const label = $("[data-label]", root);
  const sub = $("[data-sub]", root);
  $("[data-basis]", root).textContent = basis;
  root.dataset.mode = state.mode;
  const update = () => {
    const t = new Date();
    if (state.mode === "down") {
      const s = secondsBetween(t, clock.end);
      counter.textContent = formatInt(s);
      counter.dataset.value = String(s);
      label.textContent = "seconds ahead of you, on average";
    } else {
      const s = secondsBetween(state.birth, t);
      counter.textContent = formatInt(s);
      counter.dataset.value = String(s);
      label.textContent = "seconds you've lived so far";
    }
  };
  tick(update);
  const secs = state.mode === "down" ? secondsBetween(now, clock.end) : secondsBetween(state.birth, now);
  const u = units(secs);
  if (sub) sub.textContent = state.mode === "down"
    ? `About ${round1(u.years)} years: roughly ${formatInt(u.sunrises)} sunrises, ${formatInt(u.weekends)} weekends and ${formatInt(u.fullMoons)} full moons.`
    : `That's ${formatInt(u.sunrises)} sunrises and ${formatInt(u.fullMoons)} full moons so far.`;
  const next = milestones(state.birth, now, 1)[0];
  const ms = $("[data-milestone]", root);
  if (ms) ms.innerHTML = next ? `Your next billion-second birthday: <b>${formatInt(next.seconds)} seconds old</b> on ${fmtDate(next.at)}.` : "";
  const deskLink = $("[data-desk]", root);
  if (deskLink) deskLink.href = CFG.root + "desk/" + buildHash(state);
  const toggle = $("[data-toggle]", root);
  if (toggle) toggle.textContent = state.mode === "down" ? "Show time lived instead" : "Show time ahead instead";
  return { clock, secs };
}

function cardFor(state, secs) {
  const asOf = `As of ${fmtShort(new Date())}. An average from public life tables, not a prediction.`;
  return state.mode === "down"
    ? { big: formatInt(secs), label: "seconds ahead of me, on average. I'm spending today on what matters.", small: asOf, text: `I have about ${formatInt(secs)} seconds ahead of me, on average. How many do you have?` }
    : { big: formatInt(secs), label: "seconds lived so far, and counting.", small: `As of ${fmtShort(new Date())}.`, text: `I've lived ${formatInt(secs)} seconds so far. How many have you?` };
}

async function initHome() {
  const form = $("#clock-form");
  const result = $("#result");
  const err = $("[data-error]", form);
  const tables = await loadTables().catch(() => null);
  if (!tables) {
    err.textContent = "The life tables couldn't load. Check your connection and reload.";
    err.hidden = false;
    return;
  }
  fillCountries(form.elements.country, tables);
  let state = null;
  let current = null;
  const show = () => {
    current = renderClock(result, tables, state);
    result.hidden = false;
  };
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const s = readForm(form);
    const msg = validate({ birth: s.birth, now: new Date() });
    err.textContent = msg || "";
    err.hidden = !msg;
    if (msg) return;
    state = s;
    show();
    result.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    $("[data-counter]", result).focus({ preventScroll: true });
    track("clock_start", `${state.mode}-${state.country}`);
  });
  $("[data-toggle]", result).addEventListener("click", () => {
    state = { ...state, mode: state.mode === "down" ? "up" : "down" };
    form.elements.mode.value = state.mode;
    show();
    track("mode_toggle", state.mode);
  });
  $("[data-edit]", result).addEventListener("click", () => {
    clearInterval(timer);
    result.hidden = true;
    form.scrollIntoView({ block: "start" });
    form.elements.birth.focus();
  });
  $("[data-card]", result).addEventListener("click", () => {
    const now = new Date();
    const s = state.mode === "down" ? secondsBetween(now, current.clock.end) : secondsBetween(state.birth, now);
    const card = cardFor(state, s);
    shareCard($("[data-cardbox]", result), card, card.text);
    track("card_open", state.mode);
  });
  $("[data-desk]", result).addEventListener("click", () => track("desk_open"));
}

async function initDesk() {
  const tables = await loadTables();
  const codes = Object.keys(tables.names).concat("WLD");
  const form = $("#clock-form");
  const desk = $("#desk");
  fillCountries(form.elements.country, tables);
  const start = () => {
    const state = readHash(location.hash, codes);
    if (!state) {
      form.hidden = false;
      desk.hidden = true;
      return;
    }
    form.hidden = true;
    desk.hidden = false;
    document.body.classList.add("desk-on");
    renderClock(desk, tables, state, { desk: true });
    $("[data-toggle]", desk).onclick = () => {
      location.hash = buildHash({ ...state, mode: state.mode === "down" ? "up" : "down" });
    };
  };
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const s = readForm(form);
    const msg = validate({ birth: s.birth, now: new Date() });
    const err = $("[data-error]", form);
    err.textContent = msg || "";
    err.hidden = !msg;
    if (!msg) location.hash = buildHash(s);
  });
  window.addEventListener("hashchange", start);
  $("[data-fullscreen]").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.().catch(() => {});
  });
  const wake = $("[data-wake]");
  let lock = null;
  if (!("wakeLock" in navigator)) wake.hidden = true;
  wake.addEventListener("click", async () => {
    try {
      if (lock) { await lock.release(); lock = null; wake.textContent = "Keep screen on"; return; }
      lock = await navigator.wakeLock.request("screen");
      wake.textContent = "Screen stays on ✓";
      lock.addEventListener("release", () => { lock = null; wake.textContent = "Keep screen on"; });
    } catch (e) { wake.textContent = "Screen lock not available"; }
  });
  start();
}

function initBillion() {
  const form = $("#billion-form");
  const result = $("#result");
  const err = $("[data-error]", form);
  let birth = null;
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    birth = parseDate(new FormData(form).get("birth"));
    const msg = validate({ birth, now: new Date() });
    err.textContent = msg || "";
    err.hidden = !msg;
    if (msg) return;
    const now = new Date();
    const next = milestones(birth, now, 4);
    const last = lastMilestone(birth, now);
    const counter = $("[data-counter]", result);
    tick(() => {
      const s = secondsBetween(birth, new Date());
      counter.textContent = formatInt(s);
      counter.dataset.value = String(s);
    });
    $("[data-next]", result).innerHTML = next.length
      ? `You turn <b>${formatInt(next[0].seconds)} seconds old</b> on <b>${fmtDate(next[0].at)}</b>, around ${next[0].at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })} if you were born at midnight.`
      : "You've passed every billion-second birthday on our list. Remarkable.";
    $("[data-list]", result).innerHTML =
      (last ? `<li><b>${formatInt(last.seconds)}</b> seconds: ${fmtDate(last.at)} (already passed)</li>` : "") +
      next.map((m) => `<li><b>${formatInt(m.seconds)}</b> seconds: ${fmtDate(m.at)}</li>`).join("");
    result.hidden = false;
    result.dataset.next = next.length ? next[0].at.toISOString() : "";
    track("billion_start");
  });
  $("[data-card]", result).addEventListener("click", () => {
    const now = new Date();
    const next = milestones(birth, now, 1)[0];
    const s = secondsBetween(birth, now);
    const card = next
      ? { big: formatInt(s), label: `seconds old. I'll be ${formatInt(next.seconds)} seconds old on ${fmtShort(next.at)}.`, small: "Billion-second birthdays, by LifeClock.", text: `I turn ${formatInt(next.seconds)} seconds old on ${fmtShort(next.at)}. When's yours?` }
      : { big: formatInt(s), label: "seconds old, and counting.", small: "Billion-second birthdays, by LifeClock.", text: `I'm ${formatInt(s)} seconds old. How old are you in seconds?` };
    shareCard($("[data-cardbox]", result), card, card.text);
    track("card_open", "billion");
  });
}

window.addEventListener("error", (ev) => { document.body.dataset.error = ev.message; });
window.addEventListener("unhandledrejection", (ev) => { document.body.dataset.error = String(ev.reason && ev.reason.message || ev.reason); });
const init = { home: initHome, desk: initDesk, billion: initBillion }[page];
const ready = init ? Promise.resolve(init()).catch((e) => { document.body.dataset.error = e.message; }) : Promise.resolve();

// Screenshot helper: ?demo=1 fills in a sample birthday and starts the clock; ?demo=card also draws the card.
const demo = new URLSearchParams(location.search).get("demo");
if (demo) {
  ready.then(async () => {
    const form = document.querySelector("#clock-form, #billion-form");
    if (!form) return;
    form.elements.birth.value = "1990-06-15";
    if (form.elements.sex) form.querySelector('input[name="sex"][value="female"]').checked = true;
    if (form.elements.country) {
      while (form.elements.country.options.length < 2) await new Promise((r) => setTimeout(r, 20));
      form.elements.country.value = "USA";
    }
    form.requestSubmit();
    if (demo === "card") setTimeout(() => document.querySelector("[data-card]").click(), 50);
    setTimeout(() => window.scrollTo(0, 0), 300);
  });
}

if (/[?&]selftest=1\b/.test(location.search)) {
  ready.then(() => import("./selftest.js")).then((m) => m.run(page)).catch((e) => { document.body.dataset.selftest = "fail: " + e.message; });
}
