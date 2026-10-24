"""Append building metadata without changing any hourly CSV cell.

Run from the project root: python3 Data_cleaning/add_building_metadata.py
Uses only the standard library. Outputs are <building_id>_model_input.csv next
to each source and Data_cleaning/building_metadata_report.txt. Empty metadata
cells represent missing/ambiguous values; categories remain readable text.
Also appends electricity_kwh_per_m2 = electricity_kwh / gross floor_area_m2,
using 28 significant decimal digits. Missing/non-numeric/non-finite readings
or missing floor areas give empty derived cells; original readings stay intact.

The observed TXT files use numbered sections, optional equipment qualifiers,
and opening years with renovation notes. L03_B01 has conflicting floor-count
labels in sections 2 and 3; neither is assumed correct. Heating/cooling flags
come only from that section, never from tap-water heating.
"""

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from itertools import zip_longest
import os
from pathlib import Path
import re
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = PROJECT_ROOT / "Data/BuildingsByLocation"
DEFAULT_REPORT = PROJECT_ROOT / "Data_cleaning/building_metadata_report.txt"
BUILDINGS = ("L03_B01", "L07_B01", "L14_B01", "L14_B02", "L14_B03", "L14_B04", "L14_B05")
EXISTING_COLUMNS = (
    "building_id", "interval_start_utc", "interval_end_utc", "electricity_kwh",
    "temperature_c", "relative_humidity_pct", "wind_speed_kmh", "wind_direction_deg",
    "direct_solar_radiation_wm2", "diffuse_solar_radiation_wm2",
)
METADATA_COLUMNS = (
    "floor_area_m2", "heated_area_m2", "building_use", "climate_zone",
    "year_opened", "number_of_floors", "ventilation_system_count",
    "ventilation_used_for_heating", "ventilation_used_for_cooling",
    "has_direct_electric_heating", "has_district_heating", "has_district_cooling",
    "has_heat_pump", "has_solar_pv",
)
INTENSITY_COLUMN = "electricity_kwh_per_m2"
APPENDED_COLUMNS = METADATA_COLUMNS + (INTENSITY_COLUMN,)
MISSING = {"", "missing", "unknown", "n/a", "na", "none", "null", "not available"}
GLOBAL_LABELS = {
    "gross total floor area": "floor_area_m2",
    "gross total heated area": "heated_area_m2",
    "year opened": "year_opened",
    "number of floors": "number_of_floors",
    "ventilation systems": "ventilation_system_count",
    "solar pv": "has_solar_pv",
}
VENTILATION_LABELS = {
    "used for space heating": "ventilation_used_for_heating",
    "used for space cooling": "ventilation_used_for_cooling",
}
HEATING_LABELS = {
    "direct electrical heating": "has_direct_electric_heating",
    "direct electric heating": "has_direct_electric_heating",
    "district heating": "has_district_heating",
    "district cooling": "has_district_cooling",
    "heat pump": "has_heat_pump",
}


class MetadataError(ValueError):
    """Invalid input identity, CSV structure, area, or output preservation."""


@dataclass
class BuildingInput:
    building: str
    source: Path
    info: Path
    destination: Path
    metadata: dict
    issues: dict


def whitespace(value):
    return " ".join(value.split())


def parse_value(field, raw):
    """Return a CSV-ready value or None, with a reason when it is unknown."""
    value = whitespace(raw)
    if value.casefold() in MISSING:
        return None, "explicitly missing"
    if field in {"building_use", "climate_zone"}:
        return value, None
    if field.endswith("_area_m2"):
        match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(?:sqm|m2|m²)", value, re.I)
        if match:
            area = Decimal(match.group(1))
            if area <= 0:
                raise MetadataError(f"{field}: supplied area must be positive, got {raw!r}")
            return format(area, "f"), None
        return None, "unrecognised area or unit"
    if field == "year_opened":
        match = re.fullmatch(r"(\d{4})(?:\s*\(renovated in \d{4}\))?", value, re.I)
        if match and int(match.group(1)) > 0:
            return int(match.group(1)), None
        return None, "unrecognised opening year"
    if field in {"number_of_floors", "ventilation_system_count"}:
        if re.fullmatch(r"\d+", value):
            return int(value), None
        return None, "unrecognised integer"
    if value.casefold() in {"yes", "no"}:
        return int(value.casefold() == "yes"), None
    return None, "expected explicit YES or NO"


def read_metadata(path, building):
    """Parse labelled fields, retaining all occurrences to detect conflicts."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        raise MetadataError(f"{path}: empty building-info file")
    title = re.fullmatch(r"(.+?)\s*\((L\d+_B\d+)\)", whitespace(lines[first]))
    if not title or title.group(2) != building or path.name != f"{building}-building_info.txt":
        raise MetadataError(f"{path}: title/filename does not identify expected building {building}")

    candidates = {field: [] for field in METADATA_COLUMNS}
    candidates["building_use"].append((first + 1, title.group(1).strip()))
    section = None
    for number, raw in enumerate(lines[first + 1:], first + 2):
        line = whitespace(raw)
        if line.casefold().startswith("note:"):
            break
        heading = re.fullmatch(r"§\s*\d+\s+(.+)", line)
        if heading:
            line = heading.group(1)
            heading_label = line.split("=", 1)[0].strip().casefold()
            if heading_label in {"heating & cooling system", "heating and cooling system"}:
                section = "heating"
            elif heading_label == "ventilation systems":
                section = "ventilation"
            else:
                section = None
        if re.match(r"climate\s+zone\s*:", line, re.I):
            candidates["climate_zone"].append((number, line.split(":", 1)[1].strip()))
        if "=" not in line:
            continue
        label, value = line.lstrip("- ").split("=", 1)
        label = whitespace(label).casefold()
        field = GLOBAL_LABELS.get(label)
        if section == "ventilation":
            field = field or VENTILATION_LABELS.get(label)
        elif section == "heating":
            # Parentheses describe equipment (e.g. ground source/electric boiler).
            base_label = re.sub(r"\s*\([^()]*\)\s*$", "", label).strip()
            field = field or HEATING_LABELS.get(base_label)
        if field:
            candidates[field].append((number, value.strip()))

    metadata, issues = {}, {}
    for field, entries in candidates.items():
        values, reasons = [], []
        for number, raw in entries:
            try:
                value, reason = parse_value(field, raw)
            except MetadataError as error:
                raise MetadataError(f"{path}, line {number}: {error}") from error
            values.append(value)
            if reason:
                reasons.append(f"line {number}: {raw!r} ({reason})")
        distinct = set(values)
        if not entries:
            metadata[field] = None
            issues[field] = "missing: label not found in the relevant section"
        elif len(distinct) > 1:
            metadata[field] = None
            issues[field] = "ambiguous/conflicting entries: " + "; ".join(
                f"line {number}: {raw!r}" for number, raw in entries
            )
        elif reasons:
            metadata[field] = None
            issues[field] = "; ".join(reasons)
        else:
            metadata[field] = values[0]
    return metadata, issues


def check_path(path):
    for component in (path, *path.parents):
        if component.is_symlink():
            raise MetadataError(f"Symbolic-link paths are not followed: {component}")


def electricity_per_m2(electricity, floor_area):
    """Return kWh/m² as decimal text, retaining zero/negative readings."""
    if floor_area is None or not str(floor_area).strip():
        return ""
    try:
        energy, area = Decimal(electricity.strip()), Decimal(str(floor_area))
    except InvalidOperation:
        return ""
    if not energy.is_finite() or not area.is_finite() or area <= 0:
        return ""
    with localcontext() as context:
        context.prec = 28
        return format(energy / area, "f")


def prepare_inputs(root):
    root = Path(root).expanduser().absolute()
    check_path(root)
    root = root.resolve()
    inputs = []
    for building in BUILDINGS:
        location = root / building.split("_")[0]
        # Exact source names intentionally exclude generated model_input CSVs.
        source = location / "unifieddataconsumption" / f"{building}_consumption_weather.csv"
        destination = source.with_name(f"{building}_model_input.csv")
        matches = sorted(location.rglob(f"{building}-building_info.txt"))
        if len(matches) != 1:
            raise MetadataError(f"{building}: expected one matching building-info file under {location}, found {len(matches)}")
        info = matches[0]
        for path in (source, info, destination):
            check_path(path)
        if destination.exists() and not destination.is_file():
            raise MetadataError(f"Output path is not a file: {destination}")
        if not source.is_file() or not info.is_file():
            raise MetadataError(f"{building}: required input missing: {source} or {info}")
        metadata, issues = read_metadata(info, building)
        inputs.append(BuildingInput(building, source, info, destination, metadata, issues))
    return inputs


def stage_csv(building, temporary):
    """Copy all original cells as strings, append metadata, and check identity."""
    count = 0
    with building.source.open(encoding="utf-8-sig", newline="") as source, temporary.open(
        "w", encoding="utf-8", newline=""
    ) as output:
        reader, writer = csv.reader(source, strict=True), csv.writer(output)
        headers = next(reader, [])
        if (len(headers) != len(set(headers)) or not set(EXISTING_COLUMNS).issubset(headers)
                or set(APPENDED_COLUMNS).intersection(headers)):
            raise MetadataError(f"{building.source}: invalid source columns: {headers!r}")
        identity = headers.index("building_id")
        energy_index = headers.index("electricity_kwh")
        appended = [building.metadata[field] for field in METADATA_COLUMNS]
        writer.writerow(headers + list(APPENDED_COLUMNS))
        for count, row in enumerate(reader, 1):
            if len(row) != len(headers) or row[identity] != building.building:
                raise MetadataError(f"{building.source}: data row {count}: invalid width or unexpected building_id; expected {building.building}")
            intensity = electricity_per_m2(row[energy_index], building.metadata["floor_area_m2"])
            writer.writerow(row + appended + [intensity])
    if count == 0:
        raise MetadataError(f"{building.source}: no rows; cannot verify building_id")
    return count


def verify_csv(building, temporary, expected_count):
    """Re-read staged CSV and compare every original cell in its original order."""
    appended = ["" if building.metadata[field] is None else str(building.metadata[field])
                for field in METADATA_COLUMNS]
    with building.source.open(encoding="utf-8-sig", newline="") as source, temporary.open(
        encoding="utf-8", newline=""
    ) as output:
        original, enriched = csv.reader(source, strict=True), csv.reader(output, strict=True)
        headers = next(original)
        energy_index = headers.index("electricity_kwh")
        if next(enriched, None) != headers + list(APPENDED_COLUMNS):
            raise MetadataError(f"{building.building}: output columns differ from expected")
        count = 0
        for count, (left, right) in enumerate(zip_longest(original, enriched), 1):
            if left is None or right is None:
                raise MetadataError(f"{building.building}: row counts differ at row {count}")
            intensity = electricity_per_m2(left[energy_index], building.metadata["floor_area_m2"])
            if right != left + appended + [intensity]:
                raise MetadataError(f"{building.building}: row count/order/values differ at row {count}")
        if count != expected_count:
            raise MetadataError(f"{building.building}: row count changed during verification")


def report_text(inputs, counts):
    lines = [
        "Building metadata report",
        "Empty metadata cells = missing/ambiguous; explicit YES/NO = 1/0.",
        "Heating/cooling flags exclude tap-water heating. Opening years exclude renovations.",
        "electricity_kwh_per_m2 = electricity_kwh / floor_area_m2 (28 significant digits);",
        "empty if reading is missing/non-numeric/non-finite or floor area is missing.",
        "Verified: matching CSV/TXT identity, positive supplied areas, row counts/order,",
        "all original headers/cells (including timestamps), and repeated metadata.",
    ]
    for building, count in zip(inputs, counts):
        lines.extend(["", f"{building.building}: {count} input rows = {count} output rows",
                      f"  Metadata source: {building.info}", f"  CSV source: {building.source}",
                      f"  Output: {building.destination}"])
        for field, value in building.metadata.items():
            lines.append(f"  {field}: {value if value is not None else '(empty)'}")
        lines.append("  Missing/ambiguous fields:")
        lines.extend(f"    {field}: {reason}" for field, reason in building.issues.items())
        if not building.issues:
            lines.append("    none")
    return "\n".join(lines) + "\n"


def write_outputs(inputs, report):
    """Stage and verify all seven tables and report before replacing outputs."""
    report = Path(report).expanduser().absolute()
    check_path(report)
    report = report.resolve()
    if report.exists() and not report.is_file():
        raise MetadataError(f"Report path is not a file: {report}")
    if report in {path for item in inputs for path in (item.source, item.info, item.destination)}:
        raise MetadataError("Report path must differ from all input/output data files")
    staged, counts = [], []
    try:
        for building in inputs:
            with tempfile.NamedTemporaryFile(dir=building.destination.parent, prefix=".metadata_", delete=False) as handle:
                temporary = Path(handle.name)
            staged.append((temporary, building.destination))
            count = stage_csv(building, temporary)
            verify_csv(building, temporary, count)
            counts.append(count)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=report.parent,
                                         prefix=".metadata_report_", delete=False) as handle:
            staged.append((Path(handle.name), report))
            handle.write(report_text(inputs, counts))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
    for building, count in zip(inputs, counts):
        print(f"[{building.building}] verified {count} rows; {len(building.issues)} missing/ambiguous fields -> {building.destination}")
    print(f"Metadata report: {report}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="BuildingsByLocation data directory")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="metadata report destination")
    args = parser.parse_args(argv)
    try:
        write_outputs(prepare_inputs(args.root), args.report)
    except (MetadataError, OSError, UnicodeError, csv.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
