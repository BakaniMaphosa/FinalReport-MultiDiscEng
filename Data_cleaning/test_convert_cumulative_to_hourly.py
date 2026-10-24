"""Test cumulative conversion using temporary files, never project datasets."""

from contextlib import redirect_stderr, redirect_stdout
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import convert_cumulative_to_hourly as converter


class CumulativeConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "Data/BuildingsByLocation"
        self.channel = converter.Channel("L06_B01", "EM01.Pt")
        self.building = self.root / "L06/L06_B01"

    def source(self, values, hours=None, path=None, headers=None):
        path = path or self.building / "1h/adrenalin.1h.L06.B01.EM01.Pt.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        hours = hours or range(len(values))
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers or ["timestamp [UTC]", "value Pt [Consumed active energy (kWh)]"])
            for hour, value in zip(hours, values):
                writer.writerow([(start + timedelta(hours=hour)).isoformat(), value])
        return path

    def intervals(self, values, hours=None):
        path = self.source(values, hours)
        readings, _ = converter.read_original_readings(path, self.channel)
        return converter.calculate_intervals(readings)

    def config(self, channels=None):
        entries = channels if channels is not None else [{
            "building_id": "L06_B01", "channel": "EM01.Pt", "confirmed_cumulative": True,
        }]
        path = self.base / "config.json"
        path.write_text(json.dumps({"cumulative_channels": entries}))
        return path

    def test_decrease_rebound_and_normal_resumption(self):
        intervals = self.intervals([100, 110, 5, 120, 130])
        self.assertEqual([i.difference for i in intervals], list(map(Decimal, [10, -105, 115, 10])))
        self.assertEqual([i.reasons for i in intervals], [
            [], ["counter_decrease"], ["possible_rebound_after_counter_decrease"], [],
        ])

    def test_consecutive_decreases_each_protect_the_next_interval(self):
        intervals = self.intervals([100, 10, 5, 20, 25])
        self.assertEqual(intervals[0].reasons, ["counter_decrease"])
        self.assertEqual(intervals[1].reasons, ["counter_decrease", "possible_rebound_after_counter_decrease"])
        self.assertEqual(intervals[2].reasons, ["possible_rebound_after_counter_decrease"])
        self.assertEqual(intervals[3].reasons, [])

    def test_invalid_values_remain_in_original_pairs_without_bridging(self):
        intervals = self.intervals([100, 10, "NA", 20, 30])
        self.assertEqual(len(intervals), 4)
        self.assertIn("possible_rebound_after_counter_decrease", intervals[1].reasons)
        self.assertIn("invalid_current_reading", intervals[1].reasons)
        self.assertIn("invalid_previous_reading", intervals[2].reasons)
        self.assertIsNone(intervals[1].difference)
        self.assertIsNone(intervals[2].difference)
        self.assertEqual([i.difference for i in intervals if not i.reasons], [Decimal(10)])
        for invalid in ("NaN", "Infinity", ""):
            with self.subTest(invalid=invalid):
                intervals = self.intervals([10, invalid, 30, 40])
                self.assertEqual(sum(not i.reasons for i in intervals), 1)

    def test_gaps_and_negative_changes_across_gaps(self):
        intervals = self.intervals([100, 50, 100, 110], [0, 1, 3, 4])
        self.assertEqual(intervals[1].reasons, [
            "not_exactly_one_hour_apart", "possible_rebound_after_counter_decrease",
        ])
        self.assertEqual(intervals[2].reasons, [])
        intervals = self.intervals([100, 50, 110, 120], [0, 2, 3, 4])
        self.assertEqual(intervals[0].reasons, ["not_exactly_one_hour_apart", "counter_decrease"])
        self.assertEqual(intervals[1].reasons, ["possible_rebound_after_counter_decrease"])
        self.assertEqual(intervals[2].reasons, [])
        intervals = self.intervals([1, 9, 10], [0, 2, 3])
        self.assertEqual([i.difference for i in intervals if not i.reasons], [Decimal(1)])

    def test_true_zero_and_large_positive_changes_are_not_trimmed(self):
        intervals = self.intervals([100, 100, 1000000000000])
        self.assertEqual([i.reasons for i in intervals], [[], []])
        self.assertEqual(intervals[0].difference, Decimal(0))
        self.assertEqual(intervals[1].difference, Decimal(999999999900))

    def test_sorting_and_timezone_normalization(self):
        path = self.source([30, 10, 20], [2, 0, 1])
        readings, _ = converter.read_original_readings(path, self.channel)
        self.assertEqual([r.source_row for r in readings], [2, 3, 1])
        self.assertEqual([r.value for r in readings], [Decimal(10), Decimal(20), Decimal(30)])
        self.assertTrue(all(r.timestamp.tzinfo == timezone.utc for r in readings))
        self.assertEqual([i.difference for i in converter.calculate_intervals(readings)], [Decimal(10), Decimal(10)])

    def test_duplicate_timestamp_stops_file_without_new_csv_outputs(self):
        source = self.source([10, 20, 30], [0, 1, 1])
        before = source.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as errors:
            self.assertFalse(converter.process_file(source, self.building, self.channel))
        self.assertIn("Duplicate timestamps", errors.getvalue())
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(list((self.building / "processed").glob("*.csv")), [])
        report = next((self.building / "processed").glob("*.txt")).read_text()
        self.assertIn("STATUS: STOPPED", report)
        self.assertIn(converter.LIMITATION, report)

    def test_invalid_timestamp_stops_instead_of_dropping_original_row(self):
        source = self.source([10, 20, 30])
        text = source.read_text().replace("2024-01-01T01:00:00+00:00", "bad timestamp")
        source.write_text(text)
        with self.assertRaisesRegex(converter.InputProblem, "cannot be placed chronologically"):
            converter.read_original_readings(source, self.channel)

    def test_written_outputs_original_readings_and_exact_limitation(self):
        source = self.source([100, 110, 5, 120, 130])
        before = source.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.assertTrue(converter.process_file(source, self.building, self.channel))
        accepted, excluded, report = converter.output_paths(source, self.building)
        with accepted.open(newline="") as handle:
            reader = csv.DictReader(handle)
            accepted_rows = list(reader)
            self.assertEqual(reader.fieldnames, converter.ACCEPTED_COLUMNS)
        self.assertEqual([Decimal(row["energy_kwh"]) for row in accepted_rows], [Decimal(10), Decimal(10)])
        self.assertEqual(accepted_rows[1]["interval_start_utc"], "2024-01-01T03:00:00Z")
        with excluded.open(newline="") as handle:
            excluded_rows = list(csv.DictReader(handle))
        self.assertEqual(excluded_rows[0]["previous_reading_kwh"], "110")
        self.assertEqual(excluded_rows[0]["current_reading_kwh"], "5")
        self.assertEqual(excluded_rows[0]["difference_kwh"], "-105")
        self.assertEqual(excluded_rows[1]["difference_kwh"], "115")
        self.assertIn(converter.LIMITATION, report.read_text())
        self.assertEqual(source.read_bytes(), before)

    def test_configuration_requires_confirmation_and_rejects_l14_or_letter_o(self):
        for entry, message in (
            ({"building_id": "L14_B01", "channel": "EM01.Pt", "confirmed_cumulative": True}, "L14"),
            ({"building_id": "L06_B01", "channel": "EMO1.Pt", "confirmed_cumulative": True}, "Invalid channel"),
            ({"building_id": "L06_B01", "channel": "EM01.Pt", "confirmed_cumulative": False}, "not explicitly confirmed"),
        ):
            with self.subTest(entry=entry), self.assertRaisesRegex(converter.InputProblem, message):
                converter.load_channels(self.config([entry]))
        self.assertEqual(converter.load_channels(self.config()), [self.channel])
        with self.assertRaisesRegex(converter.InputProblem, "No cumulative channels"):
            converter.load_channels(self.config([]))

    def test_header_quantity_and_unit_must_match_configuration(self):
        for headers in (
            ["timestamp [UTC]", "value Pt [Active energy (Wh)]"],
            ["timestamp [UTC]", "value ePt [Active energy (kWh)]"],
            ["time", "reading"],
        ):
            source = self.source([1, 2], headers=headers)
            with self.subTest(headers=headers), self.assertRaises(converter.InputProblem):
                converter.read_original_readings(source, self.channel)

    def test_discovery_skips_weather_unconfigured_buildings_and_symbolic_links(self):
        source = self.source([1, 2])
        weather = self.root / "L06/L06_WS/L06_B01/1h/adrenalin.1h.L06.B01.EM01.Pt.csv"
        self.source([9, 10], path=weather)
        unconfigured = self.root / "L03/L03_B01/1h/adrenalin.1h.L03.B01.EM01.Pt.csv"
        self.source([1, 2], path=unconfigured)
        outside_hourly = self.building / "15m/adrenalin.1h.L06.B01.EM01.Pt.csv"
        self.source([1, 2], path=outside_hourly)
        link = self.building / "1h/nested"
        link.symlink_to(weather.parent, target_is_directory=True)
        found, errors = converter.find_sources(self.root, [self.channel])
        self.assertEqual(errors, [])
        self.assertEqual(found[self.channel], [(source, self.building)])

    def test_cli_root_and_config_work_from_another_working_directory(self):
        source = self.source([100, 110, 5, 120, 130])
        before = source.read_bytes()
        result = subprocess.run([
            sys.executable, str(Path(converter.__file__).resolve()),
            "--root", str(self.root), "--config", str(self.config()),
        ], cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("retained=2, excluded=2", result.stdout)
        self.assertEqual(source.read_bytes(), before)

    def test_output_symbolic_links_are_not_overwritten(self):
        source = self.source([10, 20])
        protected = self.base / "protected.txt"
        protected.write_text("preserve this")
        processed = self.building / "processed"
        processed.mkdir()
        accepted = processed / f"{source.stem}.hourly_energy.csv"
        accepted.symlink_to(protected)
        with self.assertRaisesRegex(converter.InputProblem, "symbolic links"):
            converter.process_file(source, self.building, self.channel)
        self.assertEqual(protected.read_text(), "preserve this")


if __name__ == "__main__":
    unittest.main()
