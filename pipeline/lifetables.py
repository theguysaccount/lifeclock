"""Refresh the life tables LifeClock is built on.

    python3 pipeline/lifetables.py refresh   # fetch WHO (and try SSA), validate, write data/ when changed
    python3 pipeline/lifetables.py check     # validate the committed tables

Sources:
- WHO Global Health Observatory, indicator LIFE_0000000035 ("ex: expectation of life at age x"),
  every country, both sexes and each sex, 19 age groups, newest year available. Open API, no key.
- SSA Office of the Chief Actuary, Actuarial Life Table (single years of age 0-119, by sex), used
  for the United States. ssa.gov answers scripts from many networks with 403; when it does, the
  committed table stays (it changes once a year with the Trustees Report).

Fails safe: a table that can't be fetched or fails validation is never written. Exit status is 1
only when the WHO tables have gone too long without a successful refresh (WHO_STALE_AFTER_DAYS
below), so a long outage shows up in Actions and a passing one doesn't.
"""
import datetime as dt
import html
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "LifeClockBot/1.0 (+https://github.com/theguysaccount/lifeclock)"
GHO = "https://ghoapi.azureedge.net/api"
SSA_URL = "https://www.ssa.gov/oact/STATS/table4c6.html"
AGES = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]
GROUPS = ["00-01", "01-04", "05-09", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49",
          "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80-84", "85PLUS"]
SEXES = {"SEX_BTSX": "all", "SEX_FMLE": "female", "SEX_MLE": "male"}


def get(url, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(15 * (attempt + 1))


def gho(query):
    return json.loads(get(f"{GHO}/{query.replace(' ', '%20')}"))["value"]


def latest_who_year():
    rows = gho("LIFE_0000000035?$filter=SpatialDim eq 'USA' and Dim1 eq 'SEX_BTSX' and Dim2 eq 'AGEGROUP_YEARS85PLUS'")
    return max(r["TimeDim"] for r in rows)


def parse_who(rows, year):
    """GHO rows -> {code: {"all"|"female"|"male": [ex at AGES]}}; GLOBAL becomes "WLD"."""
    out = {}
    for r in rows:
        if r.get("TimeDim") != year or r.get("NumericValue") is None:
            continue
        if r["SpatialDimType"] == "COUNTRY":
            code = r["SpatialDim"]
        elif r["SpatialDim"] == "GLOBAL":
            code = "WLD"
        else:
            continue
        sex = SEXES.get(r["Dim1"])
        group = r["Dim2"].replace("AGEGROUP_YEARS", "")
        if sex is None or group not in GROUPS:
            continue
        out.setdefault(code, {}).setdefault(sex, [None] * len(GROUPS))[GROUPS.index(group)] = round(r["NumericValue"], 3)
    return {c: s for c, s in out.items() if all(len(v) == 19 and None not in v for v in s.values()) and len(s) == 3}


def fetch_who():
    year = latest_who_year()
    rows = gho(f"LIFE_0000000035?$filter=TimeDim eq {year}")
    return {"source": "World Health Organization, Global Health Observatory: life tables (indicator LIFE_0000000035)",
            "url": "https://www.who.int/data/gho/data/indicators/indicator-details/GHO/life-expectancy-at-age-x-(ex)---(years)",
            "license": "CC BY-NC-SA 3.0 IGO", "year": year, "ages": AGES, "countries": parse_who(rows, year)}


def parse_ssa(page):
    """The SSA Actuarial Life Table page -> per-age death probabilities and life expectancies by sex."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", page)))
    year = re.search(r"the (\d{4}) period life table for the Social Security area population, as used in the (\d{4}) Trustees Report", text)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S | re.I):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip().replace(",", "")
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S | re.I)]
        if len(cells) == 7 and cells[0].isdigit():
            rows.append([int(cells[0])] + [float(x) for x in cells[1:]])
    if not year or len(rows) != 120 or [r[0] for r in rows] != list(range(120)):
        raise ValueError(f"unexpected SSA table layout ({len(rows)} rows)")
    return {"source": "Social Security Administration, Office of the Chief Actuary: Actuarial Life Table", "url": SSA_URL,
            "table_year": int(year.group(1)), "trustees_report": int(year.group(2)),
            "retrieved": dt.datetime.now(dt.timezone.utc).date().isoformat(),
            "note": "Period life table for the Social Security area population. Life expectancy at exact age x.",
            "male_qx": [r[1] for r in rows], "male_ex": [r[3] for r in rows],
            "female_qx": [r[4] for r in rows], "female_ex": [r[6] for r in rows]}


def validate_who(who):
    problems = []
    if len(who["countries"]) < 150:
        problems.append(f"only {len(who['countries'])} countries")
    if "USA" not in who["countries"] or "WLD" not in who["countries"]:
        problems.append("USA or world average missing")
    for code, sexes in who["countries"].items():
        for sex, ex in sexes.items():
            if not 30 <= ex[0] <= 95:
                problems.append(f"{code} {sex}: life expectancy at birth {ex[0]}")
            if not 0.5 <= ex[-1] <= 15:
                problems.append(f"{code} {sex}: life expectancy at 85 {ex[-1]}")
            # Remaining years can rise a little where young-adult deaths are high (Palestine's men in
            # 2023, for example); a big jump means the columns were scrambled.
            if any(b > a + 5 for a, b in zip(ex[1:], ex[2:])):
                problems.append(f"{code} {sex}: jumps with age")
    return problems


def validate_ssa(ssa):
    problems = []
    for sex, lo, hi in (("male", 68, 85), ("female", 74, 90)):
        ex = ssa[f"{sex}_ex"]
        if len(ex) != 120 or not lo <= ex[0] <= hi:
            problems.append(f"SSA {sex}: {len(ex)} ages, e0 {ex[0] if ex else None}")
        if any(b > a for a, b in zip(ex[1:], ex[2:])):
            problems.append(f"SSA {sex}: rises with age")
        if not all(0 <= q <= 1 for q in ssa[f"{sex}_qx"]):
            problems.append(f"SSA {sex}: probability out of range")
    return problems


def write_if_changed(path, data, keys_to_ignore=("retrieved",)):
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    strip = lambda d: {k: v for k, v in d.items() if k not in keys_to_ignore} if d else d  # noqa: E731
    if strip(old) == strip(data):
        print(f"{path.name}: unchanged")
        return False
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{path.name}: updated")
    return True


# WHO retries and a staleness limit (added 2026-11-22). The scheduled run on 2026-11-03 failed on an
# HTTP 500 from WHO's API that outlasted get()'s three quick tries (15 and 30 seconds apart); a run by
# hand a week later passed with no change. WHO publishes new life tables every few years, so a missed
# month costs nothing. refresh() now tries WHO again a few minutes later. If it still can't refresh
# the tables (an error, or a download that fails validation), it keeps the committed ones, warns, and
# records the date of the first failed run in data/refresh-state.json. The run fails only once that
# date is WHO_STALE_AFTER_DAYS old, so a long outage still shows up.
WHO_PAUSES = (60, 180)  # seconds before the 2nd and 3rd tries; each try is get()'s three quick ones
WHO_RETRY_UNTIL = 480  # seconds after the first try; no new try starts later (keeps the job inside its timeout)
# The 2nd failed monthly run comes 28-31 days after the 1st and the 3rd 59-62 days after it, so the
# third failed monthly run in a row fails: by then the tables have gone about three months unrefreshed.
WHO_STALE_AFTER_DAYS = 45
STATE_FILE = "refresh-state.json"
STATE_ABOUT = ("Written by pipeline/lifetables.py refresh. who_failing_since is the date of the first run in the "
               "current streak of runs that couldn't refresh the WHO tables, or null when the last run could. "
               f"The refresh job fails once that date is {WHO_STALE_AFTER_DAYS} days old.")
# Checked 2026-11-22: ssa.gov answered 403 in every refresh run since 2026-10-25 and to the same request
# from a home connection, robots.txt included. OPERATIONS.md has the details.
SSA_REFUSES = ("ssa.gov refuses scripted requests, GitHub's runners included, and has in every refresh run "
               "since 2026-10-25. The committed table stays; OPERATIONS.md says how it gets updated.")


def transient(e):
    """True for a failure worth trying again: HTTP 408, 429 or 5xx, a timeout, a dropped connection, a cut-off body."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (408, 429) or e.code >= 500
    return isinstance(e, (OSError, http.client.HTTPException, json.JSONDecodeError))


def who_with_retries(fetch=fetch_who, pauses=WHO_PAUSES, retry_until=WHO_RETRY_UNTIL, clock=time.monotonic):
    """fetch(), tried again after each pause while the failure is transient and time allows."""
    start = clock()
    for pause in tuple(pauses) + (None,):
        try:
            return fetch()
        except Exception as e:
            if pause is None or not transient(e) or clock() - start + pause > retry_until:
                raise
            print(f"::warning::WHO didn't answer ({e}); trying again in {pause} s", flush=True)
            time.sleep(pause)


def utc_today():
    return dt.datetime.now(dt.timezone.utc).date()


def read_state():
    path = DATA / STATE_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_state(state):
    state = {"about": STATE_ABOUT, **{k: v for k, v in state.items() if k != "about"}}
    (DATA / STATE_FILE).write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def who_refreshed():
    """Ends a streak of failed WHO refreshes, if one was running (and recreates a missing state file)."""
    state = read_state()
    if state.get("who_failing_since"):
        print(f"WHO refreshes had failed since {state['who_failing_since']}; this one worked")
    if state.get("who_failing_since") or not (DATA / STATE_FILE).exists():
        write_state(dict(state, who_failing_since=None))


def who_not_refreshed(error):
    """Keeps the committed WHO tables after a failed refresh. Returns 1 once refreshes have failed too long."""
    today, state = utc_today(), read_state()
    since = state.get("who_failing_since")
    if not since:
        since = today.isoformat()
        write_state(dict(state, who_failing_since=since))
    fail_from = dt.date.fromisoformat(since) + dt.timedelta(days=WHO_STALE_AFTER_DAYS)
    if today >= fail_from:
        print(f"::error::WHO life tables not updated: {error}. Every run since {since} has failed to refresh "
              f"them, so this one fails. The site keeps the committed tables.")
        return 1
    print(f"::warning::WHO life tables not updated, keeping the committed ones: {error}. Runs have failed "
          f"since {since}; from {fail_from} the run fails if WHO still does.")
    return 0


def refresh(fetch_who_fn=fetch_who, fetch_ssa_page=lambda: get(SSA_URL)):
    status = 0
    try:
        who = who_with_retries(fetch_who_fn)
        problems = validate_who(who)
        if problems:
            raise ValueError("the download failed validation: " + "; ".join(problems[:5]))
        write_if_changed(DATA / "who.json", who)
        print(f"WHO {who['year']}: {len(who['countries'])} tables")
        who_refreshed()
    except Exception as e:
        status = who_not_refreshed(e)
    try:
        ssa = parse_ssa(fetch_ssa_page())
        problems = validate_ssa(ssa)
        if problems:
            raise ValueError("; ".join(problems[:5]))
        write_if_changed(DATA / "ssa.json", ssa)
        print(f"SSA {ssa['table_year']} (Trustees Report {ssa['trustees_report']})")
    except Exception as e:
        if isinstance(e, urllib.error.HTTPError) and e.code == 403:
            print(f"::notice::SSA table not updated: ssa.gov answered 403. {SSA_REFUSES}")
        else:
            print(f"::warning::SSA table not updated, keeping the committed one: {e}")
    return status


def check():
    who = json.loads((DATA / "who.json").read_text(encoding="utf-8"))
    ssa = json.loads((DATA / "ssa.json").read_text(encoding="utf-8"))
    problems = validate_who(who) + validate_ssa(ssa)
    for p in problems:
        print(f"::error::{p}")
    print(f"WHO {who['year']} ({len(who['countries'])} tables), SSA {ssa['table_year']}: {'ok' if not problems else 'FAILED'}")
    return 1 if problems else 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    sys.exit(refresh() if cmd == "refresh" else check())
