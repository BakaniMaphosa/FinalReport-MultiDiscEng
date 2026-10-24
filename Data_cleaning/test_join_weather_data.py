"""Verify exact weather alignment and input preservation on temporary CSVs."""

from contextlib import redirect_stderr, redirect_stdout
import csv
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import join_weather_data as joiner


class WeatherJoinTests(unittest.TestCase):
    WEATHER_HEADERS = {
        "T": "value T [Air temperature @ 2 m (deg C)]",
        "Rh": "value Rh [Relative humidity @ 2 m (%)]",
        "Ws": "value Ws [Wind speed @ 10 m (km/h)]",
        "Wd": "value Wd [Wind direction @ 10 m (deg)]",
        "Rd": "value Rd [Direct solar radiation (W/m^2)]",
        "Rr": "value Rr [Diffuse solar radiation  (W/m^2)]",
    }

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "Data/BuildingsByLocation"
        for building in joiner.BUILDINGS:
            self.consumption(building, [[building, "2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z", "1.200000000000000000000001"]])
        for location in ("L03", "L07", "L14"):
            for quantity in self.WEATHER_HEADERS:
                self.weather(location, quantity, [
                    ["2024-01-01T10:00:00Z", self.value(location, quantity)],
                    ["2024-01-01T11:00:00Z", "999999"],
                ])

    def value(self, location, quantity):
        return {
            "T": f"{int(location[1:])}.12345678901234567890123456789",
            "Rh": "60.123456789", "Ws": "-2.5000000", "Wd": "180.0001",
            "Rd": "400.000000001", "Rr": "-0.0000123456789",
        }[quantity]

    def write(self, path, headers, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)
        return path

    def consumption(self, building, rows, headers=None):
        return self.write(
            self.root / building.split("_")[0] / "unifieddataconsumption" / f"{building}_consumption.csv",
            joiner.CONSUMPTION_COLUMNS if headers is None else headers, rows,
        )

    def weather(self, location, quantity, rows, headers=None):
        return self.write(
            self.root / location / f"{location}_WS" / f"adrenalin.1h.{location}.WS01.{quantity}.csv",
            ["timestamp [UTC]", self.WEATHER_HEADERS[quantity]] if headers is None else headers, rows,
        )

    def generate(self):
        with redirect_stdout(io.StringIO()) as output:
            buildings, weather = joiner.prepare_inputs(self.root)
            joiner.write_outputs(buildings, weather)
        return output.getvalue()

    def rows(self, building):
        path = self.root / building.split("_")[0] / "unifieddataconsumption" / f"{building}_consumption_weather.csv"
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            self.assertEqual(reader.fieldnames, [
                "building_id", "interval_start_utc", "interval_end_utc", "electricity_kwh",
                "temperature_c", "relative_humidity_pct", "wind_speed_kmh", "wind_direction_deg",
                "direct_solar_radiation_wm2", "diffuse_solar_radiation_wm2",
            ])
        return rows

    def test_joins_start_not_end_and_preserves_precision_and_negative_values(self):
        output = self.generate()
        rows = self.rows("L03_B01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["electricity_kwh"], "1.200000000000000000000001")
        self.assertEqual(rows[0]["interval_start_utc"], "2024-01-01T10:00:00Z")
        self.assertEqual(rows[0]["interval_end_utc"], "2024-01-01T11:00:00Z")
        for quantity, column in joiner.WEATHER_COLUMNS.items():
            self.assertEqual(rows[0][column], self.value("L03", quantity))
        self.assertIn("input_rows=1, output_rows=1", output)

    def test_exact_matches_only_and_unmatched_rows_remain(self):
        self.consumption("L03_B01", [
            ["L03_B01", "2024-01-01T10:30:00Z", "2024-01-01T11:30:00Z", "2"],
            ["L03_B01", "2024-01-01T09:00:00Z", "2024-01-01T10:00:00Z", ""],
            ["L03_B01", "2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z", "3"],
        ])
        output = self.generate()
        rows = self.rows("L03_B01")
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["electricity_kwh"] for row in rows], ["", "3", "2"])
        for index in (0, 2):
            self.assertTrue(all(rows[index][column] == "" for column in joiner.WEATHER_COLUMNS.values()))
        for column in joiner.WEATHER_COLUMNS.values():
            self.assertIn(f"Missing {column}: 2", output)

    def test_utc_offsets_match_the_same_instant_without_shifting_intervals(self):
        self.consumption("L03_B01", [["L03_B01", "2024-01-01T12:00:00+02:00", "2024-01-01T13:00:00+02:00", "4.000"]])
        self.weather("L03", "T", [["2024-01-01T11:00:00+01:00", "27.123"]])
        self.generate()
        row = self.rows("L03_B01")[0]
        self.assertEqual(row["temperature_c"], "27.123")
        self.assertEqual(row["interval_start_utc"], "2024-01-01T10:00:00Z")
        self.assertEqual(row["interval_end_utc"], "2024-01-01T11:00:00Z")
        self.assertEqual(row["electricity_kwh"], "4.000")

    def test_actual_weather_header_order_is_used(self):
        self.weather("L03", "T", [["3.5000", "2024-01-01T10:00:00Z"]], headers=[
            self.WEATHER_HEADERS["T"], "timestamp [UTC]",
        ])
        self.generate()
        self.assertEqual(self.rows("L03_B01")[0]["temperature_c"], "3.5000")

    def test_duplicate_weather_instants_stop_before_replacing_any_output(self):
        self.generate()
        before = {p: p.read_bytes() for p in self.root.glob("*/unifieddataconsumption/*_consumption_weather.csv")}
        duplicate_file = self.weather("L14", "T", [
            ["2024-01-01T10:00:00Z", "1"], ["2024-01-01T11:00:00+01:00", "1"],
        ])
        with redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(joiner.main(["--root", str(self.root)]), 1)
        self.assertIn("duplicate weather timestamp", errors.getvalue())
        self.assertIn(str(duplicate_file), errors.getvalue())
        self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))

    def test_missing_files_and_bad_column_structures_report_clear_errors(self):
        path = self.root / "L03/L03_WS/adrenalin.1h.L03.WS01.Rh.csv"
        path.unlink()
        bad = self.weather("L07", "T", [["time", "value"]], headers=["unknown_time", "unknown_value"])
        with self.assertRaises(joiner.WeatherJoinError) as error:
            joiner.prepare_inputs(self.root)
        self.assertIn(str(path), str(error.exception))
        self.assertIn(str(bad), str(error.exception))
        self.assertIn("unexpected weather column structure", str(error.exception))
        self.assertEqual(list(self.root.glob("*/unifieddataconsumption/*_consumption_weather.csv")), [])

    def test_missing_consumption_columns_are_not_guessed(self):
        path = self.consumption("L03_B01", [["L03_B01", "x", "y", "1"]], headers=[
            "building_id", "interval_start_utc", "interval_end_utc", "energy_kwh",
        ])
        with self.assertRaisesRegex(joiner.WeatherJoinError, "unexpected consumption columns") as error:
            joiner.prepare_inputs(self.root)
        self.assertIn(str(path), str(error.exception))

    def test_units_must_match_column_names_without_conversion(self):
        path = self.weather("L03", "T", [["2024-01-01T10:00:00Z", "273.15"]], headers=[
            "timestamp [UTC]", "value T [Air temperature (K)]",
        ])
        with self.assertRaisesRegex(joiner.WeatherJoinError, "No automatic unit conversion") as error:
            joiner.prepare_inputs(self.root)
        self.assertIn(str(path), str(error.exception))

    def test_missing_weather_tokens_are_counted_but_not_rewritten(self):
        self.weather("L03", "T", [["2024-01-01T10:00:00Z", "NaN"]])
        self.weather("L03", "Ws", [["2024-01-01T10:00:00Z", ""]])
        self.weather("L03", "Rd", [["2024-01-01T10:00:00Z", "0.0000"]])
        output = self.generate()
        row = self.rows("L03_B01")[0]
        self.assertEqual(row["temperature_c"], "NaN")
        self.assertEqual(row["wind_speed_kmh"], "")
        self.assertEqual(row["direct_solar_radiation_wm2"], "0.0000")
        self.assertIn("Missing temperature_c: 1", output)
        self.assertIn("Missing wind_speed_kmh: 1", output)
        self.assertIn("Missing direct_solar_radiation_wm2: 0", output)

    def test_duplicate_consumption_rows_and_missing_prediction_times_are_preserved(self):
        self.consumption("L03_B01", [
            ["L03_B01", "2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z", "1"],
            ["L03_B01", "", "", "NA"],
            ["L03_B01", "2024-01-01T10:00:00Z", "2024-01-01T11:00:00Z", "2"],
        ])
        self.generate()
        rows = self.rows("L03_B01")
        self.assertEqual([row["electricity_kwh"] for row in rows], ["1", "2", "NA"])
        self.assertTrue(all(rows[-1][c] == "" for c in joiner.WEATHER_COLUMNS.values()))

    def test_l14_shared_weather_cached_once_and_all_inputs_unchanged(self):
        extra = self.root / "L06/unifieddataconsumption/L06_B01_consumption.csv"
        extra.parent.mkdir(parents=True)
        extra.write_text("do not read or alter this file")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.object(joiner, "read_weather", wraps=joiner.read_weather) as read:
            self.generate()
            self.assertEqual(read.call_count, 18)
        self.assertEqual(len(list(self.root.glob("*/unifieddataconsumption/*_consumption_weather.csv"))), 7)
        for building in ("L14_B01", "L14_B02", "L14_B03", "L14_B04", "L14_B05"):
            self.assertEqual(self.rows(building)[0]["temperature_c"], self.value("L14", "T"))
        self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))
        self.assertFalse((extra.parent / "L06_B01_consumption_weather.csv").exists())

    def test_default_root_from_another_cwd_root_override_and_rerunning(self):
        script = self.base / "Data_cleaning/join_weather_data.py"
        script.parent.mkdir()
        script.write_bytes(Path(joiner.__file__).read_bytes())
        other = self.base / "another_directory"
        other.mkdir()
        result = subprocess.run([sys.executable, str(script)], cwd=other, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(joiner.MODELLING_ASSUMPTION, result.stdout)
        output = self.root / "L03/unifieddataconsumption/L03_B01_consumption_weather.csv"
        output.write_text("old generated contents")
        result = subprocess.run([sys.executable, str(script), "--root", str(self.root)], cwd=other, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.rows("L03_B01")), 1)


if __name__ == "__main__":
    unittest.main()
