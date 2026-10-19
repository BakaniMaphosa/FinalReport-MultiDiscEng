"""Clean CSV/TSV files in a directory using only Python 3.9+ standard libraries.

Run: python3 Dataset_Cleaner.py
Subdirectories and filenames are preserved in the destination. Missing cells
become N/A, exact duplicate rows are removed, and recognised date/time columns
are sorted chronologically. Temporary SQLite storage keeps large files out of
memory. Existing destination CSVs are replaced only after successful cleaning.
Short rows are padded with N/A; values beyond the header receive generated
extra_column_N names and are reported for review.

Explicit UTC offsets are converted to UTC. A timezone/time_zone/tz column can
provide an IANA timezone for a row's local timestamps. Without that information,
local times are preserved and reported; the computer's timezone is never assumed.
Timezone information in separate metadata files is validated but is not assumed
to describe the source clock of other files.
"""

import csv
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import zlib
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MISSING_VALUES = {"", "n/a", "na", "nan", "null", "none", "nat", "<na>"}
TIMEZONE_NAMES = {"timezone", "time_zone", "tz"}
DATE_NAME = re.compile(r"(^|_)(date|datetime|timestamp|time)($|_)|_at$")


def normalise_name(name):
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", name.strip())
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def is_missing(value):
    return value.strip().lower() in MISSING_VALUES


def csv_rows(path):
    """Read regular delimited files and the whole-row-quoted BDGP2 files."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(65536)
        handle.seek(0)
        if not sample.strip():
            raise ValueError("file is empty")
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            # A short sample may contain no escaped quotes even when later rows do.
            dialect.doublequote = True
        except csv.Error:
            dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
        reader = csv.reader(handle, dialect, strict=True)
        header = next(reader)
        wrapped = False
        inner_dialect = csv.excel
        if len(header) == 1:
            # Check several rows: a legitimate one-column CSV may contain commas.
            try:
                inner_dialect = csv.Sniffer().sniff(header[0], delimiters=",;\t|")
                inner_dialect.doublequote = True
                inner_header = next(csv.reader(header, inner_dialect, strict=True))
                preview = []
                for _ in range(3):
                    row = next(reader, None)
                    if row is None:
                        break
                    preview.append(row)
                wrapped = len(inner_header) > 1 and bool(preview) and all(
                    len(row) == 1
                    and len(next(csv.reader(row, inner_dialect, strict=True))) > 1
                    for row in preview
                )
            except csv.Error:
                wrapped = False
            handle.seek(0)
            reader = csv.reader(handle, dialect, strict=True)
            header = next(reader)
            if wrapped:
                header = inner_header
        if not header or any(not cell.strip() for cell in header):
            raise ValueError("header contains an empty column name")
        if len(header) != len(set(header)):
            raise ValueError("header contains duplicate column names")
        yield header
        for row in reader:
            if not row:  # Ignore physically empty lines, not empty cells.
                continue
            if wrapped:
                if len(row) != 1:
                    raise ValueError(f"inconsistent whole-row quoting near line {reader.line_num}")
                row = next(csv.reader(row, inner_dialect, strict=True))
            yield row


@lru_cache(maxsize=32768)
def parse_datetime(value):
    """Parse ISO, common unambiguous dates, and Unix s/ms/us/ns timestamps."""
    value = value.strip()
    if re.fullmatch(r"-?\d{10}|-?\d{13}|-?\d{16}|-?\d{19}", value):
        digits = len(value.lstrip("-"))
        divisor = {10: 1, 13: 1000, 16: 1000000, 19: 1000000000}[digits]
        number = int(value)
        seconds, fraction = divmod(number, divisor)
        try:
            return datetime.fromtimestamp(seconds, timezone.utc).replace(
                microsecond=fraction * 1000000 // divisor
            )
        except (ValueError, OverflowError, OSError):
            return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        pass
    # Only interpret slash dates when day/month order is unambiguous.
    slash = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})(.*)$", value)
    formats = ["%Y/%m/%d", "%Y/%m/%d %H:%M:%S", "%Y%m%d",
               "%d-%b-%Y", "%d %b %Y", "%d %B %Y"]
    if slash:
        first, second = int(slash[1]), int(slash[2])
        if first > 12 or first == second:
            base = "%d/%m/%Y"
        elif second > 12:
            base = "%m/%d/%Y"
        else:
            return None
        formats = [base, base + " %H:%M", base + " %H:%M:%S"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


@lru_cache(maxsize=256)
def get_zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def localise(value, zone):
    """Reject nonexistent/ambiguous daylight-saving times instead of guessing."""
    possibilities = {}
    for fold in (0, 1):
        candidate = value.replace(tzinfo=zone, fold=fold)
        utc = candidate.astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == value:
            possibilities[utc] = candidate
    if len(possibilities) == 1:
        return next(iter(possibilities.values())), None
    issue = "ambiguous daylight-saving timestamps" if possibilities else "nonexistent daylight-saving timestamps"
    return value, issue


def clean_timestamp(value, zone, issues):
    if is_missing(value):
        return "N/A", "3:"
    parsed = parse_datetime(value)
    if parsed is None:
        issues["invalid or unsupported dates preserved (including ambiguous day/month order)"] += 1
        return value, "2:" + value
    if parsed.tzinfo is None and zone is not None:
        parsed, issue = localise(parsed, zone)
        if issue:
            issues[issue + " preserved as local time"] += 1
    elif parsed.tzinfo is not None and zone is not None:
        if parsed.utcoffset() != parsed.astimezone(zone).utcoffset():
            issues["timestamp offsets disagree with timezone column; explicit offset retained"] += 1
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
        prefix = "0:"
    else:
        issues["timestamps without a resolved UTC offset; local time preserved"] += 1
        prefix = "1:"
    # Fixed-width keys sort fractions correctly; output is readable ISO 8601.
    key = prefix + parsed.strftime("%Y-%m-%d %H:%M:%S.%f")
    return parsed.isoformat(sep=" "), key


def clean_file(source, destination):
    issues = Counter()
    rows = csv_rows(source)
    header = next(rows)
    # Determine the complete width before writing a header. Some exports truncate
    # header lines; keep extra values under generated names instead of losing them.
    widths = Counter(len(row) for row in rows)
    original_width = len(header)
    width = max([original_width, *widths])
    for number in range(1, width - original_width + 1):
        name = f"extra_column_{number}"
        while name in header:
            name = "_" + name
        header.append(name)
    if width > original_width:
        issues[f"missing column names generated as extra_column_1 through extra_column_{width - original_width}"] = width - original_width
    short_rows = sum(count for length, count in widths.items() if length < width)
    if short_rows:
        issues["short rows padded with missing cells"] = short_rows
    rows = csv_rows(source)
    next(rows)
    names = [normalise_name(name) for name in header]
    date_columns = [i for i, name in enumerate(names) if DATE_NAME.search(name)]
    zone_columns = [i for i, name in enumerate(names) if name in TIMEZONE_NAMES]
    total = duplicates = missing = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dataset_cleaner_") as scratch:
        with closing(sqlite3.connect(str(Path(scratch) / "rows.sqlite"))) as db:
            # This database is disposable; avoid journaling copies of large rows.
            db.execute("PRAGMA journal_mode = OFF")
            db.execute("PRAGMA synchronous = OFF")
            db.execute("PRAGMA cache_size = -32768")  # Bound the cache to 32 MiB.
            db.execute("PRAGMA temp_store = FILE")
            sort_schema = "".join(f", sort_{i} TEXT" for i in range(len(date_columns)))
            db.execute(f"CREATE TABLE cleaned (digest BLOB, original BLOB, payload BLOB{sort_schema})")
            db.execute("CREATE INDEX duplicate_lookup ON cleaned (digest)")
            placeholders = ",".join("?" for _ in range(3 + len(date_columns)))
            statement = f"INSERT INTO cleaned VALUES ({placeholders})"
            for row in rows:
                total += 1
                # Compress losslessly so exact deduplication also works on wide tables.
                original = zlib.compress(
                    json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                    level=1,
                )
                digest = hashlib.sha256(original).digest()
                # Check actual row bytes too, so hash collisions never discard data.
                candidates = db.execute("SELECT original FROM cleaned WHERE digest = ?", (digest,))
                if any(stored == original for (stored,) in candidates):
                    duplicates += 1
                    continue
                row = row + [""] * (width - len(row))
                zone_names = {row[i].strip() for i in zone_columns if not is_missing(row[i])}
                zone = None
                row_issues = Counter()
                if len(zone_names) > 1:
                    row_issues["rows with conflicting timezone columns"] += 1
                elif zone_names:
                    zone_name = next(iter(zone_names))
                    zone = get_zone(zone_name)
                    if zone is None:
                        row_issues[f"rows with invalid/unknown timezone '{zone_name}'"] += 1
                row_missing = sum(is_missing(value) for value in row)
                cleaned = ["N/A" if is_missing(value) else value for value in row]
                keys = []
                for index in date_columns:
                    cleaned[index], key = clean_timestamp(cleaned[index], zone, row_issues)
                    keys.append(key)
                payload = zlib.compress(
                    json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                    level=1,
                )
                db.execute(statement, [digest, original, payload, *keys])
                missing += row_missing
                issues.update(row_issues)
            if date_columns:
                sort_columns = ", ".join(f"sort_{i}" for i in range(len(date_columns)))
                # Sort the small index, avoiding temporary copies of entire rows.
                db.execute(f"CREATE INDEX chronological ON cleaned ({sort_columns})")
            db.commit()
            order = ", ".join([f"sort_{i}" for i in range(len(date_columns))] + ["rowid"])
            temporary_output = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", newline="", dir=destination.parent,
                    prefix=".cleaning_", suffix=".tmp", delete=False,
                ) as output:
                    temporary_output = Path(output.name)
                    writer = csv.writer(output, delimiter="\t" if destination.suffix.lower() == ".tsv" else ",")
                    writer.writerow(header)
                    for (payload,) in db.execute(f"SELECT payload FROM cleaned ORDER BY {order}"):
                        writer.writerow(json.loads(zlib.decompress(payload)))
                temporary_output.replace(destination)
            finally:
                if temporary_output is not None:
                    temporary_output.unlink(missing_ok=True)
    print(f"  Saved {total - duplicates:,} rows; removed {duplicates:,} exact duplicates; filled {missing:,} missing cells.")
    if date_columns:
        print("  Sorted by: " + ", ".join(header[i] for i in date_columns))
    else:
        print("  No date/time columns recognised; original row order preserved.")
    if zone_columns:
        print("  Checked timezone columns: " + ", ".join(header[i] for i in zone_columns))
    for issue, count in issues.items():
        print(f"  Check: {count:,} {issue}.")
    if date_columns and issues:
        print("  Sort order: UTC timestamps, unresolved local timestamps, invalid values, then N/A.")


def input_directory(prompt):
    value = input(prompt).strip().strip("\"'")
    if not value:
        raise ValueError("directory cannot be empty")
    return Path(value).expanduser().resolve()


def main():
    raw_directory = input_directory("WHAT IS THE RAW DATA DIRECTORY? :")
    cleaned_directory = input_directory("WHERE DO YOU WANT THE CLEANED DATA TO GO(DIRECTORY)? :")
    if not raw_directory.is_dir():
        raise ValueError(f"raw directory does not exist: {raw_directory}")
    if raw_directory == cleaned_directory:
        raise ValueError("choose a separate output directory to preserve the raw files")
    files = sorted(
        path for path in raw_directory.rglob("*")
        if path.is_file() and path.suffix.lower() in {".csv", ".tsv"}
        and cleaned_directory not in path.resolve().parents
    )
    if not files:
        raise ValueError("no CSV or TSV files found in the raw directory")
    # Prevent output collisions with raw files, including symlinked destinations.
    sources = {path.resolve() for path in files}
    destinations = [cleaned_directory / path.relative_to(raw_directory) for path in files]
    if any(path.resolve() in sources for path in destinations):
        raise ValueError("an output path would overwrite a raw file; choose a different directory")
    failures = 0
    print(f"\nFound {len(files)} CSV/TSV file(s). Raw files will be preserved.")
    for source, destination in zip(files, destinations):
        print(f"\nCleaning {source.relative_to(raw_directory)} ...", flush=True)
        try:
            clean_file(source, destination)
        except (OSError, ValueError, csv.Error, sqlite3.Error) as error:
            failures += 1
            print(f"  Failed: {error}", file=sys.stderr)
    print(f"\nFinished: {len(files) - failures} cleaned, {failures} failed. Output: {cleaned_directory}")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    except (EOFError, KeyboardInterrupt):
        print("\nCleaning cancelled.", file=sys.stderr)
        sys.exit(130)
