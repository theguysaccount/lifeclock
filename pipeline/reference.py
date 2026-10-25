"""The LifeClock life-expectancy model in Python, written independently of site/assets/core.js.

Used by the build (country pages quote remaining years at given ages) and by the tests, which
require the browser's numbers to match these on a grid of countries, sexes and ages.

    python3 pipeline/reference.py grid   # prints {"<country>|<sex>|<age>": years} for the parity test
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YEAR_SECONDS = 365.2425 * 86400
WHO_AGES = [0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85]


def load():
    return {"ssa": json.loads((ROOT / "data" / "ssa.json").read_text(encoding="utf-8")),
            "who": json.loads((ROOT / "data" / "who.json").read_text(encoding="utf-8"))}


def _interp(xs, ys, t):
    if t <= xs[0]:
        return ys[0]
    if t >= xs[-1]:
        return ys[-1]
    i = next(k for k in range(1, len(xs)) if xs[k] >= t)
    return ys[i - 1] + (t - xs[i - 1]) / (xs[i] - xs[i - 1]) * (ys[i] - ys[i - 1])


def ssa_remaining(ssa, sex, age):
    if sex == "all":
        return (ssa_remaining(ssa, "female", age) + ssa_remaining(ssa, "male", age)) / 2
    ex = ssa["female_ex" if sex == "female" else "male_ex"]
    if age > 119:
        return max(ex[119] - (age - 119) * 0.05, 0.25)
    return _interp(list(range(120)), ex, age)


def who_remaining(row, ssa, sex, age):
    ex = row[sex]
    if age <= 85:
        return _interp(WHO_AGES, ex, age)
    return ex[-1] * ssa_remaining(ssa, sex, age) / ssa_remaining(ssa, sex, 85)


def remaining_years(tables, country, sex, age):
    if country == "USA":
        return ssa_remaining(tables["ssa"], sex, age)
    row = tables["who"]["countries"].get(country) or tables["who"]["countries"]["WLD"]
    return who_remaining(row, tables["ssa"], sex, age)


def grid(tables):
    out = {}
    for country in ("USA", "JPN", "NGA", "PSE", "KIR", "WLD", "ZZZ"):
        for sex in ("female", "male", "all"):
            for age in (0, 0.4, 1, 3.7, 17.25, 30, 44.9, 65.5, 84.99, 85, 86.3, 99.5, 119, 121.2):
                out[f"{country}|{sex}|{age}"] = remaining_years(tables, country, sex, age)
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["grid"]:
        json.dump(grid(load()), sys.stdout)
