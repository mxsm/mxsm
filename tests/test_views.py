import io
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import render_views
import update_profile
import view_counter


class ProfileViewsTest(unittest.TestCase):
    now = datetime(2026, 11, 25, tzinfo=timezone.utc)
    legacy = "https://count.getloli.com/get/@:mxsm?theme=gelbooru-h"
    camo = "https://camo.githubusercontent.com/" + "a" * 64 + "/" + legacy.encode().hex()

    def profile_html(self):
        return io.BytesIO(f'''<article class="markdown-body">
            <img src="https://github.com/mxsm/mxsm/raw/main/resource/generated/profile-views.svg" />
            <img data-canonical-src="{self.legacy}" src="{self.camo}" width="1" height="1" alt="" />
            <img data-canonical-src="{self.legacy.replace(':mxsm', ':other')}" src="{self.camo}-other" />
            </article>'''.encode())

    def counter_svg(self, refs):
        uses = "".join(f'<use xlink:href="{ref}" x="{index * 60}" />' for index, ref in enumerate(refs))
        return io.BytesIO(f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs><image id="0" /><image id="3" /><image id="4" /></defs><g>{uses}</g></svg>'''.encode())

    def test_blocked_series_reads_profile_counter_digits_in_order(self):
        forbidden = HTTPError(self.legacy, 403, "Forbidden", {}, io.BytesIO())
        self.addCleanup(forbidden.close)
        svg = self.counter_svg(["#0", "#0", "#3", "#0", "#0", "#3", "#4"])
        with patch.object(view_counter, "urlopen", side_effect=[forbidden, self.profile_html(), svg]) as fetch:
            snapshot = view_counter.fetch_views("mxsm", self.now)
        self.assertEqual((snapshot["count"], snapshot["source"]), (30034, "profile-counter-image"))
        self.assertEqual([call.args[0] for call in fetch.call_args_list[1:]], ["https://github.com/mxsm", self.camo])

    def test_bad_displayed_digit_preserves_published_counter(self):
        with TemporaryDirectory() as folder:
            output = Path(folder)
            previous = {"owner": "mxsm", "count": 30003, "updated_at": self.now.isoformat()}
            update_profile.publish(output, "profile-views", previous, render_views.render_views(30003))
            files = {p: p.read_bytes() for p in output.iterdir()}
            forbidden = HTTPError(self.legacy, 403, "Forbidden", {}, io.BytesIO())
            self.addCleanup(forbidden.close)
            svg = self.counter_svg(["#3", "#4", "#other"])
            with patch.object(view_counter, "urlopen", side_effect=[forbidden, self.profile_html(), svg]):
                with self.assertRaisesRegex(ValueError, "digit sequence"):
                    update_profile.update("profile-views", "mxsm", self.now, output)
            self.assertEqual({p: p.read_bytes() for p in output.iterdir()}, files)

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
