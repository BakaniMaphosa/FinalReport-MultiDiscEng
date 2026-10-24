"""Export one single-column target CSV per selected building.

Run from the project root: python3 Data_cleaning/export_prediction_targets.py
Reads <building_id>_model_input.csv and writes <building_id>_targets.csv in
the same directory. Copies electricity_kwh_per_m2 exactly, including empty
cells, in the original row order. Source files are unchanged.

Targets correspond to the same hourly rows as the source tables; no shifting,
filtering, splitting, or other modelling preprocessing is performed here.
The later modelling pipeline must exclude this target column and same-hour
electricity_kwh from predictors when predicting electricity_kwh_per_m2.
"""

import argparse
import csv
from itertools import zip_longest
import os
from pathlib import Path
import sys
import tempfile

from add_building_metadata import BUILDINGS, DEFAULT_ROOT, INTENSITY_COLUMN, MetadataError, check_path


def source_targets(path, building):
    """Yield raw target strings after validating the source schema/identity."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        headers = next(reader, [])
        if (len(headers) != len(set(headers))
                or not {"building_id", INTENSITY_COLUMN}.issubset(headers)):
            raise MetadataError(f"{path}: expected unique building_id and {INTENSITY_COLUMN} columns")
        identity, target = headers.index("building_id"), headers.index(INTENSITY_COLUMN)
        count = 0
        for count, row in enumerate(reader, 1):
            if len(row) != len(headers) or row[identity] != building:
                raise MetadataError(f"{path}: invalid row width or building_id at data row {count}")
            yield row[target]
        if count == 0:
            raise MetadataError(f"{path}: no target rows")


def export_targets(root):
    root = Path(root).expanduser().absolute()
    check_path(root)
    staged = []
    try:
        for building in BUILDINGS:
            directory = root / building.split("_")[0] / "unifieddataconsumption"
            source = directory / f"{building}_model_input.csv"
            destination = directory / f"{building}_targets.csv"
            for path in (source, destination):
                check_path(path)
            if destination.exists() and not destination.is_file():
                raise MetadataError(f"Output path is not a file: {destination}")
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=directory,
                prefix=".targets_", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                staged.append((temporary, destination, 0))
                writer = csv.writer(handle)
                writer.writerow([INTENSITY_COLUMN])
                count = 0
                for count, value in enumerate(source_targets(source, building), 1):
                    # A quoted empty field retains a row even when its target is missing.
                    writer.writerow([value])
            with temporary.open(encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle, strict=True)
                if next(reader, None) != [INTENSITY_COLUMN]:
                    raise MetadataError(f"{destination}: invalid target header")
                verified = 0
                for verified, (value, row) in enumerate(
                    zip_longest(source_targets(source, building), reader), 1
                ):
                    if value is None or row != [value]:
                        raise MetadataError(f"{destination}: target row {verified} differs from source")
                if verified != count:
                    raise MetadataError(f"{destination}: target row count differs from source")
            staged[-1] = (temporary, destination, count)
        # All seven exports must pass validation before any target is replaced.
        for temporary, destination, _ in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _, _ in staged:
            temporary.unlink(missing_ok=True)
    for _, destination, count in staged:
        print(f"{destination}: {count} aligned target rows")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="BuildingsByLocation data directory")
    args = parser.parse_args(argv)
    try:
        export_targets(args.root)
    except (MetadataError, OSError, UnicodeError, csv.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
