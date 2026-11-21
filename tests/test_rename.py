import datetime
import unittest

from rename import _parse_creation_time


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


if __name__ == "__main__":
    unittest.main()
