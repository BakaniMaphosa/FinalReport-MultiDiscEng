"""Build seven separate electricity-consumption tables from explicit sources.

PROJECT ASSUMPTIONS
For L03 and L14, the source timestamp is chosen to mark the interval END.
The interval starts one hour earlier. This is a project convention, not a
claim that the source documentation establishes this timestamp convention.
Their energy values are used directly, without differencing or rescaling.

L03 retains its stated kWh unit. Its unresolved scale concern remains open:
this script does not verify or automatically correct the magnitude/unit scale.

L07 already contains processed hourly energy. Its existing interval bounds
are preserved; only energy_kwh is renamed to electricity_kwh. There is no
fallback to the original cumulative readings.

Numeric/missing value text is preserved without float conversion. Missing
timestamp fields remain empty; non-empty timestamps must have a timezone and
are formatted as UTC. Rows with missing start times sort last. Duplicate rows,
gaps, and missing values are not removed, filled, or otherwise cleaned.

The explicit OUTPUT FILES in the request use unifieddataconsumption, so that
directory name is used for all seven outputs. No L06, weather, metadata,
location totals, cross-building joins, or prediction targets are processed.
"""

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import tempfile


DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "Data" / "BuildingsByLocation"
OUTPUT_FOLDER = "unifieddataconsumption"
OUTPUT_COLUMNS = [
    "building_id", "interval_start_utc", "interval_end_utc", "electricity_kwh",
]
DIRECT_COLUMNS = ["timestamp [UTC]", "value Pt [Consumed active energy (kWh)]"]
PROCESSED_COLUMNS = ["interval_start_utc", "interval_end_utc", "energy_kwh"]


@dataclass(frozen=True)
class Source:
    building: str
    relative_path: str
    already_processed: bool = False


SOURCES = (
    Source("L03_B01", "L03/L03_B01/1h/adrenalin.1h.L03.B01.EM02.Pt.csv"),
    Source("L07_B01", "L07/L07_B01/processed/adrenalin.1h.L07.B01.EM01.Pt.hourly_energy.csv", True),
    Source("L14_B01", "L14/L14_B01/1h/adrenalin.1h.L14.B01.EM01.Pt.csv"),
    Source("L14_B02", "L14/L14_B02/1h/adrenalin.1h.L14.B02.EM01.Pt.csv"),
    Source("L14_B03", "L14/L14_B03/1h/adrenalin.1h.L14.B03.EM02.Pt.csv"),
    Source("L14_B04", "L14/L14_B04/1h/adrenalin.1h.L14.B04.EM02.Pt.csv"),
    Source("L14_B05", "L14/L14_B05/1h/adrenalin.1h.L14.B05.EM02.Pt.csv"),
)


class TableBuildError(ValueError):
    pass


def check_path(path):
    """Explicit inputs/outputs never traverse weather folders or symlinks."""
    for component in reversed((path, *path.parents)):
        if component.name.casefold().endswith("_ws"):
            raise TableBuildError(f"Weather directories are excluded: {component}")
        if component.is_symlink():
            raise TableBuildError(f"Symbolic-link paths are not used: {component}")


def parse_utc(text, path, row_number, column):
    if not text.strip():
        return None
    try:
        normalized = text.strip()
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        stamp = datetime.fromisoformat(normalized)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("timestamp has no timezone")
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise TableBuildError(
            f"{path}: data row {row_number}, column {column!r}: "
            f"invalid timestamp {text!r}: {error}"
        ) from error


def format_utc(stamp):
    return stamp.isoformat().replace("+00:00", "Z") if stamp is not None else ""


def read_source(root, source):
    """Return rows sorted in memory, preserving the energy field verbatim."""
    path = root / source.relative_path
    check_path(path)
    columns = PROCESSED_COLUMNS if source.already_processed else DIRECT_COLUMNS
    rows = []
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle, strict=True)
            headers = next(reader, [])
            missing = [column for column in columns if column not in headers]
            repeated = [column for column in columns if headers.count(column) > 1]
            if missing or repeated:
                raise TableBuildError(
                    f"{path}: required columns missing={missing}, repeated={repeated}; "
                    f"actual columns={headers!r}. No column guessing or source fallback is used."
                )
            indices = [headers.index(column) for column in columns]
            for number, fields in enumerate(reader, 1):
                # An absent trailing field is missing, not a zero or a dropped row.
                values = [fields[index] if index < len(fields) else "" for index in indices]
                if source.already_processed:
                    start = parse_utc(values[0], path, number, columns[0])
                    end = parse_utc(values[1], path, number, columns[1])
                    energy = values[2]
                else:
                    end = parse_utc(values[0], path, number, columns[0])
                    try:
                        start = end - timedelta(hours=1) if end is not None else None
                    except OverflowError as error:
                        raise TableBuildError(f"{path}: data row {number}: interval start is outside the datetime range.") from error
                    energy = values[1]
                rows.append((start, end, energy))
    except (OSError, UnicodeError, csv.Error) as error:
        raise TableBuildError(f"Cannot read required source {path}: {error}") from error
    latest = datetime.max.replace(tzinfo=timezone.utc)
    rows.sort(key=lambda row: (row[0] is None, row[0] if row[0] is not None else latest))
    return rows


def prepare_tables(root):
    """Validate/read all seven inputs before creating any output directories."""
    root = Path(root).expanduser().absolute()
    check_path(root)
    tables = []
    errors = []
    for source in SOURCES:
        try:
            rows = read_source(root, source)
            location = source.building.split("_")[0]
            destination = root / location / OUTPUT_FOLDER / f"{source.building}_consumption.csv"
            check_path(destination)
            if destination.parent.exists() and not destination.parent.is_dir():
                raise TableBuildError(f"Output folder is not a directory: {destination.parent}")
            if destination.exists() and not destination.is_file():
                raise TableBuildError(f"Output path is not a file: {destination}")
            tables.append((source, destination, rows))
        except (TableBuildError, OSError) as error:
            errors.append(str(error))
    if errors:
        raise TableBuildError("Input/output validation failed; no outputs were written:\n" + "\n".join(errors))
    return tables


def write_tables(tables):
    """Stage all CSVs, then replace generated outputs (safe to rerun)."""
    staged = []
    temporary_paths = []
    try:
        for source, destination, rows in tables:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=destination.parent,
                prefix=f".{source.building}_", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                temporary_paths.append(temporary)
                writer = csv.writer(handle)
                writer.writerow(OUTPUT_COLUMNS)
                writer.writerows(
                    (source.building, format_utc(start), format_utc(end), energy)
                    for start, end, energy in rows
                )
            staged.append((temporary, destination, len(rows)))
        for temporary, destination, count in staged:
            os.replace(temporary, destination)
            print(f"{destination}: {count} rows")
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT,
        help="input root (default: project Data/BuildingsByLocation, independent of working directory)",
    )
    args = parser.parse_args(argv)
    try:
        tables = prepare_tables(args.root)
        write_tables(tables)
    except (TableBuildError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
