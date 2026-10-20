#librarys required to perform deletions
import os
from pathlib import Path
import re


def delete_non_em_es_files(datasets_folder=None):
    """Delete CSVs unless their sensor is ES or EM followed by digits.

    Read the sensor from the second-to-last dot-separated part before .csv.
    For example, keep ES01.P2.csv and EM123.I3.csv, but delete HS01.iTo.csv.
    Sensor matching is case-insensitive; the measurement part is unrestricted.

    Always preserve folders ending in _WS and everything beneath them,
    including when called directly on a weather folder or its descendants.
    Non-CSV files are also preserved.

    Default to this project's Datasets folder, independently of the current
    working directory. Return a list of deleted file paths.
    """
    if datasets_folder is None:
        datasets_folder = Path(__file__).resolve().parent.parent / "Datasets"

    datasets_folder = Path(datasets_folder).resolve()
    if not datasets_folder.is_dir():
        raise NotADirectoryError(f"Dataset folder does not exist: {datasets_folder}")

    if any(part.lower().endswith("_ws") for part in datasets_folder.parts):
        return []

    deleted_files = []
    for current_folder, subfolders, filenames in os.walk(datasets_folder):
        # Do not enter weather folders, including any nested directories.
        subfolders[:] = [
            name for name in subfolders if not name.lower().endswith("_ws")
        ]

        for filename in filenames:
            csv_file = Path(current_folder) / filename
            if not csv_file.is_file() or csv_file.suffix.lower() != ".csv":
                continue

            parts = csv_file.stem.rsplit(".", 1)
            sensor = parts[0].rsplit(".", 1)[-1] if len(parts) == 2 else ""
            if re.fullmatch(r"(?:ES|EM)[0-9]+", sensor, flags=re.IGNORECASE):
                continue

            csv_file.unlink()
            deleted_files.append(csv_file)

    return deleted_files


def delete_non_p_files(datasets_folder=None):
    """Delete CSVs whose final filename part before .csv does not start with P.

    Keep measurements such as P, Pt, P1, and P2, ignoring case. This function
    does not filter sensor names. Always preserve folders ending in _WS and
    everything beneath them, as well as all non-CSV files.

    Default to the project's Datasets folder. Return the deleted file paths.
    Files are deleted immediately when this function is called.
    """
    if datasets_folder is None:
        datasets_folder = Path(__file__).resolve().parent.parent / "Datasets"

    datasets_folder = Path(datasets_folder).resolve()
    if not datasets_folder.is_dir():
        raise NotADirectoryError(f"Dataset folder does not exist: {datasets_folder}")

    if any(part.lower().endswith("_ws") for part in datasets_folder.parts):
        return []

    deleted_files = []
    for current_folder, subfolders, filenames in os.walk(datasets_folder):
        # Skip weather folders and all their descendants.
        subfolders[:] = [
            name for name in subfolders if not name.lower().endswith("_ws")
        ]

        for filename in filenames:
            csv_file = Path(current_folder) / filename
            if not csv_file.is_file() or csv_file.suffix.lower() != ".csv":
                continue

            measurement = csv_file.stem.rsplit(".", 1)[-1]
            if measurement.lower().startswith("p"):
                continue

            csv_file.unlink()
            deleted_files.append(csv_file)

    return deleted_files

delete_non_p_files()
# No automatic deletion: call either function explicitly to run it.
