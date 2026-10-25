"""The built site: pages, links, metadata, data files and the optional keys."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://example.org/clock"


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.scripts, self.meta, self.ld, self.title = [], [], {}, [], ""
        self._t = self._ld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("a", "link") and a.get("href"):
            self.links.append((a.get("rel", ""), a["href"]))
        if tag == "script":
            if a.get("src"):
                self.scripts.append(a["src"])
            self._ld = a.get("type") == "application/ld+json"
        if tag == "meta" and (a.get("name") or a.get("property")):
            self.meta[a.get("name") or a.get("property")] = a.get("content", "")
        self._t = tag == "title"

    def handle_endtag(self, tag):
        self._t = False
        if tag == "script":
            self._ld = False

    def handle_data(self, data):
        if self._t:
            self.title += data
        if self._ld:
            self.ld.append(data)


def build(out, **env):
    e = dict(os.environ, SITE_URL=SITE, BUILD_DATE="2026-10-25", GOATCOUNTER_URL="", POSTER_URL="")
    e.update(env)
    subprocess.run([sys.executable, str(ROOT / "pipeline" / "build.py"), "--out", str(out)], check=True, env=e, capture_output=True)


class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(tempfile.mkdtemp()) / "dist"
        build(cls.out)
        cls.pages = {}
        for f in cls.out.rglob("*.html"):
            p = Page()
            p.feed(f.read_text(encoding="utf-8"))
            cls.pages[f.relative_to(cls.out).as_posix()] = p
        cls.countries = json.loads((ROOT / "data" / "countries.json").read_text())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out.parent)

    def test_pages(self):
        for name in ("index.html", "billion-seconds/index.html", "desk/index.html", "about/index.html", "404.html",
                     "life-expectancy/index.html", "life-expectancy/world/index.html", "life-expectancy/japan/index.html",
                     "life-expectancy/united-states/index.html"):
            self.assertIn(name, self.pages)
        country_pages = [n for n in self.pages if n.startswith("life-expectancy/") and n.count("/") == 2]
        self.assertEqual(len(country_pages), len(self.countries) + 1)

    def test_sitemap(self):
        locs = re.findall(r"<loc>([^<]+)</loc>", (self.out / "sitemap.xml").read_text())
        self.assertEqual(len(locs), len(self.countries) + 1 + 4)
        self.assertNotIn(f"{SITE}/desk/", locs)
        for loc in locs:
            self.assertTrue((self.out / loc[len(SITE) + 1:] / "index.html").exists(), loc)
        self.assertEqual((self.out / "urls.txt").read_text().split(), locs)

    def test_internal_links_resolve(self):
        for name, page in self.pages.items():
            if name == "404.html":
                continue
            for rel, href in page.links + [("", s) for s in page.scripts]:
                if href.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target = urlparse(urljoin(f"http://x/{name}", href)).path.lstrip("/")
                if target == "" or target.endswith("/"):
                    target += "index.html"
                with self.subTest(page=name, href=href):
                    self.assertTrue((self.out / target).exists(), target)

    def test_metadata(self):
        for name, page in self.pages.items():
            with self.subTest(name):
                self.assertTrue(page.title.strip())
                self.assertGreater(len(page.meta.get("description", "")), 30)
                self.assertTrue(page.meta["og:image"].startswith(SITE + "/assets/og/"))
                self.assertTrue((self.out / page.meta["og:image"][len(SITE) + 1:]).exists(), page.meta["og:image"])
                canon = [h for rel, h in page.links if rel == "canonical"]
                self.assertEqual(len(canon), 1)
                for block in page.ld:
                    json.loads(block)
                self.assertEqual(page.meta.get("robots") == "noindex", name in ("desk/index.html", "404.html"))
        titles = [p.title for n, p in self.pages.items() if n not in ("desk/index.html", "404.html")]
        self.assertEqual(len(titles), len(set(titles)))

    def test_support_and_privacy_on_every_page(self):
        for name in self.pages:
            html = (self.out / name).read_text()
            with self.subTest(name):
                self.assertIn("988", html)
                self.assertIn("findahelpline.com", html)
                self.assertIn("not predictions", html)

    def test_no_third_party_scripts_by_default(self):
        for name, page in self.pages.items():
            for src in page.scripts:
                self.assertFalse(src.startswith(("http", "//")), f"{name}: {src}")

    def test_country_page_numbers(self):
        html = (self.out / "life-expectancy" / "japan" / "index.html").read_text()
        who = json.loads((ROOT / "data" / "who.json").read_text())
        self.assertIn(f"{who['countries']['JPN']['all'][0]:.1f} years", html)
        self.assertIn("ranks 1st of", html)
        us = (self.out / "life-expectancy" / "united-states" / "index.html").read_text()
        self.assertIn("Life expectancy in the United States", us)
        self.assertEqual(us.count("<tr><td>"), 19 + 120)

    def test_tables_json(self):
        t = json.loads((self.out / "data" / "tables.json").read_text())
        self.assertEqual(len(t["ssa"]["female_ex"]), 120)
        self.assertEqual(t["whoAges"][-1], 85)
        self.assertIn("WLD", t["who"]["countries"])
        self.assertEqual(t["iso2"]["JP"], "JPN")
        self.assertEqual(t["inNames"]["USA"], "the United States")
        self.assertLess((self.out / "data" / "tables.json").stat().st_size, 150_000)

    def test_versioned_assets(self):
        ver = re.search(r"app\.js\?v=([0-9a-f]{10})", (self.out / "index.html").read_text()).group(1)
        self.assertIn(f'from "./core.js?v={ver}"', (self.out / "assets" / "app.js").read_text())

    def test_optional_keys(self):
        out = Path(tempfile.mkdtemp()) / "d"
        try:
            build(out, GOATCOUNTER_URL="https://x.goatcounter.com/count", POSTER_URL="https://example.org/poster")
            home = (out / "index.html").read_text()
            self.assertIn('data-goatcounter="https://x.goatcounter.com/count"', home)
            self.assertIn("https://example.org/poster", home)
            self.assertIn("https://example.org/poster", (out / "about" / "index.html").read_text())
        finally:
            shutil.rmtree(out.parent)


if __name__ == "__main__":
    unittest.main()
