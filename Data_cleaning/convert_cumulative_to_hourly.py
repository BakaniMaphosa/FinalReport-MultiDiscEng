"""Difference explicitly configured cumulative channels without editing sources.

Selection is controlled by cumulative_channels.json, not inferred from channel
names or the inspection script's numerical suggestions. L14 is never processed.
"""

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sys

from inspect_energy_readings import (
    ONE_HOUR, parse_headers, parse_timestamp, parse_value, stamp_text,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent / "Data" / "BuildingsByLocation"
DEFAULT_CONFIG = SCRIPT_DIR / "cumulative_channels.json"
BUILDING_PATTERN = re.compile(r"L[0-9]+_B[0-9]+", re.IGNORECASE)
LOCATION_PATTERN = re.compile(r"L[0-9]+", re.IGNORECASE)
CHANNEL_PATTERN = re.compile(r"(?:EM|ES)[0-9]+\.[A-Za-z][A-Za-z0-9]*", re.IGNORECASE)
ACCEPTED_COLUMNS = ["interval_start_utc", "interval_end_utc", "energy_kwh"]
EXCLUDED_COLUMNS = [
    "interval_start_utc", "interval_end_utc", "previous_reading_kwh",
    "current_reading_kwh", "difference_kwh", "exclusion_reason",
    "previous_source_row", "current_source_row",
]
LIMITATION = (
    "Intervals containing negative changes in confirmed cumulative energy\n"
    "readings, together with their immediately following intervals, were\n"
    "excluded. The causes of these decreases could not be established from\n"
    "the available documentation. This conservative treatment may discard\n"
    "valid observations following genuine counter resets, reduces temporal\n"
    "coverage, and does not resolve all possible measurement errors."
)


@dataclass(frozen=True)
class Channel:
    building: str
    name: str


@dataclass
class OriginalReading:
    source_row: int
    timestamp: datetime | None
    raw_value: str
    value: Decimal | None
    malformed: bool = False


@dataclass
class Interval:
    before: OriginalReading
    after: OriginalReading
    difference: Decimal | None
    reasons: list = field(default_factory=list)


class InputProblem(ValueError):
    """An input cannot be paired unambiguously or is not configured energy."""


def load_channels(config_path):
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputProblem(f"Cannot read channel configuration {config_path}: {error}") from error
    if not isinstance(config, dict) or not isinstance(config.get("cumulative_channels"), list):
        raise InputProblem("Configuration must contain a cumulative_channels list.")
    channels = []
    seen = set()
    for entry in config["cumulative_channels"]:
        if not isinstance(entry, dict):
            raise InputProblem("Each configured channel must be an object.")
        building, name = entry.get("building_id"), entry.get("channel")
        if not isinstance(building, str) or not BUILDING_PATTERN.fullmatch(building):
            raise InputProblem(f"Invalid building_id: {building!r}")
        if not isinstance(name, str) or not CHANNEL_PATTERN.fullmatch(name):
            raise InputProblem(f"Invalid channel: {name!r}; meter IDs use digits, including zero.")
        building = building.upper()
        if building.split("_")[0] == "L14":
            raise InputProblem(f"L14 is already hourly energy and cannot be configured: {building}/{name}")
        if entry.get("confirmed_cumulative") is not True:
            raise InputProblem(f"Channel is not explicitly confirmed cumulative: {building}/{name}")
        key = (building, name.casefold())
        if key in seen:
            raise InputProblem(f"Duplicate channel configuration: {building}/{name}")
        seen.add(key)
        channels.append(Channel(building, name))
    if not channels:
        raise InputProblem("No cumulative channels configured. Edit cumulative_channels.json or supply --config.")
    return channels


def check_path(path):
    """Never traverse weather folders or symbolic links, including root links."""
    for component in reversed((path, *path.parents)):
        if component.name.casefold().endswith("_ws"):
            raise InputProblem(f"Weather directories are excluded: {component}")
        if component.is_symlink():
            raise InputProblem(f"Symbolic links are not followed: {component}")


def find_sources(root, channels):
    root = Path(root).expanduser().absolute()
    check_path(root)
    targets = {(c.building, c.name.casefold()): c for c in channels}
    buildings = {c.building for c in channels}
    locations = {b.split("_")[0] for b in buildings}
    found = {c: [] for c in channels}
    errors = []

    def visit(directory, building=None, building_path=None, in_hourly=False):
        name = directory.name
        if name.casefold().endswith("_ws") or name.casefold() == "processed":
            return
        if LOCATION_PATTERN.fullmatch(name) and name.upper() not in locations:
            return
        if BUILDING_PATTERN.fullmatch(name):
            building = name.upper()
            if building not in buildings:
                return
            building_path, in_hourly = directory, False
        if name.casefold() == "1h" and building is not None:
            in_hourly = True
        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda e: e.name.casefold())
        except OSError as error:
            errors.append(f"Cannot read directory {directory}: {error}")
            return
        for entry in entries:
            path = directory / entry.name
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    visit(path, building, building_path, in_hourly)
                    continue
                if not in_hourly or not entry.is_file(follow_symlinks=False):
                    continue
            except OSError as error:
                errors.append(f"Cannot inspect {path}: {error}")
                continue
            parts = entry.name.split(".")
            if len(parts) < 7 or parts[-1].casefold() != "csv":
                continue
            frequency, location, building_id, meter, quantity = parts[-6:-1]
            if frequency.casefold() != "1h" or f"{location}_{building_id}".upper() != building:
                continue
            channel = targets.get((building, f"{meter}.{quantity}".casefold()))
            if channel:
                found[channel].append((path, building_path))

    building = building_path = None
    in_hourly = False
    for ancestor in reversed(root.parents):
        if LOCATION_PATTERN.fullmatch(ancestor.name) and ancestor.name.upper() not in locations:
            return found, errors
        if BUILDING_PATTERN.fullmatch(ancestor.name):
            building = ancestor.name.upper()
            if building not in buildings:
                return found, errors
            building_path, in_hourly = ancestor, False
        if ancestor.name.casefold() == "processed":
            return found, errors
        if ancestor.name.casefold() == "1h" and building is not None:
            in_hourly = True
    visit(root, building, building_path, in_hourly)
    return found, errors


def read_original_readings(source, channel):
    """Read all source rows; never drop a row to make a new adjacent pair."""
    readings = []
    invalid_timestamps = []
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            headers = next(reader, [])
            time_index, value_index, unit = parse_headers(headers, channel.name)
            if unit.casefold() != "kwh":
                raise InputProblem(f"Expected stated unit kWh, got {unit!r}; no unit conversion is performed.")
            for number, fields in enumerate(reader, 1):
                raw_timestamp = fields[time_index] if time_index < len(fields) else ""
                raw_value = fields[value_index] if value_index < len(fields) else ""
                timestamp = parse_timestamp(raw_timestamp)
                malformed = len(fields) != len(headers)
                if timestamp is None:
                    invalid_timestamps.append((number, raw_timestamp))
                readings.append(OriginalReading(
                    number, timestamp, raw_value,
                    parse_value(raw_value) if not malformed else None,
                    malformed,
                ))
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        raise InputProblem(f"Cannot process {source}: {error}") from error
    if invalid_timestamps:
        examples = "; ".join(f"row {n}: {text!r}" for n, text in invalid_timestamps[:10])
        raise InputProblem(
            f"{len(invalid_timestamps)} invalid/missing/naive timestamp(s): {examples}. "
            "Stopped: these original rows cannot be placed chronologically without guessing."
        )
    readings.sort(key=lambda r: r.timestamp)
    duplicates = defaultdict(list)
    for reading in readings:
        duplicates[reading.timestamp].append(reading.source_row)
    duplicates = {stamp: rows for stamp, rows in duplicates.items() if len(rows) > 1}
    if duplicates:
        details = "; ".join(f"{stamp_text(stamp)} (source rows {rows})" for stamp, rows in duplicates.items())
        raise InputProblem(f"Duplicate timestamps make chronological pairing ambiguous: {details}. Stopped this file.")
    return readings, headers


def calculate_intervals(readings):
    """Apply exclusions to adjacent original rows, not to a filtered series."""
    intervals = []
    previous_interval_was_negative = False
    for before, after in zip(readings, readings[1:]):
        difference = None
        reasons = []
        if after.timestamp - before.timestamp != ONE_HOUR:
            reasons.append("not_exactly_one_hour_apart")
        if before.value is None:
            reasons.append("invalid_previous_reading")
        if after.value is None:
            reasons.append("invalid_current_reading")
        if before.malformed or after.malformed:
            reasons.append("unexpected_source_column_count")
        if before.value is not None and after.value is not None:
            difference = after.value - before.value
        is_negative = difference is not None and difference < 0
        if is_negative:
            reasons.append("counter_decrease")
        if previous_interval_was_negative:
            reasons.append("possible_rebound_after_counter_decrease")
        intervals.append(Interval(before, after, difference, reasons))
        # Exactly the next original interval is protected, even across a gap
        # or invalid reading. Consecutive decreases each protect their next.
        previous_interval_was_negative = is_negative
    return intervals


def output_paths(source, building_path):
    directory = building_path / "processed"
    check_path(directory)
    if directory.exists() and not directory.is_dir():
        raise InputProblem(f"Output path is not a directory: {directory}")
    paths = (
        directory / f"{source.stem}.hourly_energy.csv",
        directory / f"{source.stem}.excluded_intervals.csv",
        directory / f"{source.stem}.processing_report.txt",
    )
    for path in paths:
        if path.is_symlink():
            raise InputProblem(f"Output symbolic links are not overwritten: {path}")
        if path == source:
            raise InputProblem(f"Refusing to overwrite source file: {path}")
    return paths


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def process_file(source, building_path, channel):
    accepted_path, excluded_path, report_path = output_paths(source, building_path)
    base_report = [
        f"Building: {channel.building}", f"Channel: {channel.name}", f"Source: {source}",
        "Selection: explicitly configured confirmed cumulative channel; no filename-based inference.",
        "The source CSV is preserved. Channels are kept separate and are not labelled total building consumption.",
        "No absolute differences, zero replacements, interpolation, outlier trimming, or weather merging are used.",
        "",
    ]
    try:
        readings, headers = read_original_readings(source, channel)
    except InputProblem as error:
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text("\n".join(base_report + [
            "STATUS: STOPPED", str(error),
            "No output CSVs were written in this run. Any pre-existing derived CSVs are unchanged prior-run outputs, not new results.",
            "", LIMITATION, "",
        ]), encoding="utf-8")
        print(f"STOPPED [{channel.building}/{channel.name}] {source}: {error}", file=sys.stderr)
        print("  retained=not generated; excluded=not generated; see " + str(report_path))
        return False

    intervals = calculate_intervals(readings)
    accepted = [i for i in intervals if not i.reasons]
    excluded = [i for i in intervals if i.reasons]
    reasons = Counter(reason for interval in excluded for reason in interval.reasons)
    report_path.parent.mkdir(exist_ok=True)
    write_csv(accepted_path, ACCEPTED_COLUMNS, (
        (stamp_text(i.before.timestamp), stamp_text(i.after.timestamp), str(i.difference))
        for i in accepted
    ))
    write_csv(excluded_path, EXCLUDED_COLUMNS, (
        (
            stamp_text(i.before.timestamp), stamp_text(i.after.timestamp),
            i.before.raw_value, i.after.raw_value,
            "" if i.difference is None else str(i.difference),
            ";".join(i.reasons), i.before.source_row, i.after.source_row,
        )
        for i in excluded
    ))
    report = base_report + [
        "STATUS: COMPLETE", "Exact source headers: " + json.dumps(headers, ensure_ascii=False),
        "Stated and derived unit: kWh", f"Original readings: {len(readings)}",
        f"Adjacent original intervals: {len(intervals)}",
        "The first reading is a baseline; it is not a separate interval.",
        f"Retained intervals: {len(accepted)}", f"Excluded intervals: {len(excluded)}",
        "Exclusion reason counts (a pair may have multiple reasons): " + json.dumps(dict(reasons), sort_keys=True),
        "A negative change across a gap also protects its immediately following original interval.",
        "Unparseable timestamps stop the file; missing/non-numeric values stay in place and exclude both touching pairs.",
        f"Accepted CSV: {accepted_path}", f"Excluded CSV: {excluded_path}",
        "", "LIMITATION", LIMITATION, "",
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"[{channel.building}/{channel.name}] {source}: retained={len(accepted)}, excluded={len(excluded)}")
    print(f"  Outputs: {accepted_path.parent}")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="building data root; default is project Data/BuildingsByLocation")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="explicit cumulative-channel JSON configuration")
    args = parser.parse_args(argv)
    try:
        channels = load_channels(args.config)
        found, errors = find_sources(args.root, channels)
    except (InputProblem, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print("Discovery was incomplete; no channels were processed.", file=sys.stderr)
        return 1
    failures = 0
    for channel in channels:
        matches = found[channel]
        if len(matches) != 1:
            print(
                f"ERROR [{channel.building}/{channel.name}]: expected exactly one source CSV in a 1h folder, found {len(matches)}. Channel skipped.",
                file=sys.stderr,
            )
            failures += 1
            continue
        source, building_path = matches[0]
        try:
            if not process_file(source, building_path, channel):
                failures += 1
        except (InputProblem, OSError) as error:
            failures += 1
            print(f"ERROR [{channel.building}/{channel.name}] {source}: {error}. Outputs may be incomplete; do not use them.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
