"""Check ambiguous metadata, equipment scope, and exact hourly-cell preservation."""

from contextlib import redirect_stdout
import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import add_building_metadata as metadata


INFO = """INSTITUTIONAL (EDUCATION) ({building})
Climate Zone: Cfb
Building info:
§1 Year Opened = 1914 (renovated in 2001)
§2 Number of floors = missing
§3 Size
- Gross total floor area = 6084 sqm
- Gross total heated area = 6084 sqm
§4 Ventilation systems = 1
- Demand controlled ventilation
- Used for space heating = YES
- Used for space cooling = NO
§5 Heating & cooling system
- Direct electrical heating (electric boiler) = YES
- District heating = NO
- District cooling = NO
- Heat pump (ground source) = NO
§6 Tap water heating
- Heat pump (ground source) = YES
- District heating = YES
§7 Solar PV = NO
NOTE:
"""


class BuildingMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "BuildingsByLocation"
        self.report = self.base / "report.txt"
        for building in metadata.BUILDINGS:
            self.info(building).parent.mkdir(parents=True)
            self.info(building).write_text(INFO.format(building=building), encoding="utf-8")
            self.source(building).parent.mkdir(parents=True, exist_ok=True)
            self.write_csv(building)

    def info(self, building="L03_B01"):
        return self.root / building.split("_")[0] / building / f"{building}-building_info.txt"

    def source(self, building="L03_B01"):
        return self.root / building.split("_")[0] / "unifieddataconsumption" / f"{building}_consumption_weather.csv"

    def destination(self, building="L03_B01"):
        return self.source(building).with_name(f"{building}_model_input.csv")

    def write_csv(self, building, rows=None, headers=metadata.EXISTING_COLUMNS):
        if rows is None:
            rows = [[building, "2024-01-01T11:00:00+01:00", "2024-01-01T11:00:00Z",
                     "1.200000000000000000000001", "-9.000", "NaN", "", " 180 ", "0.00", "-0.01"]]
        with self.source(building).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)

    def extract(self, text=None):
        if text is not None:
            self.info().write_text(text, encoding="utf-8")
        return metadata.read_metadata(self.info(), "L03_B01")

    def generate(self):
        with redirect_stdout(io.StringIO()):
            metadata.write_outputs(metadata.prepare_inputs(self.root), self.report)

    def test_qualifiers_renovations_and_tap_water_scope(self):
        values, issues = self.extract()
        self.assertEqual(values["year_opened"], 1914)
        self.assertEqual(values["has_direct_electric_heating"], 1)
        self.assertEqual(values["has_heat_pump"], 0)
        self.assertEqual(values["has_district_heating"], 0)
        self.assertEqual(values["floor_area_m2"], "6084")
        self.assertEqual(values["ventilation_used_for_cooling"], 0)
        self.assertEqual(values["building_use"], "INSTITUTIONAL (EDUCATION)")
        self.assertIsNone(values["number_of_floors"])
        self.assertEqual(set(issues), {"number_of_floors"})

    def test_observed_l03_duplicate_floor_labels_are_ambiguous(self):
        text = INFO.format(building="L03_B01").replace(
            "§2 Number of floors = missing\n§3 Size", "§2 Number of floors = 4\n§3 Number of floors = 1")
        values, issues = self.extract(text)
        self.assertIsNone(values["number_of_floors"])
        self.assertIn("conflicting", issues["number_of_floors"])
        self.assertIn("'4'", issues["number_of_floors"])
        self.assertIn("'1'", issues["number_of_floors"])
        self.assertEqual(values["heated_area_m2"], "6084")

    def test_missing_and_ambiguous_equipment_never_imply_no(self):
        text = INFO.format(building="L03_B01").replace(
            "- Heat pump (ground source) = NO\n", "").replace(
            "- District cooling = NO", "- District cooling = maybe").replace(
            "§7 Solar PV = NO", "§7 Solar PV = YES\n- Solar PV = NO")
        values, issues = self.extract(text)
        for field in ("has_heat_pump", "has_district_cooling", "has_solar_pv"):
            self.assertIsNone(values[field])
            self.assertIn(field, issues)

    def test_whitespace_and_equivalent_labels_preserve_readable_categories(self):
        text = INFO.format(building="L03_B01").replace(
            "INSTITUTIONAL (EDUCATION)", "INSTITUTIONAL   (EDUCATION)").replace(
            "Climate Zone: Cfb", "Climate  Zone:   Cfb ").replace(
            "Heating & cooling system", "Heating and cooling system").replace(
            "Direct electrical heating", "Direct electric heating").replace("YES", "yes")
        values, _ = self.extract(text)
        self.assertEqual(values["building_use"], "INSTITUTIONAL (EDUCATION)")
        self.assertEqual(values["climate_zone"], "Cfb")
        self.assertEqual(values["has_direct_electric_heating"], 1)

    def test_nonpositive_supplied_areas_stop_and_unknown_units_stay_empty(self):
        for area in ("0 sqm", "-12 sqm"):
            with self.subTest(area=area), self.assertRaisesRegex(metadata.MetadataError, "positive"):
                self.extract(INFO.format(building="L03_B01").replace("6084 sqm", area))
        values, issues = self.extract(INFO.format(building="L03_B01").replace("6084 sqm", "20 sqft"))
        self.assertIsNone(values["floor_area_m2"])
        self.assertIn("unit", issues["floor_area_m2"])

    def test_every_original_cell_row_order_extra_column_and_rerun_preserved(self):
        headers = ["extra_note"] + list(metadata.EXISTING_COLUMNS)
        rows = [
            ["comma, newline\nand quote\"", "L03_B01", "later", "", "1.000000000000000000001", "NaN", "", "-2", " 180 ", "0", "-0.1"],
            ["", "L03_B01", "earlier", "raw timestamp", "NA", "", "", "", "", "", ""],
        ]
        rows.append(rows[0][:])
        self.write_csv("L03_B01", rows, headers)
        inputs = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        # Generated and unselected CSVs cannot be discovered as source inputs.
        ignored = self.source().with_name("L99_B99_consumption_weather.csv")
        ignored.write_text("invalid CSV intentionally ignored")
        self.generate()
        with self.destination().open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            self.assertEqual(next(reader), headers + list(metadata.APPENDED_COLUMNS))
            enriched = list(reader)
        self.assertEqual([row[:len(headers)] for row in enriched], rows)
        self.assertTrue(all(row[len(headers):-1] == enriched[0][len(headers):-1] for row in enriched))
        self.assertEqual(enriched[1][-1], "")
        self.assertEqual(enriched[0][-1], enriched[2][-1])
        self.assertEqual(enriched[0][headers.index("electricity_kwh")], rows[0][headers.index("electricity_kwh")])
        before = {self.destination(b): self.destination(b).read_bytes() for b in metadata.BUILDINGS}
        before[self.report] = self.report.read_bytes()
        self.generate()
        self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))
        self.assertTrue(all(p.read_bytes() == data for p, data in inputs.items()))
        self.assertIn(str(self.info()), self.report.read_text())
        self.assertIn("number_of_floors", self.report.read_text())

    def test_electricity_per_floor_area_handles_values_and_missing_inputs(self):
        for reading, area, expected in (
            ("900", "450", "2"), ("0", "450", "0"), ("-450", "450", "-1"),
            ("1.25", "2.5", "0.5"), (" 450 ", "450", "1"),
            ("", "450", ""), ("NA", "450", ""), ("NaN", "450", ""),
            ("Infinity", "450", ""), ("uncertain", "450", ""),
            ("900", None, ""), ("900", "", ""), ("900", "0", ""),
        ):
            with self.subTest(reading=reading, area=area):
                self.assertEqual(metadata.electricity_per_m2(reading, area), expected)
        self.info().write_text(INFO.format(building="L03_B01").replace("6084 sqm", "450 sqm"))
        self.write_csv("L03_B01", [["L03_B01", "start", "end", "900", "", "", "", "", "", ""]])
        self.generate()
        with self.destination().open(newline="") as handle:
            self.assertEqual(next(csv.DictReader(handle))["electricity_kwh_per_m2"], "2")

    def test_csv_building_mismatch_fails_before_any_output_replacement(self):
        self.generate()
        before = {self.destination(b): self.destination(b).read_bytes() for b in metadata.BUILDINGS}
        self.source("L14_B05").write_text(self.source("L14_B05").read_text().replace("L14_B05", "L14_B04"))
        with self.assertRaisesRegex(metadata.MetadataError, "building_id"):
            self.generate()
        self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))
        self.assertFalse(list(self.root.rglob(".metadata_*")))

    def test_mismatched_or_duplicate_building_info_is_rejected(self):
        with self.assertRaisesRegex(metadata.MetadataError, "expected building"):
            self.extract(INFO.format(building="L14_B01"))
        self.info().write_text(INFO.format(building="L03_B01"))
        extra = self.info().parent / "copy" / self.info().name
        extra.parent.mkdir()
        extra.write_text(self.info().read_text())
        with self.assertRaisesRegex(metadata.MetadataError, "found 2"):
            metadata.prepare_inputs(self.root)

    def test_missing_source_is_not_replaced_by_existing_model_input(self):
        self.generate()
        self.source().unlink()
        with self.assertRaisesRegex(metadata.MetadataError, "required input missing"):
            self.generate()

    def test_metadata_already_in_source_is_rejected(self):
        self.write_csv("L03_B01", [], list(metadata.EXISTING_COLUMNS) + ["has_heat_pump"])
        with self.assertRaisesRegex(metadata.MetadataError, "source columns"):
            self.generate()

    def test_report_cannot_overwrite_a_source_through_dot_dot_path(self):
        self.report = self.info().parent / ".." / self.info().parent.name / self.info().name
        before = self.info().read_bytes()
        with self.assertRaisesRegex(metadata.MetadataError, "Report path must differ"):
            self.generate()
        self.assertEqual(self.info().read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
