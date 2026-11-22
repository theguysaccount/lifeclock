# Operations

LifeClock runs itself on GitHub: Pages hosts it, Actions runs every recurring job. Nothing needs a person for it to keep working.

**Live:** https://app.getlifeclock.com/ (since 2026-11-22; the first address, https://theguysaccount.github.io/lifeclock/, redirects there)
**Repo:** https://github.com/theguysaccount/lifeclock

## Automated jobs

| Job | Workflow | When | What it does | How it fails safe |
|---|---|---|---|---|
| Deploy | `pages.yml` | every push to `main`, and after a table refresh | Validates the committed tables, runs the Python and JS tests (including Python/JS model parity), builds `dist/`, drives the home page, billion-seconds page and desk mode in headless Chrome, deploys, smoke-tests the live site, pings IndexNow | Any failure stops before deploy, so the last good site stays live. IndexNow problems are logged, never fatal. |
| Life-table refresh | `refresh.yml` | the 3rd of every month, 06:23 UTC | Fetches the newest WHO life tables (GHO API, every country) and tries the SSA Actuarial Life Table; validates both (ranges, shape, coverage); runs the tests; commits and redeploys only if something changed | Tables that fail validation are never written. ssa.gov refuses GitHub's runners (403 in every run so far), which is a notice: the committed SSA table stays. Since 2026-11-22 a WHO failure is a warning too: the committed tables stay, and the run fails only once WHO refreshes have failed on every run for 45 days, which is the third monthly run in a row (see "A WHO streak" below). |
| Self-test + keep-alive | `selftest.yml` | Tuesdays 14:37 UTC | Tests; drives the **live** site end to end; checks every sitemap URL answers 200 with its own canonical and that the live tables match the committed ones; warns when tables get old. Then the keep-alive. | On failure, opens (or comments on) one `ops-alert` issue, and GitHub emails the repo owner. The site is untouched. |
| Keep-alive | `selftest.yml` → `scripts/keepalive.sh` | weekly, even if the self-test fails | Re-enables each scheduled workflow through the API; pushes an empty `[skip ci]` commit when the last commit is 45+ days old | GitHub disables scheduled workflows after 60 days without repository activity; LifeClock's data changes only yearly, so this matters here. |

## What to watch

- **Open `ops-alert` issues.**
- **Retried fetches.** Since 2026-11-22 the self-test and the smoke test after each deploy load a page again after 10, 20 and 30 seconds when GitHub Pages answers with a 5xx, times out or drops the connection (a single 503 failed the self-test on 2026-11-17): at most six retries per run in `scripts/check_live.py` and four in `scripts/e2e.sh`, so a site that's really down still fails within minutes. Each retry leaves a warning on the run, and only a page that still fails counts. A 403 or 404 fails at once.
- **A WHO streak.** Since 2026-11-22 a refresh that can't get the WHO tables tries WHO three times, a few minutes apart (60 and 180 seconds; each try is itself three quick attempts, 15 and 30 seconds apart). If it still fails, from an HTTP error, a timeout or a download that fails validation, the run keeps the committed tables and leaves a warning. The first failed run records its date in `data/refresh-state.json` and commits it without redeploying (the site doesn't read the file), and the next good run clears it. The run fails once that date is 45 days old: the third failed monthly run in a row, about three months after the last good refresh. WHO publishes new tables only every few years, so a few missed months change nothing on the site. Before this, the 500 that WHO's API returned on 2026-11-03 failed the whole run, though a run by hand a week later passed. When the job goes red, read the run's error. If WHO changed its API, fix `pipeline/lifetables.py`, then run `refresh.yml` by hand.
- **The SSA table can't refresh from Actions.** Checked 2026-11-22: ssa.gov has answered 403 in every refresh run since 2026-10-25 (each run tries three times), and it gave the same 403 to the same request from a home connection, for the table and for robots.txt. Its bot filter refuses scripted requests in general, not just GitHub's network, so no run of the job will get the table. The job still asks once a month in case that changes. Since 2026-11-22 a 403 shows as a notice in the run, not a warning. Any other SSA problem (a new page layout, a table that fails validation) is still a warning. The SSA publishes a new table with each Trustees Report (usually spring or summer). The committed table is the 2023 table from the 2026 report, read in a browser on 2026-10-25. A person updates it by hand once a year: open https://www.ssa.gov/oact/STATS/table4c6.html in a browser, save the page as `table4c6.html`, and run `python3 -c "import sys,json; sys.path.insert(0,'pipeline'); import lifetables as L; d=L.parse_ssa(open('table4c6.html').read()); assert not L.validate_ssa(d); L.write_if_changed(L.DATA/'ssa.json', d)"`, then commit. Not an AI agent: see key 5. Nothing breaks if nobody does it; the self-test warns once the table is more than 4 years old.
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

**Switched on 2026-11-22 to `app.getlifeclock.com`.** A subdomain, so the apex and whatever SiteGround serves there stay as they are. `app` has a CNAME to `theguysaccount.github.io` in the zone that answers for getlifeclock.com (SiteGround's nameservers). The domain rollout session made it the Pages custom domain (certificate approved, HTTPS enforced), set `SITE_URL` = `https://app.getlifeclock.com` and redeployed at 08:22 UTC. The self-test passed against the new address at 08:25.

#### Exact commands to switch the base URL (added 2026-11-22)

The steps above as commands, for the domain rollout session or anyone with `gh` signed in as theguysaccount: to redo the switch, move to another name, or undo it. Every address the build writes into the site (canonicals, sitemap, robots.txt, Open Graph tags, JSON-LD, IndexNow) comes from the one repo variable `SITE_URL`, and the deploy smoke test and the weekly self-test follow it too, so no file needs editing. DNS is the domain rollout session's job; nothing in this repo changes DNS. Don't add a `CNAME` file: this site deploys through Actions, which ignores one.

```bash
REPO=theguysaccount/lifeclock
DOMAIN=app.getlifeclock.com   # the chosen name: no https://, no trailing slash

# 0. DNS must already point at GitHub. Ask a public resolver (a local cache can be stale):
curl -s "https://dns.google/resolve?name=$DOMAIN&type=A"   # expect theguysaccount.github.io. and 185.199.108-111.153

# 1. Make it the Pages custom domain. GitHub requests a certificate, and github.io starts redirecting to it.
gh api -X PUT "repos/$REPO/pages" -f cname="$DOMAIN"

# 2. Enforce HTTPS once the certificate exists (minutes, sometimes hours). This tries every 2 minutes for 2 hours.
for i in $(seq 60); do gh api -X PUT "repos/$REPO/pages" -F https_enforced=true --silent 2>/dev/null && break; sleep 120; done
gh api "repos/$REPO/pages" --jq '{cname, https_enforced, certificate: .https_certificate.state}'   # expect true, "approved"

# 3. Switch the base URL and redeploy.
gh variable set SITE_URL -R "$REPO" --body "https://$DOMAIN"
gh workflow run pages.yml -R "$REPO"
sleep 20; gh run watch -R "$REPO" --exit-status "$(gh run list -R "$REPO" --workflow pages.yml --limit 1 --json databaseId --jq '.[0].databaseId')"

# 4. Pages' CDN keeps each page for up to 10 minutes (max-age=600), so wait before checking canonicals.
#    Then, from a checkout of this repo. (A machine whose DNS cache doesn't know the new name yet fails
#    these with "nodename nor servname provided"; the selftest.yml run on GitHub's runners still counts.)
sleep 600
# The home page should name the new address. If it still names the old one, run pages.yml once more
# (on 2026-11-22 a stale / outlived the wait on SoulmateCheck, and the next deploy cleared it).
curl -s --resolve "$DOMAIN:443:185.199.108.153" "https://$DOMAIN/" | grep -o '<link rel="canonical" href="[^"]*"'   # expect https://$DOMAIN/
scripts/e2e.sh "https://$DOMAIN/"
python3 scripts/check_live.py "https://$DOMAIN"
curl -sI "https://theguysaccount.github.io/${REPO#*/}/" | grep -i '^location'   # expect https://$DOMAIN/
gh workflow run selftest.yml -R "$REPO"
```

Afterwards: `gh repo edit "$REPO" --homepage "https://$DOMAIN"`, put the new address in the **Live:** line at the top, and add the domain to Google Search Console (key 4). To undo: `gh variable delete SITE_URL -R "$REPO"`, `gh api -X PUT "repos/$REPO/pages" -F cname=null`, then `gh workflow run pages.yml -R "$REPO"`.

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

**Withdrawn on 2026-11-22: don't set this routine up.** ssa.gov refuses scripted requests. An AI agent that opens the page in a browser to get the table anyway would be getting around that refusal, which this project doesn't do (DECISIONS.md, "Honest handling of blocked sources"). The yearly SSA update is for a person, as described under "What to watch".

## Safety and privacy rules the code keeps

- Every result says it's an average, not a prediction, and names its source table.
- Every page links to 988 (US) and findahelpline.com; the result screen repeats it next to the clock.
- "Time lived" mode counts up instead of down, for anyone who'd rather not see a countdown.
- Birthdays never leave the browser: no storage, no cookies, no analytics by default; desk mode keeps settings after the "#"; share cards are drawn on the device and carry only the number.
