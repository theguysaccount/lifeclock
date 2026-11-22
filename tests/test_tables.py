"""Life tables: parsing the sources, validating them, refreshing safely, and the reference model."""
import contextlib
import datetime as dt
import io
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

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

    def test_committed_refresh_state_is_readable(self):
        # Either value is fine here: the refresh job runs these tests while a streak may be running.
        since = json.loads((ROOT / "data" / L.STATE_FILE).read_text())["who_failing_since"]
        if since is not None:
            dt.date.fromisoformat(since)


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for f in ("who.json", "ssa.json"):
            shutil.copy(ROOT / "data" / f, self.tmp / f)
        self.orig, L.DATA = L.DATA, self.tmp
        self.out = io.StringIO()
        self.quiet = contextlib.redirect_stdout(self.out)
        self.quiet.__enter__()
        sleeping = mock.patch.object(L.time, "sleep")
        self.sleep = sleeping.start()
        self.addCleanup(sleeping.stop)

    def tearDown(self):
        self.quiet.__exit__(None, None, None)
        L.DATA = self.orig
        shutil.rmtree(self.tmp)

    def who_ok(self):
        return json.loads((ROOT / "data" / "who.json").read_text())

    def ssa_page(self):
        return (FIX / "ssa-table4c6.html").read_text()

    def failing_since(self, days_ago):
        """Pretend WHO refreshes have failed on every run since days_ago (relative to the real date)."""
        since = (L.utc_today() - dt.timedelta(days=days_ago)).isoformat()
        L.write_state({"who_failing_since": since})
        return since

    def streak(self):
        return L.read_state().get("who_failing_since")

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
        # Since 2026-11-22 a bad download fails the run only once WHO refreshes have failed for
        # WHO_STALE_AFTER_DAYS; until then it's a warning (next test). It's never written.
        before = (self.tmp / "who.json").read_text()
        bad = self.who_ok()
        bad["countries"] = {"USA": bad["countries"]["USA"]}
        self.failing_since(L.WHO_STALE_AFTER_DAYS)
        self.assertEqual(L.refresh(lambda: bad, lambda: (FIX / "ssa-table4c6.html").read_text()), 1)
        self.assertEqual((self.tmp / "who.json").read_text(), before)

    def test_bad_who_data_warns_at_first_without_writing(self):
        before = (self.tmp / "who.json").read_text()
        bad = self.who_ok()
        bad["countries"] = {"USA": bad["countries"]["USA"]}
        self.assertEqual(L.refresh(lambda: bad, self.ssa_page), 0)
        self.assertEqual((self.tmp / "who.json").read_text(), before)
        self.assertIn("failed validation", self.out.getvalue())
        self.assertEqual(self.streak(), L.utc_today().isoformat())
        self.sleep.assert_not_called()  # a complete answer that fails validation isn't asked for again

    def test_who_outage_fails(self):
        # Since 2026-11-22 only an outage that has lasted WHO_STALE_AFTER_DAYS fails the run.
        def down():
            raise OSError("timed out")

        self.failing_since(L.WHO_STALE_AFTER_DAYS)
        self.assertEqual(L.refresh(down, lambda: (FIX / "ssa-table4c6.html").read_text()), 1)
        self.assertIn("::error::WHO life tables not updated", self.out.getvalue())

    def test_who_500_keeps_the_committed_tables_and_passes(self):
        """The 2026-11-03 failure: WHO answers 500 on every try."""
        before = (self.tmp / "who.json").read_text()
        tries = []

        def server_error():
            tries.append(1)
            raise urllib.error.HTTPError(L.GHO, 500, "Internal Server Error", None, None)

        self.assertEqual(L.refresh(server_error, self.ssa_page), 0)
        self.assertEqual(len(tries), len(L.WHO_PAUSES) + 1)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], list(L.WHO_PAUSES))
        self.assertEqual((self.tmp / "who.json").read_text(), before)
        self.assertEqual(self.streak(), L.utc_today().isoformat())
        out = self.out.getvalue()
        self.assertIn("::warning::WHO life tables not updated, keeping the committed ones: HTTP Error 500", out)
        self.assertNotIn("::error::", out)

    def test_who_500_then_an_answer(self):
        answers = [urllib.error.HTTPError(L.GHO, 500, "Internal Server Error", None, None), self.who_ok()]

        def flaky():
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        self.assertEqual(L.refresh(flaky, self.ssa_page), 0)
        self.assertEqual(self.sleep.call_count, 1)
        self.assertIsNone(self.streak())
        self.assertNotIn("WHO life tables not updated", self.out.getvalue())

    def test_who_failures_pass_inside_the_limit_and_keep_the_start_date(self):
        def down():
            raise OSError("timed out")

        since = self.failing_since(L.WHO_STALE_AFTER_DAYS - 1)
        self.assertEqual(L.refresh(down, self.ssa_page), 0)
        self.assertEqual(self.streak(), since)

    def test_a_good_refresh_ends_the_streak(self):
        self.failing_since(L.WHO_STALE_AFTER_DAYS + 30)
        self.assertEqual(L.refresh(self.who_ok, self.ssa_page), 0)
        self.assertIsNone(self.streak())
        self.assertIn("this one worked", self.out.getvalue())

    def test_who_404_is_not_asked_again(self):
        tries = []

        def gone():
            tries.append(1)
            raise urllib.error.HTTPError(L.GHO, 404, "Not Found", None, None)

        self.assertEqual(L.refresh(gone, self.ssa_page), 0)
        self.assertEqual(len(tries), 1)
        self.sleep.assert_not_called()

    def test_retries_stop_when_time_runs_out(self):
        clock = iter([0, L.WHO_RETRY_UNTIL - L.WHO_PAUSES[0] + 1])
        tries = []

        def down():
            tries.append(1)
            raise OSError("timed out")

        with self.assertRaises(OSError):
            L.who_with_retries(down, clock=lambda: next(clock))
        self.assertEqual(len(tries), 1)
        self.sleep.assert_not_called()

    def test_ssa_403_is_a_notice(self):
        def refused():
            raise urllib.error.HTTPError(L.SSA_URL, 403, "Forbidden", None, None)

        self.assertEqual(L.refresh(self.who_ok, refused), 0)
        self.assertIn("::notice::SSA table not updated: ssa.gov answered 403", self.out.getvalue())
        self.assertNotIn("::warning::SSA", self.out.getvalue())

    def test_a_missing_state_file_is_recreated(self):
        self.assertFalse((self.tmp / L.STATE_FILE).exists())
        self.assertEqual(L.refresh(self.who_ok, self.ssa_page), 0)
        state = json.loads((self.tmp / L.STATE_FILE).read_text())
        self.assertIsNone(state["who_failing_since"])
        self.assertIn("about", state)


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
