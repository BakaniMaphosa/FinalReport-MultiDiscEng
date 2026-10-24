"""Exercise table construction against temporary CSVs, never project data."""

from contextlib import redirect_stderr, redirect_stdout
import csv
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import build_consumption_tables as builder


class ConsumptionTableTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "Data/BuildingsByLocation"

    def write(self, source, rows, headers=None):
        path = self.root / source.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        expected = builder.PROCESSED_COLUMNS if source.already_processed else builder.DIRECT_COLUMNS
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(expected if headers is None else headers)
            writer.writerows(rows)
        return path

    def populate(self):
        for source in builder.SOURCES:
            rows = (
                [["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "2.500000000000000001"]]
                if source.already_processed else [["2024-01-01T00:00:00Z", "7.000000000000000001"]]
            )
            self.write(source, rows)

    def generate(self):
        with redirect_stdout(io.StringIO()) as output:
            builder.write_tables(builder.prepare_tables(self.root))
        return output.getvalue()

    def output_rows(self, building):
        path = self.root / building.split("_")[0] / "unifieddataconsumption" / f"{building}_consumption.csv"
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            self.assertEqual(reader.fieldnames, [
                "building_id", "interval_start_utc", "interval_end_utc", "electricity_kwh",
            ])
        return rows

    def test_direct_values_precision_missing_values_gaps_and_sorting(self):
        self.populate()
        exact = "1234.000000000000000000000000000000000000001"
        self.write(builder.SOURCES[0], [
            ["2024-01-01T03:00:00Z", ""],
            ["2024-01-01T02:00:00+02:00", exact],
            ["2024-01-01T02:00:00Z", "NA"],
        ])
        self.generate()
        rows = self.output_rows("L03_B01")
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["electricity_kwh"] for r in rows], [exact, "NA", ""])
        self.assertEqual([r["interval_start_utc"] for r in rows], [
            "2023-12-31T23:00:00Z", "2024-01-01T01:00:00Z", "2024-01-01T02:00:00Z",
        ])
        self.assertEqual(rows[0]["interval_end_utc"], "2024-01-01T00:00:00Z")

    def test_l07_preserves_existing_intervals_and_values(self):
        self.populate()
        self.write(builder.SOURCES[1], [
            ["2024-01-01T04:00:00Z", "2024-01-01T05:00:00Z", ""],
            ["2024-01-01T01:15:00+01:00", "2024-01-01T01:45:00+01:00", "19.123456789012345678901234567890"],
        ])
        self.generate()
        rows = self.output_rows("L07_B01")
        self.assertEqual(rows[0], {
            "building_id": "L07_B01", "interval_start_utc": "2024-01-01T00:15:00Z",
            "interval_end_utc": "2024-01-01T00:45:00Z", "electricity_kwh": "19.123456789012345678901234567890",
        })
        self.assertEqual(rows[1]["electricity_kwh"], "")
        self.assertEqual(rows[1]["interval_start_utc"], "2024-01-01T04:00:00Z")

    def test_seven_separate_tables_preserve_all_sources_and_unrelated_files(self):
        self.populate()
        for relative in (
            "L06/L06_B01/1h/leave_me.csv", "L14/L14_WS/weather.csv",
            "L03/L03_B01/README.md", "L14/L14_B02/building_info.txt",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("unchanged")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = self.generate()
        self.assertEqual(len(list(self.root.glob("*/unifieddataconsumption/*_consumption.csv"))), 7)
        self.assertEqual(output.count(": 1 rows"), 7)
        self.assertFalse((self.root / "L06/unifieddataconsumption").exists())
        for source in builder.SOURCES:
            self.assertEqual(self.output_rows(source.building)[0]["building_id"], source.building)
        self.assertTrue(all(path.read_bytes() == content for path, content in before.items()))

    def test_preflight_missing_processed_file_does_not_fall_back_or_write(self):
        self.populate()
        processed = self.root / builder.SOURCES[1].relative_path
        processed.unlink()
        raw = processed.parent.parent / "1h/adrenalin.1h.L07.B01.EM01.Pt.csv"
        raw.parent.mkdir()
        raw.write_text("timestamp [UTC],value Pt [Consumed active energy (kWh)]\n")
        with self.assertRaisesRegex(builder.TableBuildError, "no outputs were written"):
            builder.prepare_tables(self.root)
        self.assertEqual(list(self.root.glob("*/unifieddataconsumption")), [])

    def test_preflight_bad_columns_keeps_previous_outputs_unchanged(self):
        self.populate()
        self.generate()
        outputs = {p: p.read_bytes() for p in self.root.glob("*/unifieddataconsumption/*.csv")}
        self.write(builder.SOURCES[1], [["x", "y", "z"]], headers=["timestamp", "energy", "other"])
        with redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(builder.main(["--root", str(self.root)]), 1)
        self.assertIn("required columns missing", errors.getvalue())
        self.assertIn("No column guessing or source fallback", errors.getvalue())
        self.assertTrue(all(path.read_bytes() == content for path, content in outputs.items()))

    def test_duplicates_missing_timestamps_and_negative_values_are_preserved(self):
        self.populate()
        self.write(builder.SOURCES[0], [
            ["2024-01-01T00:00:00Z", "-7.000"],
            ["", "NaN"],
            ["2024-01-01T00:00:00Z", "-7.000"],
        ])
        self.generate()
        rows = self.output_rows("L03_B01")
        self.assertEqual([r["electricity_kwh"] for r in rows], ["-7.000", "-7.000", "NaN"])
        self.assertEqual(rows[-1]["interval_start_utc"], "")
        self.assertEqual(rows[-1]["interval_end_utc"], "")

    def test_rerunning_replaces_outputs_instead_of_appending(self):
        self.populate()
        self.generate()
        self.write(builder.SOURCES[0], [["2024-01-01T00:00:00Z", "42.000000"]])
        self.generate()
        rows = self.output_rows("L03_B01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["electricity_kwh"], "42.000000")
        self.assertEqual(list(self.root.glob("*/unifieddataconsumption/*.tmp")), [])

    def test_invalid_nonempty_timestamp_reports_error_without_writing(self):
        self.populate()
        self.write(builder.SOURCES[0], [["not a timestamp", "1.0"]])
        with self.assertRaisesRegex(builder.TableBuildError, "invalid timestamp"):
            builder.prepare_tables(self.root)
        self.assertEqual(list(self.root.glob("*/unifieddataconsumption")), [])

    def test_default_root_from_unrelated_cwd_and_root_override(self):
        self.populate()
        script = self.base / "Data_cleaning/build_consumption_tables.py"
        script.parent.mkdir()
        script.write_bytes(Path(builder.__file__).read_bytes())
        unrelated = self.base / "another_directory"
        unrelated.mkdir()
        result = subprocess.run([sys.executable, str(script)], cwd=unrelated, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count(": 1 rows"), 7)
        result = subprocess.run([
            sys.executable, str(script), "--root", str(self.root),
        ], cwd=unrelated, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_output_directory_symlinks_are_not_followed(self):
        self.populate()
        protected = self.base / "protected"
        protected.mkdir()
        (self.root / "L03/unifieddataconsumption").symlink_to(protected, target_is_directory=True)
        with self.assertRaisesRegex(builder.TableBuildError, "Symbolic-link"):
            builder.prepare_tables(self.root)
        self.assertEqual(list(protected.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
