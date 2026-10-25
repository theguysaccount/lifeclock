"""Life tables: parsing the sources, validating them, refreshing safely, and the reference model."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import lifetables as L  # noqa: E402
import reference as R  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


class ParseTest(unittest.TestCase):
    def test_ssa_page(self):
        ssa = L.parse_ssa((FIX / "ssa-table4c6.html").read_text())
        self.assertEqual((ssa["table_year"], ssa["trustees_report"]), (2023, 2026))
        self.assertEqual(len(ssa["female_ex"]), 120)
        self.assertEqual(ssa["female_ex"][0], 81.06)
        self.assertEqual(ssa["male_ex"][30], 47.5)
        self.assertEqual(ssa["male_qx"][0], 0.006015)
        self.assertEqual(L.validate_ssa(ssa), [])

    def test_ssa_layout_change_is_rejected(self):
        page = (FIX / "ssa-table4c6.html").read_text().replace("<td> 81.06</td>", "", 1)
        with self.assertRaises(ValueError):
            L.parse_ssa(page)
        with self.assertRaises(ValueError):
            L.parse_ssa("<html>Access Denied</html>")

    def test_who_rows(self):
        rows = json.loads((FIX / "gho-jpn-2021.json").read_text())["value"]
        who = L.parse_who(rows, 2021)
        self.assertEqual(set(who), {"JPN"})
        self.assertEqual(set(who["JPN"]), {"all", "female", "male"})
        self.assertEqual(len(who["JPN"]["female"]), 19)
        self.assertGreater(who["JPN"]["female"][0], who["JPN"]["male"][0])
        self.assertEqual(L.parse_who(rows, 2020), {})


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.who = json.loads((ROOT / "data" / "who.json").read_text())
        self.ssa = json.loads((ROOT / "data" / "ssa.json").read_text())

    def test_committed_tables_are_valid(self):
        self.assertEqual(L.validate_who(self.who), [])
        self.assertEqual(L.validate_ssa(self.ssa), [])
        self.assertGreaterEqual(len(self.who["countries"]), 180)

    def test_scrambled_tables_are_rejected(self):
        bad = json.loads(json.dumps(self.who))
        bad["countries"]["JPN"]["all"] = list(reversed(bad["countries"]["JPN"]["all"]))
        self.assertTrue(L.validate_who(bad))
        del bad["countries"]["WLD"]
        self.assertTrue(any("world" in p for p in L.validate_who(bad)))
        broken = dict(self.ssa, female_ex=self.ssa["female_ex"][:50])
        self.assertTrue(L.validate_ssa(broken))


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for f in ("who.json", "ssa.json"):
            shutil.copy(ROOT / "data" / f, self.tmp / f)
        self.orig, L.DATA = L.DATA, self.tmp
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()

    def tearDown(self):
        self.quiet.__exit__(None, None, None)
        L.DATA = self.orig
        shutil.rmtree(self.tmp)

    def who_ok(self):
        return json.loads((ROOT / "data" / "who.json").read_text())

    def test_ssa_blocked_keeps_the_committed_table(self):
        before = (self.tmp / "ssa.json").read_text()

        def blocked():
            raise OSError("HTTP Error 403: Forbidden")

        self.assertEqual(L.refresh(self.who_ok, blocked), 0)
        self.assertEqual((self.tmp / "ssa.json").read_text(), before)

    def test_new_ssa_table_is_written(self):
        page = (FIX / "ssa-table4c6.html").read_text().replace("<td> 81.06</td>", "<td> 81.16</td>", 1)
        self.assertEqual(L.refresh(self.who_ok, lambda: page), 0)
        self.assertEqual(json.loads((self.tmp / "ssa.json").read_text())["female_ex"][0], 81.16)

    def test_bad_who_data_fails_without_writing(self):
        before = (self.tmp / "who.json").read_text()
        bad = self.who_ok()
        bad["countries"] = {"USA": bad["countries"]["USA"]}
        self.assertEqual(L.refresh(lambda: bad, lambda: (FIX / "ssa-table4c6.html").read_text()), 1)
        self.assertEqual((self.tmp / "who.json").read_text(), before)

    def test_who_outage_fails(self):
        def down():
            raise OSError("timed out")

        self.assertEqual(L.refresh(down, lambda: (FIX / "ssa-table4c6.html").read_text()), 1)


class ModelTest(unittest.TestCase):
    t = R.load()

    def test_us_uses_ssa_single_years(self):
        self.assertAlmostEqual(R.remaining_years(self.t, "USA", "female", 30), 52.08)
        self.assertAlmostEqual(R.remaining_years(self.t, "USA", "male", 30.5), (47.5 + 46.6) / 2)
        self.assertAlmostEqual(R.remaining_years(self.t, "USA", "all", 30), (52.08 + 47.5) / 2)

    def test_who_interpolates_between_age_groups(self):
        jpn = self.t["who"]["countries"]["JPN"]["male"]
        self.assertAlmostEqual(R.remaining_years(self.t, "JPN", "male", 40), jpn[9])
        self.assertAlmostEqual(R.remaining_years(self.t, "JPN", "male", 42.5), (jpn[9] + jpn[10]) / 2)
        self.assertAlmostEqual(R.remaining_years(self.t, "JPN", "male", 3), jpn[1] + (jpn[2] - jpn[1]) / 2)

    def test_past_85_follows_the_ssa_shape(self):
        e85 = self.t["who"]["countries"]["JPN"]["female"][-1]
        ssa = self.t["ssa"]["female_ex"]
        self.assertAlmostEqual(R.remaining_years(self.t, "JPN", "female", 90), e85 * ssa[90] / ssa[85])

    def test_unknown_country_uses_the_world(self):
        self.assertEqual(R.remaining_years(self.t, "ZZZ", "all", 20), R.remaining_years(self.t, "WLD", "all", 20))

    def test_always_positive(self):
        for age in (0, 50, 100, 119, 125):
            self.assertGreater(R.remaining_years(self.t, "KIR", "male", age), 0)


if __name__ == "__main__":
    unittest.main()
