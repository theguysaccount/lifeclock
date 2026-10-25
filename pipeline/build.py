"""Build the LifeClock static site into dist/. Standard library only (Python 3.9+).

    python3 pipeline/build.py [--out dist]

Optional environment (GitHub repository variables in CI; see OPERATIONS.md):
    SITE_URL         canonical origin + path, no trailing slash (default: the GitHub Pages URL)
    GOATCOUNTER_URL  e.g. https://lifeclock.goatcounter.com/count -> cookieless analytics on
    POSTER_URL       link to a print shop or payment link for posters/shirts -> money slot shown
    BUILD_DATE       YYYY-MM-DD, to reproduce a build
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reference import remaining_years, WHO_AGES, YEAR_SECONDS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITE_URL = "https://theguysaccount.github.io/lifeclock"
REPO_URL = "https://github.com/theguysaccount/lifeclock"
INDEXNOW_KEY = (ROOT / "site" / "indexnow-key.txt").read_text().strip()
BRAND = "LifeClock"
e = html.escape


def attr(s):
    return html.escape(str(s), quote=True)


def years_fmt(y):
    return f"{y:.1f}"


def billions(y):
    s = y * YEAR_SECONDS
    return f"{s / 1e9:.2f} billion" if s >= 1e9 else f"{s / 1e6:,.0f} million"


# Country names that read with "the": "in the United States".
THE = {"USA", "GBR", "NLD", "PHL", "BHS", "GMB", "MDV", "MHL", "SLB", "CAF", "DOM", "ARE", "COG", "COD", "COM", "SYC"}


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


SUPPORT = ('If thinking about time or death feels heavy right now, you’re not alone. In the US, call or text '
           '<a href="https://988lifeline.org/">988</a> (Suicide &amp; Crisis Lifeline). Elsewhere, find a free, '
           'confidential helpline at <a href="https://findahelpline.com/">findahelpline.com</a>.')


class Site:
    def __init__(self, out, today):
        self.out, self.today = out, today
        self.site_url = os.environ.get("SITE_URL", DEFAULT_SITE_URL).rstrip("/")
        self.goatcounter = os.environ.get("GOATCOUNTER_URL", "").strip()
        self.poster_url = os.environ.get("POSTER_URL", "").strip()
        self.ssa = json.loads((ROOT / "data" / "ssa.json").read_text(encoding="utf-8"))
        self.who = json.loads((ROOT / "data" / "who.json").read_text(encoding="utf-8"))
        self.countries = json.loads((ROOT / "data" / "countries.json").read_text(encoding="utf-8"))
        self.tables = {"ssa": self.ssa, "who": self.who}
        self.codes = sorted((c for c in self.who["countries"] if c in self.countries), key=lambda c: self.countries[c]["name"])
        self.pages = []
        h = hashlib.sha1()
        for p in sorted((ROOT / "site" / "assets").rglob("*")):
            if p.is_file():
                h.update(p.name.encode() + p.read_bytes())
        h.update((ROOT / "data" / "who.json").read_bytes() + (ROOT / "data" / "ssa.json").read_bytes())
        self.ver = h.hexdigest()[:10]

    def url(self, path):
        return f"{self.site_url}/{path}"

    def in_name(self, code):
        name = self.countries[code]["name"]
        return f"the {name}" if code in THE else name

    def write(self, path, text):
        f = self.out / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")

    def layout(self, path, title, description, body, *, page="static", og="home", jsonld=None, noindex=False, current="", root=None):
        if root is None:
            depth = path.count("/")
            root = "../" * depth if depth else "./"
        cfg = json.dumps({"root": root, "siteUrl": self.site_url, "posterUrl": self.poster_url})
        here = ' aria-current="page"'
        nav = "".join(f'<a href="{root}{p}"{here if p == current else ""}>{label}</a>' for p, label in
                      [("", "LifeClock"), ("billion-seconds/", "Billion seconds"), ("life-expectancy/", "By country"), ("about/", "About")])
        ld = "".join('<script type="application/ld+json">%s</script>\n' % json.dumps(b, ensure_ascii=False).replace("</", "<\\/")
                     for b in (jsonld or []))
        gc = (f'<script data-goatcounter="{attr(self.goatcounter)}" async src="https://gc.zgo.at/count.js"></script>\n'
              if self.goatcounter else "")
        privacy = ("Visits are counted with GoatCounter (no cookies, no personal data). " if self.goatcounter else "") + \
            "Your birthday never leaves your browser; nothing is stored."
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{attr(description)}">
<link rel="canonical" href="{self.url(path)}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{BRAND}">
<meta property="og:title" content="{attr(title)}">
<meta property="og:description" content="{attr(description)}">
<meta property="og:url" content="{self.url(path)}">
<meta property="og:image" content="{self.site_url}/assets/og/{og}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#14161f">
<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{root}assets/site.css?v={self.ver}">
{ld}<script type="application/json" id="site-config">{cfg}</script>
<script type="module" src="{root}assets/app.js?v={self.ver}"></script>
{gc}</head>
<body data-page="{page}">
<a class="skip" href="#main">Skip to content</a>
<header class="site-head"><div class="wrap">
<a class="logo" href="{root}"><span aria-hidden="true">◷</span> {BRAND}</a>
<nav class="nav" aria-label="Main">{nav}</nav>
</div></header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site-foot"><div class="wrap">
<nav aria-label="Footer"><a href="{root}">LifeClock</a><a href="{root}billion-seconds/">Billion-second birthday</a><a href="{root}life-expectancy/">Life expectancy by country</a><a href="{root}about/">About, method and privacy</a><a href="{REPO_URL}">Source code</a></nav>
<p>{SUPPORT}</p>
<p>Estimates are averages from public life tables (U.S. Social Security Administration and World Health Organization), not predictions or medical advice. {privacy}</p>
</div></footer>
</body>
</html>
"""

    def form(self, submit, desk=False):
        return f"""<form id="clock-form" class="card" novalidate{' hidden' if desk else ''}>
<label>Your birthday <input type="date" name="birth" required min="1906-01-01" max="{self.today.isoformat()}" autocomplete="bday"></label>
<fieldset><legend>Life tables differ by sex</legend>
<label class="inline"><input type="radio" name="sex" value="female"> Female</label>
<label class="inline"><input type="radio" name="sex" value="male"> Male</label>
<label class="inline"><input type="radio" name="sex" value="all" checked> Prefer not to say</label>
</fieldset>
<label>Country <select name="country"><option value="WLD">World average</option></select></label>
<fieldset><legend>Show</legend>
<label class="inline"><input type="radio" name="mode" value="down" checked> Time ahead (counts down)</label>
<label class="inline"><input type="radio" name="mode" value="up"> Time lived (counts up)</label>
</fieldset>
<p class="error" data-error role="alert" hidden></p>
<button class="btn" type="submit">{submit}</button>
<p class="note" style="margin-top:12px">Nothing you enter leaves this page: no account, no cookies, no storage.</p>
</form>"""

    def result_block(self, desk=False):
        poster = (f'<a class="btn secondary small" href="{attr(self.poster_url)}" rel="noopener">Get it printed</a>' if self.poster_url else "")
        if desk:
            return """<section id="desk" hidden aria-live="off">
<p class="counter" data-counter tabindex="-1"></p>
<p class="label" data-label></p>
<p class="basis" data-basis></p>
<div class="btn-row">
<button class="btn secondary small" type="button" data-toggle></button>
<button class="btn secondary small" type="button" data-fullscreen>Full screen</button>
<button class="btn secondary small" type="button" data-wake>Keep screen on</button>
<a class="btn secondary small" href="../">Exit</a>
</div>
<p class="basis">This address holds your birthday after the “#”, which never reaches any server. Bookmark it for your desk; don't share it.</p>
</section>"""
        return f"""<section id="result" hidden>
<p class="eyebrow">Your LifeClock</p>
<p class="counter" data-counter tabindex="-1" aria-live="off"></p>
<p class="label" data-label></p>
<p data-sub></p>
<p class="basis" data-basis></p>
<div class="btn-row">
<button class="btn" type="button" data-card>Make my share card</button>
<a class="btn secondary" data-desk href="desk/">Desk mode</a>
<button class="btn secondary" type="button" data-toggle></button>
<button class="btn secondary" type="button" data-edit>Change details</button>
{poster}
</div>
<div class="cardbox" data-cardbox hidden>
<canvas width="1080" height="1080" aria-label="Your LifeClock share card"></canvas>
<div class="btn-row"><button class="btn small" type="button" data-native hidden>Share…</button><a class="btn small secondary" data-download download="lifeclock.png" href="#">Download image</a><button class="btn small secondary" type="button" data-copy>Copy text and link</button></div>
</div>
<p class="milestone" data-milestone></p>
<p class="support">{SUPPORT}</p>
</section>"""

    # ---------- pages ----------
    def home(self):
        us, world = self.ssa, self.who["countries"]["WLD"]
        body = f"""
<div class="page-intro">
<h1>Your life, counted in seconds</h1>
<p class="lede">Enter your birthday to see roughly how many seconds are ahead of you, from public life tables. It's an average, not a prediction: a nudge to spend today on what matters.</p>
</div>
{self.form("Start my LifeClock")}
{self.result_block()}
<section>
<h2>How it works</h2>
<p>Life tables record, for each age, how many more years people of that age live on average. LifeClock looks up your exact age in the newest table for your country and sex, adds that many years to today, and counts the seconds down to that date. For the United States it uses the Social Security Administration's {us['table_year']} period life table (from the {us['trustees_report']} Trustees Report); for {len(self.codes) - 1} other countries and the world it uses the World Health Organization's {self.who['year']} life tables.</p>
<p>The worldwide average at birth is {years_fmt(world['all'][0])} years. The older you are, the further the average reaches, because you've already lived through the risks of earlier years.</p>
<p><a href="life-expectancy/">Life expectancy by age for every country →</a> · <a href="billion-seconds/">When are you a billion seconds old? →</a></p>
<h2>Why count seconds?</h2>
<p>A big number in seconds makes time feel concrete in a way “decades” doesn't. Some people keep it on a second screen in <a href="desk/">desk mode</a> as a nudge to skip what doesn't matter. If a countdown isn't for you, switch to time lived: it counts up instead.</p>
</section>
"""
        ld = [{"@context": "https://schema.org", "@type": "WebApplication", "name": "LifeClock", "url": self.site_url + "/",
               "applicationCategory": "LifestyleApplication", "operatingSystem": "Any", "isAccessibleForFree": True,
               "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
               "description": "A live count of the seconds ahead of you, on average, from SSA and WHO life tables."}]
        self.write("index.html", self.layout("", "LifeClock: your life in seconds, from public life tables",
                                             "How many seconds are ahead of you, on average? A free, private life-expectancy clock built on SSA and WHO life tables. Nothing is stored.",
                                             body, page="home", jsonld=ld, current=""))
        self.pages.append("")

    def billion(self):
        body = f"""
<h1>When will you be a billion seconds old?</h1>
<p class="lede">A billion seconds is about 31 years and 8 months. Enter your birthday to see the exact day you pass it, and your next billion-second birthdays.</p>
<form id="billion-form" class="card" novalidate>
<label>Your birthday <input type="date" name="birth" required min="1906-01-01" max="{self.today.isoformat()}" autocomplete="bday"></label>
<p class="error" data-error role="alert" hidden></p>
<button class="btn" type="submit">Find my billion-second birthday</button>
<p class="note" style="margin-top:12px">Nothing you enter leaves this page.</p>
</form>
<section id="result" hidden>
<p class="eyebrow">You've lived</p>
<p class="counter" data-counter tabindex="-1"></p>
<p class="label">seconds so far</p>
<p data-next></p>
<ul data-list></ul>
<div class="btn-row"><button class="btn" type="button" data-card>Make my share card</button><a class="btn secondary" href="../">See your LifeClock</a></div>
<div class="cardbox" data-cardbox hidden>
<canvas width="1080" height="1080" aria-label="Your billion-second share card"></canvas>
<div class="btn-row"><button class="btn small" type="button" data-native hidden>Share…</button><a class="btn small secondary" data-download download="billion-seconds.png" href="#">Download image</a><button class="btn small secondary" type="button" data-copy>Copy text and link</button></div>
</div>
</section>
<h2>Billion-second birthdays at a glance</h2>
<div class="table-wrap"><table><thead><tr><th>Seconds old</th><th>Age</th></tr></thead><tbody>
{''.join(f'<tr><td>{n / 1e9:g} billion</td><td>{n / YEAR_SECONDS:.1f} years ({n / 86400:,.0f} days)</td></tr>' for n in (5e8, 1e9, 1.5e9, 2e9, 2.5e9, 3e9))}
</tbody></table></div>
<p>The dates assume you were born at midnight local time; leap years are counted exactly. Want the other direction? <a href="../">LifeClock</a> counts the seconds ahead of you, on average.</p>
"""
        self.write("billion-seconds/index.html", self.layout(
            "billion-seconds/", "When will I be a billion seconds old? Billion-second birthday calculator",
            "Find the exact date you turn 1 billion seconds old (about 31.7 years), plus your 1.5 and 2 billion-second birthdays. Free, private, nothing stored.",
            body, page="billion", og="billion", current="billion-seconds/"))
        self.pages.append("billion-seconds/")

    def desk(self):
        body = f"""
<div class="page-intro">
<h1>LifeClock desk mode</h1>
<p class="lede">A full-screen clock for a spare screen or tablet. Fill this in once, then bookmark the page.</p>
</div>
{self.form("Open desk mode", desk=False)}
{self.result_block(desk=True)}
"""
        self.write("desk/index.html", self.layout("desk/", f"Desk mode | {BRAND}", "LifeClock as a full-screen desk clock.",
                                                  body, page="desk", noindex=True))

    def country_rows(self, code):
        row = self.who["countries"][code]
        return "".join(
            f"<tr><td>{age}{'+' if age == 85 else ''}</td><td>{years_fmt(row['female'][i])}</td><td>{years_fmt(row['male'][i])}</td><td>{years_fmt(row['all'][i])}</td></tr>"
            for i, age in enumerate(WHO_AGES))

    def country_page(self, code):
        root = "../../"
        if code == "WLD":
            name, slug, where = "the world", "world", "worldwide"
        else:
            name, slug = self.countries[code]["name"], self.countries[code]["slug"]
            where = f"in {self.in_name(code)}"
        path = f"life-expectancy/{slug}/"
        row = self.who["countries"][code]
        world = self.who["countries"]["WLD"]
        ranking = sorted((c for c in self.codes), key=lambda c: -self.who["countries"][c]["all"][0])
        rank = ranking.index(code) + 1 if code in ranking else None
        t = self.tables
        r30f, r30m = remaining_years(t, code, "female", 30), remaining_years(t, code, "male", 30)
        r65 = remaining_years(t, code, "all", 65)
        diff = row["all"][0] - world["all"][0]
        comparison = ("" if code == "WLD" else
                      f"That's {abs(diff):.1f} years {'more' if diff >= 0 else 'less'} than the world average of {years_fmt(world['all'][0])}, "
                      f"and ranks {ordinal(rank)} of {len(ranking)} countries in the WHO's tables.")
        us_note = ""
        if code == "USA":
            s = self.ssa
            us_rows = "".join(f"<tr><td>{a}</td><td>{s['female_ex'][a]:.2f}</td><td>{s['male_ex'][a]:.2f}</td></tr>" for a in range(0, 120))
            us_note = f"""<h2>United States, single years of age (SSA)</h2>
<p>For the US, LifeClock uses the Social Security Administration's {s['table_year']} period life table from the {s['trustees_report']} Trustees Report, which gives every age from 0 to 119. At 30, a woman has {s['female_ex'][30]:.1f} more years on average and a man {s['male_ex'][30]:.1f}; at 65, {s['female_ex'][65]:.1f} and {s['male_ex'][65]:.1f}.</p>
<details><summary>Show all ages, 0 to 119</summary><div class="table-wrap"><table><thead><tr><th>Age</th><th>Women</th><th>Men</th></tr></thead><tbody>{us_rows}</tbody></table></div></details>
<p class="note">Source: <a href="{s['url']}">SSA Office of the Chief Actuary, Actuarial Life Table</a>. U.S. government work, public domain.</p>"""
        cta = f'<p><a class="btn" href="{root}?c={code}">See your LifeClock{" for " + e(self.in_name(code)) if code != "WLD" else ""}</a></p>'
        body = f"""
<nav class="note" aria-label="Breadcrumb"><a href="{root}">LifeClock</a> › <a href="{root}life-expectancy/">Life expectancy by country</a> › {e(name.capitalize() if code == 'WLD' else name)}</nav>
<h1>Life expectancy {e(where)}, by age</h1>
<p class="lede">On average, a newborn {e(where)} can expect to live {years_fmt(row['all'][0])} years: {years_fmt(row['female'][0])} for girls and {years_fmt(row['male'][0])} for boys (World Health Organization, {self.who['year']}). {comparison}</p>
<div class="facts">
<div class="fact"><b>{years_fmt(r30f)} years</b><span>left on average for a 30-year-old woman, about {billions(r30f)} seconds</span></div>
<div class="fact"><b>{years_fmt(r30m)} years</b><span>left on average for a 30-year-old man, about {billions(r30m)} seconds</span></div>
<div class="fact"><b>{years_fmt(r65)} years</b><span>left on average at 65, everyone</span></div>
</div>
{cta}
<h2>Average years left at each age</h2>
<p>Each row is the average number of further years lived by people who reach that age, using the mortality rates of {self.who['year']}. It rises past the at-birth figure for older ages because those people have already survived the earlier years.</p>
<div class="table-wrap"><table><thead><tr><th>Age</th><th>Women</th><th>Men</th><th>Everyone</th></tr></thead><tbody>{self.country_rows(code)}</tbody></table></div>
<p class="note">Source: <a href="{self.who['url']}">WHO Global Health Observatory, life tables</a> ({self.who['year']}), licensed CC BY-NC-SA 3.0 IGO. Averages describe whole populations, not any one person; health, habits, income and luck matter far more.</p>
{us_note}
<h2>What these numbers mean</h2>
<p>A period life table is a snapshot: it applies one year's death rates to every age. If health keeps improving, people born today will likely live longer than these figures. Treat them as a rough guide to the time ahead, not a forecast.</p>
<p><a href="{root}life-expectancy/">Compare all countries →</a></p>
"""
        ld = [{"@context": "https://schema.org", "@type": "Dataset",
               "name": f"Life expectancy {where} by age and sex ({self.who['year']})",
               "description": f"Average remaining years of life at ages 0 to 85+ for women, men and everyone {where}, from WHO life tables.",
               "url": self.url(path), "creator": {"@type": "Organization", "name": "World Health Organization"},
               "license": "https://creativecommons.org/licenses/by-nc-sa/3.0/igo/", "temporalCoverage": str(self.who["year"]),
               "spatialCoverage": "World" if code == "WLD" else name, "isAccessibleForFree": True}]
        title = (f"Life expectancy {where} by age ({self.who['year']}): years left at every age | {BRAND}")
        desc = (f"Average years left at every age {where}, for women and men, from WHO life tables ({self.who['year']}): "
                f"{years_fmt(row['all'][0])} years at birth.")
        self.write(path + "index.html", self.layout(path, title, desc, body, og="life-expectancy", jsonld=ld, current="life-expectancy/"))
        self.pages.append(path)

    def hub(self):
        root = "../"
        rows = sorted(self.codes, key=lambda c: -self.who["countries"][c]["all"][0])
        trs = "".join(
            f'<tr><td><a href="{self.countries[c]["slug"]}/">{e(self.countries[c]["name"])}</a></td>'
            f'<td>{years_fmt(self.who["countries"][c]["female"][0])}</td><td>{years_fmt(self.who["countries"][c]["male"][0])}</td>'
            f'<td>{years_fmt(self.who["countries"][c]["all"][0])}</td></tr>' for c in rows)
        w = self.who["countries"]["WLD"]
        body = f"""
<nav class="note" aria-label="Breadcrumb"><a href="{root}">LifeClock</a> › Life expectancy by country</nav>
<h1>Life expectancy by country and age ({self.who['year']})</h1>
<p class="lede">Average life expectancy at birth in {len(self.codes)} countries, from the World Health Organization's {self.who['year']} life tables. The world average is {years_fmt(w['all'][0])} years ({years_fmt(w['female'][0])} for women, {years_fmt(w['male'][0])} for men). Open a country to see the average years left at every age. <a href="world/">World table →</a></p>
<div class="table-wrap"><table><thead><tr><th>Country</th><th>Women</th><th>Men</th><th>Everyone</th></tr></thead><tbody>{trs}</tbody></table></div>
<p class="note">Source: WHO Global Health Observatory, licensed CC BY-NC-SA 3.0 IGO. The United States page also has the SSA's single-year table, which LifeClock uses for US visitors.</p>
<p><a class="btn" href="{root}">See your own LifeClock</a></p>
"""
        self.write("life-expectancy/index.html", self.layout(
            "life-expectancy/", f"Life expectancy by country and age ({self.who['year']}) | {BRAND}",
            f"Life expectancy at birth for women and men in {len(self.codes)} countries, and the average years left at every age, from WHO life tables.",
            body, og="life-expectancy", current="life-expectancy/"))
        self.pages.append("life-expectancy/")

    def about(self):
        root = "../"
        poster = (f'<p><a class="btn" href="{attr(self.poster_url)}" rel="noopener">Get your seconds printed</a></p>' if self.poster_url else
                  "<p>Printed posters and shirts (“I had 1,580,214,377 seconds left when I bought this shirt”) are planned but not available yet.</p>")
        body = f"""
<h1>About LifeClock</h1>
<p class="lede">LifeClock turns a public life table into a live count of the seconds ahead of you, on average. It's meant as a gentle nudge to spend time on what matters, not a forecast.</p>
<h2>Method</h2>
<p>Your exact age is the time since midnight on your birthday, in years of 365.2425 days. LifeClock finds the average remaining years for that age, sex and country, adds them to the moment you press start, and counts down to that moment every second.</p>
<ul>
<li><b>United States:</b> the SSA's {self.ssa['table_year']} period life table (from the {self.ssa['trustees_report']} Trustees Report), single years of age 0 to 119, interpolated between birthdays.</li>
<li><b>Other countries and the world:</b> the WHO's {self.who['year']} life tables (“expectation of life at age x”), at ages 0, 1, 5, 10 … 85, interpolated in between. Past 85, the WHO figure is extended with the shape of the SSA table.</li>
<li><b>Prefer not to say:</b> the WHO's both-sexes table; for the US, the average of the SSA's female and male tables.</li>
</ul>
<p>These are period life tables, so they assume today's death rates stay the same for the rest of your life. The source tables refresh themselves every month from the SSA and WHO (they change about once a year).</p>
<h2>Privacy</h2>
<p>Your birthday never leaves your browser. There are no accounts, no cookies and no storage{', and visits are counted with GoatCounter, which collects no personal data' if self.goatcounter else ', and no analytics'}. Desk mode keeps your settings after the “#” in the address, which browsers never send to a server. The share card is drawn on your device.</p>
<h2>If this feels heavy</h2>
<p>{SUPPORT}</p>
<p>You can always switch to “time lived”, which counts up instead of down.</p>
<h2>Posters and shirts</h2>
{poster}
<h2>Sources and licenses</h2>
<ul>
<li><a href="{self.ssa['url']}">SSA Office of the Chief Actuary: Actuarial Life Table</a> (U.S. government work, public domain).</li>
<li><a href="{self.who['url']}">WHO Global Health Observatory: life expectancy at age x</a> (CC BY-NC-SA 3.0 IGO). LifeClock's derived tables are shared under the same license.</li>
</ul>
<p>Code: MIT, on <a href="{REPO_URL}">GitHub</a>. Found a problem? <a href="{REPO_URL}/issues/new">Open an issue</a>.</p>
<p class="note">Not affiliated with the SSA or the WHO. Not medical, financial or legal advice.</p>
"""
        self.write("about/index.html", self.layout("about/", f"About LifeClock: method, sources and privacy",
                                                   "How LifeClock estimates the seconds ahead of you from SSA and WHO life tables, and why it stores nothing.",
                                                   body, current="about/"))
        self.pages.append("about/")

    def not_found(self):
        after = self.site_url.split("://", 1)[1]
        prefix = "/" + after.split("/", 1)[1] + "/" if "/" in after else "/"
        body = f'<h1>Page not found</h1><p>That page doesn\'t exist.</p><p><a class="btn" href="{prefix}">Open LifeClock</a></p>'
        self.write("404.html", self.layout("404.html", f"Page not found | {BRAND}", "That page doesn't exist. Open LifeClock instead.",
                                           body, noindex=True, root=prefix))

    def data_files(self):
        compact = {
            "ssa": {"table_year": self.ssa["table_year"], "trustees_report": self.ssa["trustees_report"],
                    "female_ex": self.ssa["female_ex"], "male_ex": self.ssa["male_ex"]},
            "who": {"year": self.who["year"], "countries": self.who["countries"]},
            "whoAges": WHO_AGES,
            "names": {c: self.countries[c]["name"] for c in self.codes},
            "inNames": {c: self.in_name(c) for c in THE if c in self.countries},
            "iso2": {self.countries[c]["iso2"]: c for c in self.codes if self.countries[c]["iso2"]},
        }
        self.write("data/tables.json", json.dumps(compact, separators=(",", ":"), ensure_ascii=False))

    def meta_files(self):
        lastmod = self.today.isoformat()
        urls = "".join(f"<url><loc>{self.url(p)}</loc><lastmod>{lastmod}</lastmod></url>\n" for p in self.pages)
        self.write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n')
        self.write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {self.site_url}/sitemap.xml\n")
        self.write(f"{INDEXNOW_KEY}.txt", INDEXNOW_KEY)
        self.write(".nojekyll", "")
        (self.out / "urls.txt").write_text("".join(self.url(p) + "\n" for p in self.pages), encoding="utf-8")

    def build(self):
        if self.out.exists():
            shutil.rmtree(self.out)
        shutil.copytree(ROOT / "site" / "assets", self.out / "assets")
        app = self.out / "assets" / "app.js"
        app.write_text(app.read_text(encoding="utf-8").replace('from "./core.js"', f'from "./core.js?v={self.ver}"')
                       .replace('import("./selftest.js")', f'import("./selftest.js?v={self.ver}")'), encoding="utf-8")
        shutil.copy(ROOT / "site" / "favicon.svg", self.out / "favicon.svg")
        self.home()
        self.billion()
        self.desk()
        self.hub()
        self.country_page("WLD")
        for c in self.codes:
            self.country_page(c)
        self.about()
        self.not_found()
        self.data_files()
        self.meta_files()
        return self


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    today = dt.date.fromisoformat(os.environ["BUILD_DATE"]) if os.environ.get("BUILD_DATE") else dt.datetime.now(dt.timezone.utc).date()
    site = Site(Path(args.out), today).build()
    print(f"built {len(site.pages)} pages into {args.out}")


if __name__ == "__main__":
    main()
