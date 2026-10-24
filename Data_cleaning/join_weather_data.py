"""Left-join location weather onto seven separate consumption tables.

Prediction time is interval_start_utc. Weather is joined only on exact UTC
timestamp equality, without shifting electricity values or interval bounds.

MODELLING ASSUMPTION
Weather labelled at the prediction time is treated as available at
that time. The source contains historical weather/reanalysis rather
than an operational feed, so actual publication latency and weather
aggregation timing are not established by this join.

Measurement headers and stated units are read from the weather CSVs. Units
must agree with the output-column names; no unit conversion is performed.
Energy and weather values are copied as text without scaling or rounding.
Missing weather stays missing; negative or unusual measurements are retained.
Missing-value counts recognise blank, NA, N/A, NaN, null, and None tokens,
case-insensitively, for reporting only; existing tokens are not rewritten.

All input schemas and weather timestamp uniqueness are checked before output
files are written. No source files, L06 files, or building metadata are changed.
Explicit input filenames prevent generated outputs from becoming inputs.
"""

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile


DEFAULT_ROOT = Path(__file__).resolve().parent.parent / "Data" / "BuildingsByLocation"
BUILDINGS = ("L03_B01", "L07_B01", "L14_B01", "L14_B02", "L14_B03", "L14_B04", "L14_B05")
CONSUMPTION_COLUMNS = ["building_id", "interval_start_utc", "interval_end_utc", "electricity_kwh"]
WEATHER_COLUMNS = {
    "T": "temperature_c",
    "Rh": "relative_humidity_pct",
    "Ws": "wind_speed_kmh",
    "Wd": "wind_direction_deg",
    "Rd": "direct_solar_radiation_wm2",
    "Rr": "diffuse_solar_radiation_wm2",
}
EXPECTED_UNITS = {
    "T": {"deg c", "°c"}, "Rh": {"%"}, "Ws": {"km/h"},
    "Wd": {"deg", "°"}, "Rd": {"w/m^2", "w/m²"}, "Rr": {"w/m^2", "w/m²"},
}
OUTPUT_COLUMNS = CONSUMPTION_COLUMNS + list(WEATHER_COLUMNS.values())
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none"}
MODELLING_ASSUMPTION = (
    "Weather labelled at the prediction time is treated as available at "
    "that time. The source contains historical weather/reanalysis rather "
    "than an operational feed, so actual publication latency and weather "
    "aggregation timing are not established by this join."
)


class WeatherJoinError(ValueError):
    pass


@dataclass
class WeatherSeries:
    path: Path
    headers: list
    stated_unit: str
    values: dict


@dataclass
class ConsumptionRow:
    prediction_time: datetime | None
    columns: list


@dataclass
class BuildingInput:
    building: str
    source: Path
    destination: Path
    rows: list


def check_path(path):
    # This step intentionally reads _WS directories, but never follows links.
    for component in reversed((path, *path.parents)):
        if component.is_symlink():
            raise WeatherJoinError(f"Symbolic-link paths are not followed: {component}")


def parse_utc(text, path, row_number, column, allow_missing=False):
    if not text.strip() and allow_missing:
        return None
    try:
        normalized = text.strip()
        if normalized.endswith(("Z", "z")):
            normalized = normalized[:-1] + "+00:00"
        timestamp = datetime.fromisoformat(normalized)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("an explicit timezone is required")
        return timestamp.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise WeatherJoinError(
            f"{path}: data row {row_number}, {column!r}: invalid timestamp {text!r}: {error}"
        ) from error


def format_utc(timestamp):
    return timestamp.isoformat().replace("+00:00", "Z") if timestamp is not None else ""


def weather_header_indices(headers, quantity, path):
    timestamps = [i for i, name in enumerate(headers) if re.fullmatch(r"timestamp\s*\[UTC\]", name.strip(), re.I)]
    measurements = []
    for index, name in enumerate(headers):
        match = re.fullmatch(r"value\s+(\S+)\s*\[(.+)\]", name.strip(), re.I)
        if match and match.group(1).casefold() == quantity.casefold():
            measurements.append((index, match.group(2)))
    if len(headers) != 2 or len(timestamps) != 1 or len(measurements) != 1:
        raise WeatherJoinError(
            f"{path}: unexpected weather column structure {headers!r}; expected exactly "
            f"timestamp [UTC] and value {quantity} [description (unit)]."
        )
    value_index, description = measurements[0]
    unit_match = re.search(r"\(([^()]+)\)\s*$", description)
    if not unit_match:
        raise WeatherJoinError(f"{path}: no stated measurement unit found in {headers[value_index]!r}.")
    stated_unit = unit_match.group(1)
    if stated_unit.strip().casefold() not in EXPECTED_UNITS[quantity]:
        raise WeatherJoinError(
            f"{path}: stated unit {stated_unit!r} does not agree with output column "
            f"{WEATHER_COLUMNS[quantity]!r}. No automatic unit conversion is performed."
        )
    return timestamps[0], value_index, stated_unit


def read_weather(path, quantity):
    check_path(path)
    values, source_rows = {}, {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            headers = next(reader, [])
            time_index, value_index, stated_unit = weather_header_indices(headers, quantity, path)
            for number, fields in enumerate(reader, 1):
                if len(fields) > len(headers):
                    raise WeatherJoinError(f"{path}: data row {number}: unexpected extra CSV fields.")
                raw_time = fields[time_index] if time_index < len(fields) else ""
                timestamp = parse_utc(raw_time, path, number, headers[time_index])
                if timestamp in values:
                    raise WeatherJoinError(
                        f"{path}: duplicate weather timestamp {format_utc(timestamp)} "
                        f"at data rows {source_rows[timestamp]} and {number}. "
                        "Stopped; weather rows are not aggregated or deduplicated."
                    )
                values[timestamp] = fields[value_index] if value_index < len(fields) else ""
                source_rows[timestamp] = number
    except (OSError, UnicodeError, csv.Error) as error:
        raise WeatherJoinError(f"Cannot read required weather file {path}: {error}") from error
    return WeatherSeries(path, headers, stated_unit, values)


def read_consumption(path):
    check_path(path)
    rows = []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            headers = next(reader, [])
            if len(headers) != 4 or set(headers) != set(CONSUMPTION_COLUMNS):
                raise WeatherJoinError(
                    f"{path}: unexpected consumption columns {headers!r}; "
                    f"expected exactly {CONSUMPTION_COLUMNS!r}."
                )
            indices = [headers.index(name) for name in CONSUMPTION_COLUMNS]
            for number, fields in enumerate(reader, 1):
                if len(fields) > len(headers):
                    raise WeatherJoinError(f"{path}: data row {number}: unexpected extra CSV fields.")
                columns = [fields[index] if index < len(fields) else "" for index in indices]
                start = parse_utc(columns[1], path, number, "interval_start_utc", allow_missing=True)
                end = parse_utc(columns[2], path, number, "interval_end_utc", allow_missing=True)
                columns[1], columns[2] = format_utc(start), format_utc(end)
                rows.append(ConsumptionRow(start, columns))
    except (OSError, UnicodeError, csv.Error) as error:
        raise WeatherJoinError(f"Cannot read required consumption file {path}: {error}") from error
    latest = datetime.max.replace(tzinfo=timezone.utc)
    rows.sort(key=lambda row: (row.prediction_time is None, row.prediction_time or latest))
    return rows


def prepare_inputs(root):
    """Read/validate all 25 input files before touching any generated output."""
    root = Path(root).expanduser().absolute()
    check_path(root)
    weather, buildings, errors = {}, [], []
    for location in dict.fromkeys(building.split("_")[0] for building in BUILDINGS):
        weather[location] = {}
        for quantity, column in WEATHER_COLUMNS.items():
            path = root / location / f"{location}_WS" / f"adrenalin.1h.{location}.WS01.{quantity}.csv"
            try:
                weather[location][column] = read_weather(path, quantity)
            except (WeatherJoinError, OSError) as error:
                errors.append(str(error))
    for building in BUILDINGS:
        location = building.split("_")[0]
        directory = root / location / "unifieddataconsumption"
        source = directory / f"{building}_consumption.csv"
        destination = directory / f"{building}_consumption_weather.csv"
        try:
            rows = read_consumption(source)
            check_path(destination)
            if destination.exists() and not destination.is_file():
                raise WeatherJoinError(f"Output path is not a file: {destination}")
            buildings.append(BuildingInput(building, source, destination, rows))
        except (WeatherJoinError, OSError) as error:
            errors.append(str(error))
    if errors:
        raise WeatherJoinError("Validation failed; no outputs were written:\n" + "\n".join(errors))
    return buildings, weather


def joined_rows(rows, location_weather):
    """Yield precisely one output per left-hand row using exact dict lookups."""
    for row in rows:
        appended = [
            location_weather[column].values.get(row.prediction_time, "")
            if row.prediction_time is not None else ""
            for column in WEATHER_COLUMNS.values()
        ]
        yield row.columns + appended


def write_outputs(buildings, weather):
    staged, temporary_paths = [], []
    try:
        for building in buildings:
            missing = Counter({column: 0 for column in WEATHER_COLUMNS.values()})
            output_count = 0
            location_weather = weather[building.building.split("_")[0]]
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=building.destination.parent,
                prefix=f".{building.building}_weather_", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                temporary_paths.append(temporary)
                writer = csv.writer(handle)
                writer.writerow(OUTPUT_COLUMNS)
                for joined in joined_rows(building.rows, location_weather):
                    writer.writerow(joined)
                    output_count += 1
                    for column, value in zip(WEATHER_COLUMNS.values(), joined[4:]):
                        missing[column] += value.strip().casefold() in MISSING_TOKENS
            if output_count != len(building.rows):
                raise WeatherJoinError(f"{building.building}: input/output row counts differ; no outputs replaced.")
            staged.append((temporary, building, output_count, missing))
        for temporary, building, output_count, missing in staged:
            os.replace(temporary, building.destination)
            print(f"[{building.building}] input_rows={len(building.rows)}, output_rows={output_count}")
            for column in WEATHER_COLUMNS.values():
                print(f"  Missing {column}: {missing[column]}")
            print(f"  Output: {building.destination}")
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT,
        help="data root (default: project Data/BuildingsByLocation, independent of working directory)",
    )
    args = parser.parse_args(argv)
    try:
        buildings, weather = prepare_inputs(args.root)
        print("MODELLING ASSUMPTION: " + MODELLING_ASSUMPTION)
        for location, series in weather.items():
            for column, data in series.items():
                print(
                    f"Weather [{location}/{column}]: unit={data.stated_unit!r}; "
                    f"headers={json.dumps(data.headers, ensure_ascii=False)}; file={data.path}"
                )
        write_outputs(buildings, weather)
    except (WeatherJoinError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
