import datetime as dt
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
os.environ["CODEX_DASHBOARD_LIB_DIR"] = str(REPOSITORY_ROOT / "backend")

loader = importlib.machinery.SourceFileLoader(
    "codex_dashboard_data",
    str(REPOSITORY_ROOT / "codex-quota" / "codex-dashboard-data"),
)
spec = importlib.util.spec_from_loader(loader.name, loader)
dashboard_data = importlib.util.module_from_spec(spec)
loader.exec_module(dashboard_data)


class OfficialTokenActivityTests(unittest.TestCase):
    def setUp(self):
        self.today = dt.datetime(
            2026,
            7,
            30,
            12,
            tzinfo=dt.timezone.utc,
        )

    def _build(self, buckets):
        return dashboard_data.OfficialTokenActivity(self.today).build({
            "summary": {},
            "dailyUsageBuckets": buckets,
        })

    def _current_calendar_day(self, usage):
        current_month = next(
            month
            for month in usage["calendar_months"]
            if month["key"] == "2026-07"
        )
        return next(
            item
            for item in current_month["days"]
            if item["day"] == 30
        )

    def test_missing_current_day_is_pending_without_losing_known_totals(self):
        usage = self._build([
            {"startDate": "2026-07-29", "tokens": 125},
        ])

        self.assertIsNone(usage["today"])
        self.assertFalse(usage["current_day_available"])
        self.assertIsNone(usage["days"][-1]["tokens"])
        self.assertIsNone(self._current_calendar_day(usage)["tokens"])
        self.assertEqual(usage["seven_days"], 125)
        self.assertEqual(usage["ninety_days"], 125)

    def test_explicit_zero_current_day_remains_a_real_zero(self):
        usage = self._build([
            {"startDate": "2026-07-29", "tokens": 125},
            {"startDate": "2026-07-30", "tokens": 0},
        ])

        self.assertEqual(usage["today"], 0)
        self.assertTrue(usage["current_day_available"])
        self.assertEqual(usage["days"][-1]["tokens"], 0)
        self.assertEqual(self._current_calendar_day(usage)["tokens"], 0)
        self.assertEqual(usage["seven_days"], 125)
        self.assertEqual(usage["ninety_days"], 125)


if __name__ == "__main__":
    unittest.main()
