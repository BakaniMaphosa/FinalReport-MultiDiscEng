"""Inspection tests use temporary CSVs; never alter the project's data."""

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import inspect_energy_readings as inspector


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()

    def csv_file(self, rows, channel="EM01.Pt", building="L06_B01", path=None, headers=None):
        path = path or self.base / "example.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        quantity = channel.split(".")[1]
        if headers is None:
            headers = ["timestamp [UTC]", f"value {quantity} [Consumed active energy (kWh)]"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)
        return inspector.inspect_file(building, channel, path)

    def hourly_rows(self, values):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        return [((start + timedelta(hours=i)).isoformat(), str(value)) for i, value in enumerate(values)]

    def test_sorting_utc_and_exact_hourly_statistics(self):
        result = self.csv_file([
            ("2024-01-01T02:00:00+02:00", "10"),
            ("2023-12-31T23:00:00Z", "8"),
            ("2024-01-01T02:00:00Z", "12"),
        ])
        m = result.metrics
        self.assertEqual(result.stated_unit, "kWh")
        self.assertEqual(result.row_count, 3)
        self.assertEqual([r.value for r in m["ordered"]], [Decimal(8), Decimal(10), Decimal(12)])
        self.assertTrue(all(r.timestamp.tzinfo == timezone.utc for r in m["ordered"]))
        self.assertEqual(len(m["pairs"]), 2)
        self.assertEqual(len(m["hourly_pairs"]), 1)
        self.assertEqual(m["non_hourly_pairs"], 1)
        self.assertEqual(m["hourly_pairs"][0].change, Decimal(2))
        rendered = "\n".join(inspector.render_file(result))
        self.assertIn("First timestamp (chronological UTC): 2023-12-31T23:00:00Z", rendered)
        self.assertIn("Last timestamp (chronological UTC): 2024-01-01T02:00:00Z", rendered)

    def test_missing_and_nonfinite_values_are_never_bridged(self):
        result = self.csv_file(self.hourly_rows([10, "NA", 30, 25, "NaN", "Infinity", ""]))
        m = result.metrics
        self.assertEqual(len(m["values"]), 3)
        self.assertEqual(m["invalid_values"], 4)
        self.assertEqual(len(m["pairs"]), 1)
        self.assertEqual(m["pairs"][0].change, Decimal(-5))
        self.assertEqual(m["missing_value_pairs"], 5)
        self.assertEqual(inspector.direction_counts(m["pairs"]), (0, 1, 0))

    def test_utc_duplicate_timestamps_exclude_every_touching_pair(self):
        result = self.csv_file([
            ("2024-01-01T00:00:00Z", "10"),
            ("2024-01-01T01:00:00Z", "11"),
            ("2024-01-01T02:00:00+01:00", "11"),
            ("2024-01-01T02:00:00Z", "13"),
            ("2024-01-01T03:00:00Z", "14"),
        ])
        m = result.metrics
        self.assertEqual(len(m["duplicates"]), 1)
        self.assertEqual(m["ambiguous_pairs"], 3)
        self.assertEqual(m["non_hourly_pairs"], 1)
        self.assertEqual(len(m["hourly_pairs"]), 1)
        self.assertEqual(m["pairs"][0].before.value, Decimal(13))
        self.assertIn("rows [2, 3]", "\n".join(inspector.render_file(result)))

    def test_unplaceable_rows_and_naive_timestamps_block_comparisons(self):
        result = self.csv_file([
            ("2024-01-01T00:00:00Z", "10"),
            ("bad timestamp", "20"),
            ("2024-01-01T01:00:00Z", "30"),
            ("2024-01-01T02:00:00Z", "40"),
            ("2024-01-01T03:00:00", "50"),
        ])
        m = result.metrics
        self.assertEqual(m["invalid_timestamps"], 2)
        self.assertEqual(m["untimed_barrier_pairs"], 1)
        self.assertEqual(len(m["pairs"]), 1)
        self.assertEqual(m["pairs"][0].change, Decimal(10))

    def test_schema_errors_and_reversed_expected_columns(self):
        result = self.csv_file([("2024-01-01T00:00:00Z", "10", "extra")])
        self.assertEqual(result.metrics["malformed_rows"], 1)
        self.assertEqual(result.metrics["invalid_values"], 1)
        result = self.csv_file([("x", "10", "extra")], headers=["time", "reading", "extra"])
        self.assertIn("Unexpected columns", result.error)
        self.assertEqual(result.row_count, 1)
        self.assertTrue(result.requires_review)
        result = self.csv_file([("10", "2024-01-01T00:00:00Z")], headers=[
            "value Pt [Consumed active energy (kWh)]", "timestamp [UTC]",
        ])
        self.assertIsNone(result.error)
        self.assertEqual(result.readings[0].value, Decimal(10))
        result = self.csv_file([("2024-01-01T00:00:00Z", "10")], headers=[
            "timestamp [UTC]", "value ePt [Active energy export (kWh)]",
        ])
        self.assertIn("Unexpected quantity", result.error)

    def test_constants_and_short_series_require_manual_review(self):
        for values in ([0] * 30, [17] * 30, [1, 2, 3]):
            with self.subTest(values=values[:3]):
                result = self.csv_file(self.hourly_rows(values))
                self.assertEqual(result.suggested_interpretation, "manual review required")
                self.assertTrue(result.requires_review)
        documented = self.csv_file(self.hourly_rows([0] * 30), building="L14_B01")
        self.assertIn("documented hourly energy", documented.suggested_interpretation)
        self.assertIn("manual review required", documented.suggested_interpretation)
        self.assertIn("All-zero", documented.evidence)

    def test_cumulative_suggestion_with_reset_does_not_approve_conversion(self):
        values = [10000 + i * 10 for i in range(100)]
        values[50] = 9000
        result = self.csv_file(self.hourly_rows(values))
        self.assertEqual(result.suggested_interpretation, "suggested cumulative energy")
        self.assertTrue(result.requires_review)
        self.assertIn("resets/corrections", result.evidence)
        self.assertEqual(inspector.direction_counts(result.metrics["hourly_pairs"])[1], 1)

    def test_hourly_suggestion_distinguishes_documentation(self):
        rows = self.hourly_rows([100, 101, 100, 99] * 10)
        suggested = self.csv_file(rows)
        self.assertEqual(suggested.suggested_interpretation, "suggested hourly energy")
        self.assertTrue(suggested.requires_review)
        documented = self.csv_file(rows, building="L14_B01")
        self.assertEqual(documented.suggested_interpretation, "documented hourly energy")
        self.assertFalse(documented.requires_review)
        self.assertIn("consistent, not proof", documented.evidence)

    def test_discovery_skips_weather_links_and_nonselected_channels(self):
        root = self.base / "data"
        selected = root / "l03/l03_b01/deep/1H/adrenalin.1h.l03.b01.em02.pt.CSV"
        self.csv_file(self.hourly_rows([1, 2]), path=selected, building="L03_B01", channel="EM02.Pt")
        for relative in (
            "L03/L03_WS/L03_B01/1h/adrenalin.1h.L03.B01.EM02.Pt.csv",
            "L06/L06_B01/1h/adrenalin.1h.L06.B01.EM01.P.csv",
            "L06/L06_B01/1h/adrenalin.1h.L06.B01.EMO1.Pt.csv",
            "L06/L06_B01/15m/adrenalin.1h.L06.B01.EM01.Pt.csv",
            "L03/L03_B02/1h/adrenalin.1h.L03.B02.EM02.Pt.csv",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not a readable CSV schema")
        link = root / "L14_B01"
        link.symlink_to(selected.parent, target_is_directory=True)
        found, errors = inspector.discover_files(root)
        self.assertEqual(errors, [])
        self.assertEqual(found[("L03_B01", "EM02.Pt")], [selected])
        self.assertEqual(sum(len(paths) for paths in found.values()), 1)
        report, results, error = inspector.build_report(root)
        self.assertTrue(error)
        self.assertEqual(sum(result.path is None for result in results), 9)
        self.assertIn("MISSING FILE", report)
        self.assertIn("SUMMARY TABLE", report)

    def test_multiple_source_files_are_not_merged_or_silently_chosen(self):
        root = self.base / "data"
        for subfolder in ("", "nested"):
            path = root / "L03/L03_B01/1h" / subfolder / "adrenalin.1h.L03.B01.EM02.Pt.csv"
            self.csv_file(self.hourly_rows([1, 2]), channel="EM02.Pt", building="L03_B01", path=path)
        _, results, _ = inspector.build_report(root)
        selected = [result for result in results if result.building == "L03_B01"]
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(result.requires_review for result in selected))
        self.assertTrue(all("Multiple selected files" in result.issues[0] for result in selected))

    def test_cli_works_from_another_cwd_and_report_equals_stdout(self):
        project = self.base / "project"
        script = project / "Data_cleaning/inspect_energy_readings.py"
        script.parent.mkdir(parents=True)
        script.write_bytes(Path(inspector.__file__).read_bytes())
        sources = {}
        for building, channel in inspector.TARGETS:
            location, building_id = building.split("_")
            path = project / f"Data/BuildingsByLocation/{location}/{building}/1h/adrenalin.1h.{location}.{building_id}.{channel}.csv"
            self.csv_file(self.hourly_rows([1, 2]), building=building, channel=channel, path=path)
            sources[path] = path.read_bytes()
        result = subprocess.run([sys.executable, str(script)], cwd=self.base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        report = script.parent / "energy_readings_report.txt"
        self.assertEqual(report.read_text(), result.stdout)
        self.assertEqual(result.stdout.count("Exact column headers:"), 10)
        self.assertTrue(all(path.read_bytes() == before for path, before in sources.items()))
        overridden = subprocess.run(
            [sys.executable, str(script), "--root", str(self.base / "missing")],
            cwd=self.base, capture_output=True, text=True,
        )
        self.assertEqual(overridden.returncode, 1)
        self.assertIn("DISCOVERY ERROR", overridden.stdout)


if __name__ == "__main__":
    unittest.main()
