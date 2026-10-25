"""Render the 1200x630 Open Graph cards in site/assets/og/ with headless Chrome.

    python3 scripts/og.py

Needs Google Chrome or Chromium; set CHROME to its path if it isn't found.
"""
import html
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "assets" / "og"
CHROME = os.environ.get("CHROME") or next(
    (c for c in [shutil.which("google-chrome"), shutil.which("chromium"),
                 "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"] if c and Path(c).exists()), None)

CARD = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:1200px;height:630px;overflow:hidden}}
body{{background:linear-gradient(135deg,#14161f,#2a2335);color:#f1edf6;font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 display:flex;flex-direction:column;justify-content:space-between;padding:60px 72px;box-sizing:border-box}}
.top{{font-size:36px;font-weight:700;color:#f2b15b}}
.big{{font:800 118px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:-.03em;color:#fff}}
h1{{font-size:46px;line-height:1.15;margin:18px 0 0;font-weight:650;max-width:1000px}}
p{{font-size:28px;color:#b4accb;margin:0}}
</style></head><body>
<div class="top">◷ LifeClock</div>
<div><div class="big">{big}</div><h1>{title}</h1></div>
<p>{sub}</p>
</body></html>"""


def render(name, big, title, sub, work):
    page = work / f"{name}.html"
    page.write_text(CARD.format(big=html.escape(big), title=html.escape(title), sub=html.escape(sub)), encoding="utf-8")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                    f"--user-data-dir={work / 'profile'}", "--window-size=1200,630", "--virtual-time-budget=2000",
                    f"--screenshot={OUT / (name + '.png')}", page.as_uri()], check=True, capture_output=True)
    print(OUT / f"{name}.png")


def main():
    if not CHROME:
        raise SystemExit("Chrome not found; set CHROME")
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    try:
        render("home", "1,453,133,934", "How many seconds are ahead of you?", "A free, private life clock from SSA and WHO life tables. An average, not a prediction.", work)
        render("billion", "1,000,000,000", "When will you be a billion seconds old?", "About 31 years and 8 months. Find your exact date.", work)
        render("life-expectancy", "83.9 · 78.5 · 73.3", "Life expectancy by country and age", "Average years left at every age in 185 countries, from WHO life tables.", work)
    finally:
        shutil.rmtree(work)


if __name__ == "__main__":
    main()
