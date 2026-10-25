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
only when WHO data can't be fetched or validated, so a failed run shows up in Actions.
"""
import datetime as dt
import html
import json
import re
import sys
import time
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


def refresh(fetch_who_fn=fetch_who, fetch_ssa_page=lambda: get(SSA_URL)):
    status = 0
    try:
        who = fetch_who_fn()
        problems = validate_who(who)
        if problems:
            raise ValueError("; ".join(problems[:5]))
        write_if_changed(DATA / "who.json", who)
        print(f"WHO {who['year']}: {len(who['countries'])} tables")
    except Exception as e:
        print(f"::error::WHO life tables not updated: {e}")
        status = 1
    try:
        ssa = parse_ssa(fetch_ssa_page())
        problems = validate_ssa(ssa)
        if problems:
            raise ValueError("; ".join(problems[:5]))
        write_if_changed(DATA / "ssa.json", ssa)
        print(f"SSA {ssa['table_year']} (Trustees Report {ssa['trustees_report']})")
    except Exception as e:
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
