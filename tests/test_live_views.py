import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api import profile_views


class LiveViewsTest(unittest.TestCase):
    def request(self, method):
        start = Mock()
        body = b"".join(profile_views.app({"REQUEST_METHOD": method}, start))
        status, headers = start.call_args.args
        return status, dict(headers), body

    @patch.object(profile_views, "original_counter_image", return_value="counter.svg")
    @patch.object(profile_views, "read_counter_image", side_effect=[30009, 30010])
    def test_each_get_renders_one_new_total_even_across_a_carry(self, read, resolve):
        for count in ("30,009", "30,010"):
            status, headers, svg = self.request("GET")
            self.assertEqual(status, "200 OK")
            self.assertIn("no-store", headers["Cache-Control"])
            self.assertEqual(ElementTree.fromstring(svg).findtext("{*}title"), f"Profile Views · {count}")
        self.assertEqual(read.call_count, 2)
        self.assertEqual(resolve.call_count, 2)

    @patch.object(profile_views, "read_counter_image")
    @patch.object(profile_views, "original_counter_image")
    def test_head_and_unsupported_methods_do_not_record_views(self, resolve, read):
        self.assertEqual(self.request("HEAD")[::2], ("200 OK", b""))
        self.assertEqual(self.request("POST")[::2], ("405 Method Not Allowed", b""))
        resolve.assert_not_called()
        read.assert_not_called()

    @patch.object(profile_views, "original_counter_image", return_value="counter.svg")
    @patch.object(profile_views, "read_counter_image", side_effect=TimeoutError("upstream timed out"))
    def test_ambiguous_upstream_failure_does_not_retry_and_double_count(self, read, _resolve):
        status, headers, _body = self.request("GET")
        self.assertEqual(status, "503 Service Unavailable")
        self.assertIn("no-store", headers["Cache-Control"])
        read.assert_called_once()
