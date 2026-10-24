"""Select CSV channels by filename only; never read or transform CSV contents."""

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys


KEEP_CHANNELS = {
    "L03_B01": {"EM02.Pt"},
    "L06_B01": {"EM01.Pt", "EM01.ePt", "EM02.Pt"},
    "L07_B01": {"EM01.Pt"},
    "L14_B01": {"EM01.Pt"},
    "L14_B02": {"EM01.Pt"},
    "L14_B03": {"EM02.Pt"},
    "L14_B04": {"EM02.Pt"},
    "L14_B05": {"EM02.Pt"},
}
ALLOWED_CHANNELS = {
    building: {channel.casefold() for channel in channels}
    for building, channels in KEEP_CHANNELS.items()
}
LOCATIONS = {building.split("_")[0] for building in KEEP_CHANNELS}
BUILDING_NAME = re.compile(r"L[0-9]+_B[0-9]+", re.IGNORECASE)
LOCATION_NAME = re.compile(r"L[0-9]+", re.IGNORECASE)


@dataclass
class BuildingSummary:
    folders: int = 0
    hourly_folders: int = 0
    retained: int = 0
    deleted: int = 0
    errors: int = 0


def matches_channel(filename, building):
    """Match complete trailing 1h.location.building.meter.quantity.csv parts."""
    parts = filename.split(".")
    if len(parts) < 7 or parts[-1].casefold() != "csv":
        return False
    interval, location, building_id, meter, quantity = parts[-6:-1]
    return (
        interval.casefold() == "1h"
        and f"{location}_{building_id}".upper() == building
        and f"{meter}.{quantity}".casefold() in ALLOWED_CHANNELS[building]
    )


def filter_csv_files(root):
    """Delete unwanted CSVs under listed buildings' 1h folders.

    Return (summaries, error_count). Preserve non-CSV files, directory
    structure, weather folders, symbolic links, and unlisted buildings.
    """
    # Do not resolve the input: resolving would follow symbolic links.
    root = Path(root).expanduser().absolute()
    summaries = {building: BuildingSummary() for building in KEEP_CHANNELS}
    error_count = 0

    def report_error(path, action, error, building=None):
        nonlocal error_count
        error_count += 1
        if building in summaries:
            summaries[building].errors += 1
        print(f"ERROR: cannot {action} {path}: {error}", file=sys.stderr)

    # Reject symlinks in the supplied root, including its parent path.
    for component in reversed((root, *root.parents)):
        try:
            if component.is_symlink():
                report_error(component, "use symbolic-link root path", "links are not followed")
                return summaries, error_count
        except OSError as error:
            report_error(component, "inspect root path", error)
            return summaries, error_count

    def visit(directory, building=None, in_hourly=False):
        name = directory.name
        if name.casefold().endswith("_ws"):
            return
        if LOCATION_NAME.fullmatch(name) and name.upper() not in LOCATIONS:
            return
        if BUILDING_NAME.fullmatch(name):
            building = name.upper()
            if building not in KEEP_CHANNELS:
                return
            summaries[building].folders += 1
            in_hourly = False
        if building is not None and name.casefold() == "1h":
            summaries[building].hourly_folders += 1
            in_hourly = True

        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda entry: entry.name.casefold())
        except OSError as error:
            report_error(directory, "read directory", error, building)
            return

        for entry in entries:
            path = directory / entry.name
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    visit(path, building, in_hourly)
                    continue
                if building is None or not in_hourly:
                    continue
                if path.suffix.casefold() != ".csv":
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError as error:
                report_error(path, "inspect entry", error, building)
                continue

            if matches_channel(entry.name, building):
                summaries[building].retained += 1
                print(f"RETAINED [{building}] {path}")
            else:
                try:
                    path.unlink()
                except OSError as error:
                    report_error(path, "delete file", error, building)
                    continue
                summaries[building].deleted += 1
                print(f"DELETED  [{building}] {path}")

    # Also support a root pointing directly into a listed building.
    building = None
    in_hourly = False
    for ancestor in reversed(root.parents):
        name = ancestor.name
        if name.casefold().endswith("_ws"):
            return summaries, error_count
        if LOCATION_NAME.fullmatch(name) and name.upper() not in LOCATIONS:
            return summaries, error_count
        if BUILDING_NAME.fullmatch(name):
            building = name.upper()
            if building not in KEEP_CHANNELS:
                return summaries, error_count
            in_hourly = False
        if building is not None and name.casefold() == "1h":
            in_hourly = True
    if building is not None:
        summaries[building].folders += 1
    visit(root, building, in_hourly)
    return summaries, error_count


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Delete unwanted CSV channels in selected buildings' 1h folders."
    )
    parser.add_argument(
        "--root", type=Path, default=Path("./datasets"),
        help="dataset directory (default: ./datasets)",
    )
    args = parser.parse_args(argv)
    summaries, errors = filter_csv_files(args.root)
    for building, summary in summaries.items():
        print(
            f"SUMMARY [{building}]: {summary.folders} building folder(s), "
            f"{summary.hourly_folders} 1h folder(s), {summary.retained} retained, "
            f"{summary.deleted} deleted, {summary.errors} error(s)"
        )
    print(f"TOTAL ERRORS: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
