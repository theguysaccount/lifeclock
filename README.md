# LifeClock

**Live:** https://theguysaccount.github.io/lifeclock/ · **Screens:** [docs/screens](docs/screens/)

Your life, counted in seconds. Enter a birthday, sex and country, and LifeClock shows a live count of the seconds ahead of you, on average, from public life tables: the U.S. Social Security Administration's for the US, and the World Health Organization's for 184 other countries and the world. It's an average, not a prediction, and it says so.

- **Live counter** that ticks every second, with everyday units (sunrises, weekends, full moons).
- **Time lived mode** that counts up instead, for anyone who'd rather not see a countdown.
- **Share card** drawn in the browser (1080×1080 PNG) with just the number.
- **Desk mode**: a full-screen clock for a spare screen; settings live after the "#" and never reach a server.
- **Billion-second birthday** calculator.
- **Life expectancy pages** for 185 countries and the world: average years left at every age, by sex.
- **Nothing stored**: no accounts, cookies, storage or analytics by default. Crisis-line links on every page.

## How it runs

| What | Where | When |
|---|---|---|
| Validate, test, build, drive in headless Chrome, deploy, smoke-test, IndexNow | `.github/workflows/pages.yml` | every push |
| Fetch WHO (and try SSA) life tables, validate, commit, redeploy | `.github/workflows/refresh.yml` | monthly |
| Live end-to-end test, page and table checks, keep-alive | `.github/workflows/selftest.yml` | weekly |

Failure handling and the keys for the domain, analytics and posters: [OPERATIONS.md](OPERATIONS.md).

## Layout

```
data/ssa.json, data/who.json   life tables (refreshed by refresh.yml), data/countries.json names and ISO codes
pipeline/lifetables.py         fetch, parse and validate the WHO and SSA tables
pipeline/reference.py          the model in Python (independent of the JS; the tests compare them)
pipeline/build.py              static site generator (standard library only) -> dist/
site/assets/core.js            the model in the browser; app.js the UI; selftest.js the end-to-end driver
scripts/                       e2e.sh, screens.sh, og.py, indexnow.py, check_live.py, keepalive.sh
tests/                         Python tests (tables, model, build) and tests/js (model, parity)
```

## Run, test, deploy

Python 3.9+, Google Chrome, Node 18+ for the JS tests.

```bash
python3 pipeline/build.py && python3 -m http.server -d dist 8000   # http://localhost:8000
python3 -m unittest discover -s tests
node --test tests/js/*.test.mjs
scripts/e2e.sh
```

Deploy is a push to `main`.

## Model

Exact age is time since local midnight on the birthday, in 365.2425-day years. Remaining years come from the SSA's single-year table (US; linear between ages) or the WHO's table at ages 0, 1, 5 … 85 (linear between; past 85, the WHO value follows the SSA curve's shape). "Prefer not to say" uses the WHO both-sexes table, or the average of the SSA's two tables. The clock counts down to the moment you pressed start plus those years.

## License

Code: MIT. Life tables: SSA (U.S. government work, public domain) and WHO (CC BY-NC-SA 3.0 IGO); the derived `data/who.json` and `dist/data/tables.json` are shared under CC BY-NC-SA 3.0 IGO.
