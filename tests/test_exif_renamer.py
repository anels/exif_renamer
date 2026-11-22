import datetime
import os
import tempfile
import unittest
from unittest import mock

import exif_renamer
from exif_renamer import _parse_creation_time, sanitize_filename


class TestParseCreationTime(unittest.TestCase):
    def test_utc_z_converts_to_local(self):
        dt = _parse_creation_time("2024-06-01T12:00:00Z")
        expected = datetime.datetime(
            2024, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc
        ).astimezone()
        self.assertEqual(dt, expected)

    def test_offset_is_converted(self):
        dt = _parse_creation_time("2024-06-01T12:00:00+02:00")
        expected = datetime.datetime(
            2024, 6, 1, 12, 0, 0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=2)),
        ).astimezone()
        self.assertEqual(dt, expected)

    def test_naive_stays_naive(self):
        dt = _parse_creation_time("2024-06-01T12:00:00")
        self.assertIsNone(dt.tzinfo)

    def test_fractional_seconds(self):
        dt = _parse_creation_time("2024-06-01T12:00:00.000Z")
        expected = datetime.datetime(
            2024, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc
        ).astimezone()
        self.assertEqual(dt, expected)


class TestSanitizeFilename(unittest.TestCase):
    def test_collapses_doubled_vendor_prefix(self):
        self.assertEqual(
            sanitize_filename("2024-06-01 12.00.00 Canon_Canon_EOS_R5"),
            "2024-06-01 12.00.00 Canon_EOS_R5",
        )

    def test_strips_nul_and_slash(self):
        self.assertEqual(sanitize_filename("a\x00b/c"), "ab_c")


class TestScanDir(unittest.TestCase):
    def _scan(self, tmp):
        with mock.patch.object(
            exif_renamer, "get_image_exif_datetime", return_value="2024-06-01 12.00.00"
        ):
            exif_renamer.scan_dir(tmp, verbose=False)

    def test_same_timestamp_suffixes_follow_original_name_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("c.jpg", "a.jpg", "b.jpg"):
                with open(os.path.join(tmp, name), "w") as f:
                    f.write(name)
            self._scan(tmp)

            renamed = os.path.join(tmp, "renamed")
            expected = {
                "2024-06-01 12.00.00.jpg": "a.jpg",
                "2024-06-01 12.00.00-1.jpg": "b.jpg",
                "2024-06-01 12.00.00-2.jpg": "c.jpg",
            }
            self.assertEqual(sorted(os.listdir(renamed)), sorted(expected))
            for new_name, original in expected.items():
                with open(os.path.join(renamed, new_name)) as f:
                    self.assertEqual(f.read(), original)

    def test_each_move_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "a.jpg"), "w").close()
            with self.assertLogs(level="INFO") as logs:
                self._scan(tmp)
            self.assertTrue(
                any("a.jpg => 2024-06-01 12.00.00.jpg" in line for line in logs.output)
            )


if __name__ == "__main__":
    unittest.main()
