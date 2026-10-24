"""Read-only inspection of the ten selected electricity channels.

No readings are changed, converted to consumption, filtered, or merged.
The only file written is energy_readings_report.txt beside this script.
"""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
from statistics import median
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPT_DIR.parent / "Data" / "BuildingsByLocation"
REPORT_PATH = SCRIPT_DIR / "energy_readings_report.txt"
TARGETS = (
    ("L03_B01", "EM02.Pt"),
    ("L06_B01", "EM01.Pt"),
    ("L06_B01", "EM01.ePt"),
    ("L06_B01", "EM02.Pt"),
    ("L07_B01", "EM01.Pt"),
    ("L14_B01", "EM01.Pt"),
    ("L14_B02", "EM01.Pt"),
    ("L14_B03", "EM02.Pt"),
    ("L14_B04", "EM02.Pt"),
    ("L14_B05", "EM02.Pt"),
)
TARGET_LOOKUP = {(b.casefold(), c.casefold()): (b, c) for b, c in TARGETS}
BUILDINGS = {building for building, _ in TARGETS}
LOCATIONS = {building.split("_")[0] for building in BUILDINGS}
BUILDING_PATTERN = re.compile(r"L[0-9]+_B[0-9]+", re.IGNORECASE)
LOCATION_PATTERN = re.compile(r"L[0-9]+", re.IGNORECASE)
ONE_HOUR = timedelta(hours=1)


@dataclass
class Reading:
    row: int
    raw_timestamp: str
    raw_value: str
    timestamp: datetime | None
    value: Decimal | None
    shape_ok: bool = True


@dataclass
class Difference:
    before: Reading
    after: Reading
    change: Decimal
    elapsed: timedelta


@dataclass
class Inspection:
    building: str
    channel: str
    path: Path | None
    headers: list = field(default_factory=list)
    stated_unit: str = "unknown"
    row_count: int | None = None
    readings: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    error: str | None = None
    metrics: dict = field(default_factory=dict)
    suggested_interpretation: str = "manual review required"
    evidence: str = ""
    requires_review: bool = True


def target_for_filename(filename, building):
    parts = filename.split(".")
    if len(parts) < 7 or parts[-1].casefold() != "csv":
        return None
    interval, location, building_id, meter, quantity = parts[-6:-1]
    if interval.casefold() != "1h":
        return None
    if f"{location}_{building_id}".upper() != building:
        return None
    return TARGET_LOOKUP.get((building.casefold(), f"{meter}.{quantity}".casefold()))


def discover_files(root):
    """Locate selected CSVs without opening other files or following links."""
    found = {target: [] for target in TARGETS}
    errors = []
    root = Path(root).expanduser().absolute()
    for part in reversed((root, *root.parents)):
        if part.name.casefold().endswith("_ws"):
            errors.append(f"Root is inside an excluded weather directory: {part}")
            return found, errors
        if part.is_symlink():
            errors.append(f"Symbolic-link root paths are not followed: {part}")
            return found, errors

    def walk_error(error):
        errors.append(f"Cannot read directory {error.filename}: {error}")

    for current, directories, filenames in os.walk(root, onerror=walk_error, followlinks=False):
        directory = Path(current)
        parts = directory.parts
        if any(
            (LOCATION_PATTERN.fullmatch(part) and part.upper() not in LOCATIONS)
            or (BUILDING_PATTERN.fullmatch(part) and part.upper() not in BUILDINGS)
            for part in parts
        ):
            directories[:] = []
            continue
        directories[:] = sorted(
            name for name in directories
            if not name.casefold().endswith("_ws")
            and not (directory / name).is_symlink()
            and not (BUILDING_PATTERN.fullmatch(name) and name.upper() not in BUILDINGS)
            and not (LOCATION_PATTERN.fullmatch(name) and name.upper() not in LOCATIONS)
        )
        building_indices = [i for i, part in enumerate(parts) if part.upper() in BUILDINGS]
        if not building_indices:
            continue
        index = building_indices[-1]
        building = parts[index].upper()
        if not any(part.casefold() == "1h" for part in parts[index + 1:]):
            continue
        for filename in sorted(filenames):
            target = target_for_filename(filename, building)
            if target is None:
                continue
            path = directory / filename
            try:
                if not path.is_symlink() and path.is_file():
                    found[target].append(path)
            except OSError as error:
                errors.append(f"Cannot inspect selected file {path}: {error}")
    return found, errors


def parse_timestamp(text):
    """Require an explicit timezone, then represent the instant in UTC."""
    try:
        text = text.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        stamp = datetime.fromisoformat(text)
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return None
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def parse_value(text):
    try:
        value = Decimal(text.strip())
        return value if value.is_finite() else None
    except InvalidOperation:
        return None


def parse_headers(headers, channel):
    timestamps = [i for i, h in enumerate(headers) if re.fullmatch(r"timestamp\s*\[UTC\]", h.strip(), re.I)]
    values = []
    for index, header in enumerate(headers):
        match = re.fullmatch(r"value\s+(\S+)\s*\[(.+)\]", header.strip(), re.I)
        if match:
            values.append((index, match))
    quantity = channel.split(".")[1]
    if len(headers) != 2 or len(timestamps) != 1 or len(values) != 1:
        raise ValueError(
            "Unexpected columns: expected exactly timestamp [UTC] and "
            f"value {quantity} [description (unit)]; no columns were guessed."
        )
    value_index, match = values[0]
    if match.group(1).casefold() != quantity.casefold():
        raise ValueError(f"Unexpected quantity column: expected {quantity}, got {match.group(1)}.")
    description = match.group(2)
    unit = re.search(r"\(([^()]+)\)\s*$", description)
    return timestamps[0], value_index, unit.group(1) if unit else "unknown"


def analyze_readings(readings):
    """Compare adjacent chronological rows; never bridge invalid/duplicate rows."""
    ordered = sorted(
        (reading for reading in readings if reading.timestamp is not None),
        key=lambda reading: (reading.timestamp, reading.row),
    )
    timestamp_counts = Counter(reading.timestamp for reading in ordered)
    duplicates = defaultdict(list)
    for reading in ordered:
        if timestamp_counts[reading.timestamp] > 1:
            duplicates[reading.timestamp].append(reading)
    untimed_rows = sorted(reading.row for reading in readings if reading.timestamp is None)
    pairs = []
    ambiguous_pairs = missing_value_pairs = untimed_barrier_pairs = non_hourly_pairs = 0
    for before, after in zip(ordered, ordered[1:]):
        elapsed = after.timestamp - before.timestamp
        if elapsed != ONE_HOUR:
            non_hourly_pairs += 1
        if before.timestamp in duplicates or after.timestamp in duplicates:
            ambiguous_pairs += 1
            continue
        if before.value is None or after.value is None:
            missing_value_pairs += 1
            continue
        low, high = sorted((before.row, after.row))
        if bisect_right(untimed_rows, low) < bisect_left(untimed_rows, high):
            untimed_barrier_pairs += 1
            continue
        pairs.append(Difference(before, after, after.value - before.value, elapsed))
    values = [reading.value for reading in readings if reading.value is not None]
    return {
        "ordered": ordered,
        "values": values,
        "duplicates": dict(duplicates),
        "pairs": pairs,
        "hourly_pairs": [pair for pair in pairs if pair.elapsed == ONE_HOUR],
        "timestamp_pairs": max(len(ordered) - 1, 0),
        "non_hourly_pairs": non_hourly_pairs,
        "ambiguous_pairs": ambiguous_pairs,
        "missing_value_pairs": missing_value_pairs,
        "untimed_barrier_pairs": untimed_barrier_pairs,
        "invalid_timestamps": len(untimed_rows),
        "invalid_values": sum(reading.value is None for reading in readings),
        "malformed_rows": sum(not reading.shape_ok for reading in readings),
    }


def direction_counts(pairs):
    return (
        sum(pair.change > 0 for pair in pairs),
        sum(pair.change < 0 for pair in pairs),
        sum(pair.change == 0 for pair in pairs),
    )


def interpret(result):
    """Produce cautious numerical suggestions, never approval to convert data."""
    documented = result.building.startswith("L14_")
    if documented:
        result.suggested_interpretation = "documented hourly energy; manual review required"
    if result.error:
        result.evidence = result.error
        if documented:
            result.evidence = "Documented hourly energy (provided interpretation); " + result.evidence
        return
    metrics = result.metrics
    values, hourly = metrics["values"], metrics["hourly_pairs"]
    increases, decreases, _ = direction_counts(hourly)
    count = len(hourly)
    concerns = bool(
        result.issues or metrics["invalid_timestamps"] or metrics["invalid_values"]
        or metrics["duplicates"] or metrics["malformed_rows"]
    )
    basis = "Documented hourly energy (provided L14 interpretation). " if documented else "Numerical suggestion only; no interval/counter documentation assumed. "
    if not values or min(values) == max(values):
        reason = "No valid numeric readings." if not values else (
            "All-zero series; values alone cannot establish counter versus hourly energy."
            if values[0] == 0 else "Constant series; values alone cannot establish counter versus hourly energy."
        )
        result.evidence = basis + reason
        return
    if count < 24:
        result.evidence = basis + f"Only {count} eligible one-hour pairs; insufficient one-hour evidence for this heuristic."
        return

    positive_steps = [pair.change for pair in hourly if pair.change > 0]
    absolute_steps = [abs(pair.change) for pair in hourly if pair.change != 0]
    span = max(values) - min(values)
    level = median([abs(value) for value in values])
    typical_positive = median(positive_steps) if positive_steps else Decimal(0)
    typical_absolute = median(absolute_steps) if absolute_steps else Decimal(0)
    variation = sum(absolute_steps, Decimal(0))
    balance = abs(sum((pair.change for pair in hourly), Decimal(0))) / variation if variation else Decimal(0)
    counter_like = (
        increases >= 10 and Decimal(decreases) / count <= Decimal("0.02")
        and typical_positive > 0 and span >= 20 * typical_positive
        and level >= 20 * typical_positive
    )
    hourly_like = (
        Decimal(increases) / count >= Decimal("0.10")
        and Decimal(decreases) / count >= Decimal("0.10")
        and balance <= Decimal("0.25")
        and typical_absolute > 0 and span <= 100 * typical_absolute
    )
    if documented:
        if increases and decreases and min(values) >= 0 and not counter_like:
            result.suggested_interpretation = "documented hourly energy"
            result.evidence = basis + "Nonnegative readings rise and fall over one-hour pairs; observed behaviour is consistent, not proof."
            result.requires_review = concerns
        else:
            result.evidence = basis + "Observed behaviour does not clearly corroborate the documentation; a rising run alone does not disprove hourly energy."
    elif counter_like:
        result.suggested_interpretation = "suggested cumulative energy"
        result.evidence = (
            basis + f"{increases}/{count} one-hour increases, {decreases} decreases; "
            f"median absolute reading / median positive step = {level / typical_positive:.2f}, "
            f"reading span / median positive step = {span / typical_positive:.2f}. "
            "Counter-like levels and trajectory; decreases may be resets/corrections. Metadata/manual review is still required."
        )
    elif hourly_like:
        result.suggested_interpretation = "suggested hourly energy"
        result.evidence = (
            basis + f"{increases} increases and {decreases} decreases in {count} one-hour pairs; "
            f"absolute signed change / total absolute change = {balance:.3f}; "
            f"span / median absolute step = {span / typical_absolute:.2f}. "
            "Bounded, bidirectional variation suggests interval values; metadata/manual review is still required."
        )
    else:
        result.evidence = basis + "Direction, scale, and available one-hour comparisons do not give a decisive counter/hourly pattern."
    if concerns:
        result.evidence += " Missing/invalid entries, duplicate timestamps, or schema/unit issues also require review."


def inspect_file(building, channel, path, issues=()):
    result = Inspection(building, channel, path, issues=list(issues))
    if path is None:
        result.error = "MISSING FILE: no matching selected CSV was found in a 1h folder."
        interpret(result)
        return result
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            result.headers = next(reader, [])
            try:
                time_index, value_index, result.stated_unit = parse_headers(result.headers, channel)
            except ValueError as error:
                result.error = str(error)
                result.row_count = sum(1 for _ in reader)
                interpret(result)
                return result
            if result.stated_unit == "unknown":
                result.issues.append("Stated unit could not be extracted from the value header.")
            for row_number, row in enumerate(reader, 1):
                shape_ok = len(row) == len(result.headers)
                raw_time = row[time_index] if time_index < len(row) else ""
                raw_value = row[value_index] if value_index < len(row) else ""
                result.readings.append(Reading(
                    row_number, raw_time, raw_value,
                    parse_timestamp(raw_time) if shape_ok else None,
                    parse_value(raw_value) if shape_ok else None,
                    shape_ok,
                ))
            result.row_count = len(result.readings)
    except (OSError, UnicodeError, csv.Error) as error:
        result.error = f"Cannot completely read CSV: {error}; no inference from a partial read."
        interpret(result)
        return result
    result.metrics = analyze_readings(result.readings)
    interpret(result)
    if result.issues:
        result.requires_review = True
    return result


def stamp_text(stamp):
    return stamp.isoformat().replace("+00:00", "Z")


def number_text(value):
    return "N/A" if value is None else str(value)


def range_text(values):
    if not values:
        return "minimum=N/A, median=N/A, maximum=N/A"
    return f"minimum={min(values)}, median={median(values)}, maximum={max(values)}"


def pair_statistics(title, pairs):
    lines = [f"{title}: {len(pairs)} eligible pair(s)"]
    for label, count in zip(("Increases", "Decreases", "Unchanged"), direction_counts(pairs)):
        percentage = f"{100 * count / len(pairs):.4f}%" if pairs else "N/A"
        lines.append(f"  {label}: {count} ({percentage})")
    lines.append("  Consecutive differences: " + range_text([pair.change for pair in pairs]))
    return lines


def render_file(result):
    lines = [
        "=" * 100,
        f"Building: {result.building} | Channel: {result.channel}",
        f"File path: {result.path or 'MISSING'}",
        "Exact column headers: " + json.dumps(result.headers, ensure_ascii=False),
        f"Stated unit: {result.stated_unit}",
        f"Total data rows (excluding header; blank/malformed records counted): {number_text(result.row_count)}",
    ]
    for issue in result.issues:
        lines.append(f"NOTICE: {issue}")
    if result.error:
        lines.extend([f"ERROR: {result.error}", "Statistics unavailable; columns/rows were not guessed."])
    else:
        m = result.metrics
        ordered = m["ordered"]
        lines.extend([
            f"Valid finite numeric readings: {len(m['values'])}",
            f"Missing/non-numeric/non-finite or malformed readings: {m['invalid_values']}",
            f"Valid UTC timestamps: {len(ordered)}; missing/invalid/naive timestamps: {m['invalid_timestamps']}",
            f"Rows with an unexpected column count: {m['malformed_rows']}",
            f"First timestamp (chronological UTC): {stamp_text(ordered[0].timestamp) if ordered else 'N/A'}",
            f"Last timestamp (chronological UTC): {stamp_text(ordered[-1].timestamp) if ordered else 'N/A'}",
            "Reading statistics (all finite numeric readings, original stated unit): " + range_text(m["values"]),
        ])
        for label, sample in (("First 10", ordered[:10]), ("Last 10", ordered[-10:])):
            lines.append(f"{label} timestamp/value pairs (chronological UTC; raw value text preserved):")
            for reading in sample:
                status = "" if reading.value is not None else " [not a valid numeric reading]"
                lines.append(f"  row {reading.row}: {stamp_text(reading.timestamp)} | {reading.raw_value!r}{status}")
            if not sample:
                lines.append("  N/A")
        invalid_rows = [r for r in result.readings if r.timestamp is None]
        if invalid_rows:
            lines.append("Unplaceable timestamp/malformed row examples (up to 10):")
            for reading in invalid_rows[:10]:
                lines.append(f"  row {reading.row}: timestamp={reading.raw_timestamp!r}, value={reading.raw_value!r}, columns_ok={reading.shape_ok}")
        duplicates = m["duplicates"]
        lines.append(
            f"Duplicate timestamps: {len(duplicates)} distinct timestamp(s), "
            f"{sum(len(rows) for rows in duplicates.values())} affected rows, "
            f"{sum(len(rows) - 1 for rows in duplicates.values())} extra occurrences"
        )
        for timestamp, rows in duplicates.items():
            lines.append(f"  {stamp_text(timestamp)}: rows {[r.row for r in rows]}, values {[r.raw_value for r in rows]!r}")
        lines.extend([
            f"Consecutive chronological timestamp pairs: {m['timestamp_pairs']}",
            f"Timestamp pairs NOT exactly one hour apart (including zero-duration duplicates): {m['non_hourly_pairs']}",
            f"Pairs excluded because either timestamp is duplicated: {m['ambiguous_pairs']}",
            f"Further pairs excluded for missing/non-numeric readings: {m['missing_value_pairs']}",
            f"Further pairs excluded across unplaceable source rows: {m['untimed_barrier_pairs']}",
        ])
        lines.extend(pair_statistics("All valid consecutive comparisons, including gaps (not hourly energy)", m["pairs"]))
        lines.extend(pair_statistics("Exactly-one-hour consecutive comparisons ONLY", m["hourly_pairs"]))
        lines.append("Decrease examples (up to 10 eligible chronological pairs; elapsed time explicitly shown):")
        decreases = [pair for pair in m["pairs"] if pair.change < 0]
        for pair in decreases[:10]:
            lines.append(
                f"  {stamp_text(pair.before.timestamp)} | {pair.before.raw_value!r} -> "
                f"{stamp_text(pair.after.timestamp)} | {pair.after.raw_value!r}; "
                f"difference={pair.change}; elapsed={pair.elapsed}"
            )
        if not decreases:
            lines.append("  None among eligible pairs.")
    lines.extend([
        f"Suggested interpretation: {result.suggested_interpretation}",
        f"Evidence: {result.evidence}",
        f"Requires review: {'yes - manual review required' if result.requires_review else 'no (documented interpretation and observed behaviour are consistent)'}",
        "",
    ])
    return lines


def build_report(root, destination=REPORT_PATH):
    found, discovery_errors = discover_files(root)
    results = []
    for building, channel in TARGETS:
        paths = found[(building, channel)]
        issues = []
        if len(paths) > 1:
            issues.append(f"Multiple selected files ({len(paths)}) match this building/channel; each is inspected separately, never merged. Manual review required.")
        for path in paths or [None]:
            results.append(inspect_file(building, channel, path, issues))
    lines = [
        "ENERGY READINGS INSPECTION - READ ONLY",
        f"Data root: {Path(root).expanduser().absolute()}",
        f"Report destination: {destination}",
        "Scope: ten selected channels in building 1h folders; weather folders and symbolic links skipped.",
        "Source files are never modified, converted, filtered, or merged. No outlier removal is performed.",
        "Numbers and differences retain the stated unit. A difference is a numerical comparison, not approved consumption.",
        "Data rows are sorted in memory by timezone-aware UTC timestamp. Naive/invalid timestamps are not assigned a timezone.",
        "Duplicate timestamps are reported; every comparison touching any occurrence is excluded, even if duplicate values agree.",
        "Missing/non-numeric rows remain barriers. No comparison bridges them. Unplaceable timestamp rows also block pairs spanning them in source-row order.",
        "All-interval comparisons include gaps and are explicitly separate from exactly-one-hour statistics.",
        "Documented basis: the selected L14 channels are treated as hourly energy, as specified in the inspection requirements.",
        "Other interpretations are numerical suggestions only. Pt/ePt names and units do not establish interval versus counter semantics.",
        "Heuristic suggestions require >=24 one-hour pairs plus direction AND scale evidence; no monotonicity threshold approves conversion.",
        "Counter-like suggestion: >=10 increases, <=2% decreases, and both median absolute level and span >=20 median positive one-hour steps.",
        "Hourly-like suggestion: >=10% increases and >=10% decreases, absolute signed/absolute total change <=0.25, and span <=100 median absolute one-hour steps.",
        "These are exploratory heuristics, not proofs. Counter resets/corrections and rising/constant hourly runs are possible.",
        "All non-L14 suggestions still require manual metadata review; constant/all-zero/insufficient or indecisive series require manual review.",
        "Percentages use the eligible pair count printed for their comparison group; comparisons use exact numeric equality, without tolerance filtering.",
        "",
    ]
    for error in discovery_errors:
        lines.append(f"DISCOVERY ERROR: {error}")
    for result in results:
        lines.extend(render_file(result))
    lines.extend([
        "SUMMARY TABLE",
        "building_id | channel | stated_unit | suggested_interpretation | evidence | requires_review",
    ])
    for result in results:
        cells = (
            result.building, result.channel, result.stated_unit,
            result.suggested_interpretation, result.evidence,
            "yes - manual review required" if result.requires_review else "no",
        )
        lines.append(" | ".join(str(cell).replace("|", "/").replace("\n", " ") for cell in cells))
    structural_error = bool(discovery_errors or any(result.error or result.issues for result in results))
    return "\n".join(lines) + "\n", results, structural_error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT,
        help=f"building data directory (default, independent of working directory: {DEFAULT_ROOT})",
    )
    args = parser.parse_args(argv)
    report, _, structural_error = build_report(args.root, REPORT_PATH)
    print(report, end="")
    try:
        REPORT_PATH.write_text(report, encoding="utf-8")
    except OSError as error:
        print(f"ERROR: cannot save report to {REPORT_PATH}: {error}", file=sys.stderr)
        return 1
    return 1 if structural_error else 0


if __name__ == "__main__":
    sys.exit(main())
