# State (2026-10-25)

- **Existing material (read):** five LifeClock notes from 2021 (ad copy "Yes, this clock makes you uncomfortable. That's why it works", "Why wait? You're not getting any younger", "make a desktop-sized version", a Tidbyt link, a TikTok link), the "Seconds left shirts" note, and the Existism "Weareracingtime" note (78 years = 28,470 days). No code, site or sales.
- **getlifeclock.com:** owned (Namecheap, renews 2027-09-24), DNS at SiteGround, serving something behind SiteGround's robot challenge. Not touched.
- **What works now:** a live static site with the live clock (count down or up), share card, desk mode, billion-second calculator, 186 life-expectancy pages, and three scheduled workflows (deploy, monthly table refresh, weekly self-test with keep-alive).
- **What's limited:** ssa.gov refuses scripted requests (403) from this machine and GitHub's runners, so the SSA table updates only when a fetch gets through or by hand once a year (OPERATIONS.md). The WHO API works.
- **Worth reusing:** the life-table pipeline (WHO GHO + SSA, validated), the Python/JS model-parity test, the canvas share card, and the hash-only desk-mode pattern for private settings.
