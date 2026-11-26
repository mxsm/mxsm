import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import render_views
import update_profile
import view_counter


class ProfileViewsTest(unittest.TestCase):
    now = datetime(2026, 11, 25, tzinfo=timezone.utc)

    def test_legacy_counter_name_and_read_only_total(self):
        for total in (0, 30003):
            with self.subTest(total=total):
                response = io.BytesIO(json.dumps({"name": ":mxsm", "total": total}).encode())
                with patch.object(view_counter, "urlopen", return_value=response) as fetch:
                    snapshot = view_counter.fetch_views("mxsm", self.now)
                self.assertEqual(snapshot["count"], total)
                request = fetch.call_args.args[0]
                url = urlsplit(request.full_url)
                self.assertEqual((request.get_method(), url.scheme, url.netloc),
                                 ("GET", "https", "count.getloli.com"))
                self.assertEqual(unquote(url.path), "/api/stats/series/:mxsm")

    def test_invalid_upstream_total_or_counter_name(self):
        for name, total in [("mxsm", 30003), (":mxsm", -1), (":mxsm", True),
                            (":mxsm", 1.5), (":mxsm", "30003")]:
            with self.subTest(name=name, total=total):
                response = io.BytesIO(json.dumps({"name": name, "total": total}).encode())
                with patch.object(view_counter, "urlopen", return_value=response), self.assertRaises(ValueError):
                    view_counter.fetch_views("mxsm", self.now)

    def test_preserve_snapshot_on_failure_and_render_offline(self):
        snapshot = {"owner": "mxsm", "count": 30003, "updated_at": self.now.isoformat()}
        with TemporaryDirectory() as folder, patch.object(update_profile, "fetch_views") as fetch:
            output = Path(folder)
            fetch.return_value = snapshot
            update_profile.update("profile-views", "mxsm", self.now, output)
            svg = output / "profile-views.svg"
            data = output / "profile-views.json"
            original = (svg.read_bytes(), data.read_bytes())

            fetch.side_effect = [OSError("counter unavailable"), dict(snapshot, count=29999)]
            for error in (OSError, ValueError):
                with self.assertRaises(error):
                    update_profile.update("profile-views", "mxsm", self.now, output)
                self.assertEqual((svg.read_bytes(), data.read_bytes()), original)

            fetch.reset_mock()
            svg.unlink()
            update_profile.update("profile-views", "mxsm", self.now, output, render_only=True)
            fetch.assert_not_called()
            self.assertEqual((svg.read_bytes(), data.read_bytes()), original)

    def test_every_digit_selects_its_own_lion_and_labels_the_drum(self):
        href = "{http://www.w3.org/1999/xlink}href"
        for count, digits in [(0, "0000000"), (30003, "0030003"), (1023456789, "1023456789")]:
            with self.subTest(count=count):
                root = ET.fromstring(render_views.render_views(count))
                self.assertIn(f"{count:,}", root.findtext("{*}title"))
                lions = root.findall("{*}defs/{*}image")
                self.assertCountEqual([lion.get("id") for lion in lions],
                                      [f"lion-{digit}" for digit in set(digits)])
                self.assertEqual(len({lion.get(href) for lion in lions}), len(set(digits)))
                for lion in lions:
                    digit = lion.get("id").removeprefix("lion-")
                    self.assertEqual(lion.get(href), render_views.artwork(f"profile-views/{digit}.png"))

                drums = [group for group in root.iterfind(".//{*}g")
                         if any(use.get(href) == "#drum" for use in group.findall("{*}use"))]
                self.assertEqual("".join(group.findtext("{*}text") for group in drums), digits)
                for group, digit in zip(drums, digits):
                    self.assertIn(f"#lion-{digit}", [use.get(href) for use in group.findall("{*}use")])


if __name__ == "__main__":
    unittest.main()
