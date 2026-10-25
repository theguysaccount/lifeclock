# Operations

LifeClock runs itself on GitHub: Pages hosts it, Actions runs every recurring job. Nothing needs a person for it to keep working.

**Live:** https://theguysaccount.github.io/lifeclock/
**Repo:** https://github.com/theguysaccount/lifeclock

## Automated jobs

| Job | Workflow | When | What it does | How it fails safe |
|---|---|---|---|---|
| Deploy | `pages.yml` | every push to `main`, and after a table refresh | Validates the committed tables, runs the Python and JS tests (including Python/JS model parity), builds `dist/`, drives the home page, billion-seconds page and desk mode in headless Chrome, deploys, smoke-tests the live site, pings IndexNow | Any failure stops before deploy, so the last good site stays live. IndexNow problems are logged, never fatal. |
| Life-table refresh | `refresh.yml` | the 3rd of every month, 06:23 UTC | Fetches the newest WHO life tables (GHO API, every country) and tries the SSA Actuarial Life Table; validates both (ranges, shape, coverage); runs the tests; commits and redeploys only if something changed | Tables that fail validation are never written. ssa.gov answers many networks (including GitHub's) with 403, which is a warning: the committed SSA table stays. The run fails only if the WHO tables can't be fetched or validated. |
| Self-test + keep-alive | `selftest.yml` | Tuesdays 14:37 UTC | Tests; drives the **live** site end to end; checks every sitemap URL answers 200 with its own canonical and that the live tables match the committed ones; warns when tables get old. Then the keep-alive. | On failure, opens (or comments on) one `ops-alert` issue, and GitHub emails the repo owner. The site is untouched. |
| Keep-alive | `selftest.yml` → `scripts/keepalive.sh` | weekly, even if the self-test fails | Re-enables each scheduled workflow through the API; pushes an empty `[skip ci]` commit when the last commit is 45+ days old | GitHub disables scheduled workflows after 60 days without repository activity; LifeClock's data changes only yearly, so this matters here. |

## What to watch

- **Open `ops-alert` issues.**
- **The SSA warning in refresh runs.** The SSA publishes a new table with each Trustees Report (usually spring or summer). The committed table is the 2023 table from the 2026 report, read in a browser on 2026-10-25. If ssa.gov keeps refusing GitHub's runners, update it by hand once a year: open https://www.ssa.gov/oact/STATS/table4c6.html in a browser, save the page as `table4c6.html`, and run `python3 -c "import sys,json; sys.path.insert(0,'pipeline'); import lifetables as L; d=L.parse_ssa(open('table4c6.html').read()); assert not L.validate_ssa(d); L.write_if_changed(L.DATA/'ssa.json', d)"`, then commit. Or give it to the content routine below.
- **The self-test's staleness warnings** (SSA table more than 4 years old, WHO tables more than 6).

## Run anything by hand

```bash
python3 pipeline/lifetables.py refresh     # fetch WHO (and try SSA) into data/
python3 pipeline/lifetables.py check       # validate data/
python3 pipeline/build.py                  # build dist/
scripts/e2e.sh                             # drive dist/ in headless Chrome
scripts/e2e.sh https://theguysaccount.github.io/lifeclock/
python3 scripts/check_live.py https://theguysaccount.github.io/lifeclock
~/.local/bin/gh workflow run refresh.yml -R theguysaccount/lifeclock
```

## Keys Jack can turn later

Nothing below is needed for the site to work.

### 1. Custom domain: getlifeclock.com

`getlifeclock.com` is in the 2026-08-30 portfolio (Namecheap, registered 2020-09-24, renews 2027-09-24). **Something is live on it now:** its nameservers are SiteGround's (`ns1/ns2.siteground.net`), it resolves to `35.215.81.164`, and visitors get SiteGround's robot-challenge screen before the site, probably the 2021 LifeClock site. Check what's there before changing anything.

Steps once Jack decides to move it:
1. In SiteGround's DNS zone for getlifeclock.com (or at Namecheap, if the nameservers move back): replace the `A @` record with GitHub Pages' four addresses `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`; add `AAAA @` → `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153`; set `CNAME www` → `theguysaccount.github.io`.
2. GitHub → theguysaccount/lifeclock → Settings → Pages → Custom domain: `getlifeclock.com`. Wait for the certificate, then tick **Enforce HTTPS**.
3. Settings → Secrets and variables → Actions → Variables: `SITE_URL` = `https://getlifeclock.com`. Run `gh workflow run pages.yml -R theguysaccount/lifeclock`. Canonicals, sitemap, share cards and IndexNow switch over.
4. The github.io address then redirects to the domain by itself.

### 2. Money: posters and shirts

GitHub Pages is non-commercial, so the site sells nothing itself. The slot is a "Get it printed" button next to the share card and a section on the About page, hidden until a link exists. The idea from the notes: shirts reading "I had 1,580,214,377 seconds left when I bought this shirt".

- Create the product (a Stripe Payment Link, or a print-on-demand store) and set the repo variable `POSTER_URL` to its URL. Redeploy with `gh workflow run pages.yml`.
- Note: the WHO data is CC BY-NC-SA 3.0 IGO (non-commercial). A poster showing a person's own number is fine; selling the WHO tables themselves isn't.

### 3. Analytics (activation metric)

Off by default (the site promises nothing is stored). Events already in the code: `clock_start/<mode>-<country>` (**activation**), `card_open`, `card_share/<how>`, `desk_open`, `mode_toggle`, `billion_start`.

- Create a free GoatCounter site, set repo variable `GOATCOUNTER_URL` = `https://<code>.goatcounter.com/count`, redeploy. Privacy text updates itself.

### 4. Search Console

Verify the site in Google Search Console (needs Jack's Google account) and submit `/sitemap.xml`. Bing and other IndexNow engines are pinged on every deploy.

### 5. Content routine (optional)

There is no recurring AI content here. If ssa.gov keeps blocking GitHub, a yearly Claude routine in July can do the manual SSA update above: "Open the SSA Actuarial Life Table in a browser, update data/ssa.json with pipeline/lifetables.py's parse_ssa and validate_ssa, run the tests, commit and push."

## Safety and privacy rules the code keeps

- Every result says it's an average, not a prediction, and names its source table.
- Every page links to 988 (US) and findahelpline.com; the result screen repeats it next to the clock.
- "Time lived" mode counts up instead of down, for anyone who'd rather not see a countdown.
- Birthdays never leave the browser: no storage, no cookies, no analytics by default; desk mode keeps settings after the "#"; share cards are drawn on the device and carry only the number.
