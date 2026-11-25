import json
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import github_stats
import render_cards
import update_profile


class ProfileCardsTest(unittest.TestCase):
    def test_month_boundary_retry_and_offline_reproduction(self):
        def sample(owner, now):
            return {"owner": owner, "updated_at": now.isoformat(), "languages": [
                {"name": "Rust", "bytes": 90, "color": "#dea584"},
                {"name": "A&B", "bytes": 10, "color": "#123456"},
            ]}

        with TemporaryDirectory() as folder, patch("update_profile.fetch_languages", side_effect=sample) as fetch:
            output = Path(folder)
            start = datetime(2026, 11, 25, tzinfo=timezone.utc)
            update_profile.update("languages", "mxsm", start, output)
            before = {p: p.read_bytes() for p in output.iterdir()}
            update_profile.update("languages", "mxsm", start + timedelta(days=1), output)
            self.assertEqual(fetch.call_count, 1)
            self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))

            december = start.replace(month=12, day=2)
            fetch.side_effect = RuntimeError("API unavailable")
            with self.assertRaises(RuntimeError):
                update_profile.update("languages", "mxsm", december, output)
            self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))
            fetch.side_effect = sample
            update_profile.update("languages", "mxsm", december, output)
            snapshot = json.loads((output / "languages.json").read_bytes())
            self.assertEqual(snapshot["updated_at"], december.isoformat())

            svg = output / "languages.svg"
            original = svg.read_bytes()
            svg.unlink()
            update_profile.update("languages", "mxsm", december, output, render_only=True)
            self.assertEqual(svg.read_bytes(), original)
            self.assertEqual(fetch.call_count, 3)
            root = ET.fromstring(original)
            self.assertIn("A&B", "".join(root.itertext()))

    def test_partial_calendar_weeks_and_account_creation(self):
        start = date(2026, 11, 21)  # Saturday; Sunday begins the second GitHub week.
        end = start + timedelta(days=2)
        calendar = [{"contributionDays": [
            {"date": "2026-11-20", "contributionCount": 99},
            {"date": "2026-11-22", "contributionCount": 3},
            {"date": "2026-11-23", "contributionCount": 4},
            {"date": "2026-11-24", "contributionCount": 99},
        ]}]
        days = github_stats.calendar_days(calendar, start, end, start + timedelta(days=1))
        self.assertEqual(render_cards.weeks_from(days), [(date(2026, 11, 15), 0), (date(2026, 11, 22), 7)])
        with self.assertRaisesRegex(ValueError, "2026-11-21"):
            github_stats.calendar_days(calendar, start, end, start)

    def test_failed_pair_install_restores_the_previous_image(self):
        with TemporaryDirectory() as folder:
            output = Path(folder)
            update_profile.publish(output, "languages", {"version": 1}, "<svg/>")
            replace = Path.replace

            def fail_snapshot(source, dest):
                if source.name == "languages.json":
                    raise OSError("snapshot could not be installed")
                return replace(source, dest)

            with patch.object(Path, "replace", fail_snapshot), self.assertRaises(OSError):
                update_profile.publish(output, "languages", {"version": 2}, "<svg><g/></svg>")
            self.assertEqual((output / "languages.svg").read_text(), "<svg/>")
            self.assertEqual(json.loads((output / "languages.json").read_bytes()), {"version": 1})

    def test_poles_share_one_baseline_and_zero_is_not_a_column(self):
        amounts = [0, 88, 51, 21, 43, 32, 27]
        days = [(date(2026, 11, 19) + timedelta(days=i), n) for i, n in enumerate(amounts)]
        poles = ET.fromstring("<g>" + render_cards.daily_poles(days) + "</g>")
        self.assertEqual(len(poles), 7)
        self.assertIsNone(poles[0].find("g"))
        for group, (day, count) in zip(poles, days):
            self.assertIn(day.isoformat(), group.findtext("title"))
            self.assertEqual(group.findtext("text"), str(count))
            if count:
                stem, _, cap = group.findall("g/rect")
                total_height = float(stem.get("height")) + float(cap.get("height"))
                self.assertAlmostEqual(total_height, 206 * count / 88, places=2)
        flat = {d.isoformat(): 0 for d, _ in days}
        self.assertNotIn("nan", render_cards.skyline(flat).lower())
        self.assertNotIn("url(#lacquer)", render_cards.daily_poles([(d, 0) for d, _ in days]))

    def test_paginated_languages_and_display_denominator(self):
        def edge(name, size):
            return {"node": {"name": name, "color": "#abcdef"}, "size": size}

        def page(items, has_more=False, key="edges"):
            return {key: items, "pageInfo": {"hasNextPage": has_more, "endCursor": "next"}}

        first = {"name": "one", "languages": page([edge("Rust", 20), edge("HTML", 500)], True)}
        second = {"name": "two", "languages": page([edge("Rust", 40), edge("Java", 10)])}
        responses = [
            {"user": {"repositories": page([first], True, "nodes")}},
            {"repository": {"languages": page([edge("Python", 30)])}},
            {"user": {"repositories": page([second], key="nodes")}},
        ]
        with patch("github_stats.graphql", side_effect=responses):
            snapshot = github_stats.fetch_languages("mxsm", datetime.now(timezone.utc))
        self.assertEqual([(r["name"], r["bytes"]) for r in snapshot["languages"]],
                         [("Rust", 60), ("Python", 30), ("Java", 10)])
        root = ET.fromstring(render_cards.language_card(snapshot))
        strip = root.find(".//{*}g[@clip-path='url(#strip)']")
        self.assertEqual([round(float(rect.get("width")) / 752, 2) for rect in strip], [.60, .30, .10])


if __name__ == "__main__":
    unittest.main()
