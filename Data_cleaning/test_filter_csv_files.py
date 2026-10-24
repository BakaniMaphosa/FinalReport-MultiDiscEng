"""Verify deletion boundaries using temporary files only."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import filter_csv_files as cleaner


class FilterCsvFilesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "datasets"
        self.root.mkdir()

    def write(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"unchanged contents; intentionally not parsed\n")
        return path

    def run_filter(self, root=None):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            summaries, count = cleaner.filter_csv_files(root or self.root)
        return summaries, count, output.getvalue(), errors.getvalue()

    def test_cli_all_buildings_and_exact_channels(self):
        retained, deleted = [], []
        # Independent expectations from the requested building/channel policy.
        expected_channels = {
            "L03_B01": {"EM02.Pt"},
            "L06_B01": {"EM01.Pt", "EM01.ePt", "EM02.Pt"},
            "L07_B01": {"EM01.Pt"},
            "L14_B01": {"EM01.Pt"},
            "L14_B02": {"EM01.Pt"},
            "L14_B03": {"EM02.Pt"},
            "L14_B04": {"EM02.Pt"},
            "L14_B05": {"EM02.Pt"},
        }
        for building, channels in expected_channels.items():
            location, building_id = building.split("_")
            folder = f"BuildingsByLocation/{location}/{building}/records/1h/nested"
            prefix = f"adrenalin.1h.{location}.{building_id}"
            for channel in channels:
                retained.append(self.write(f"{folder}/{prefix}.{channel}.csv"))
            for channel in ("EM01.P", "EM01.P1", "EM01.ePt", "EM02.Pt", "ES01.Pt", "EMO1.Pt"):
                if channel not in channels:
                    deleted.append(self.write(f"{folder}/{prefix}.{channel}.csv"))
            # The filename's building must match the directory's building.
            deleted.append(self.write(f"{folder}/adrenalin.1h.L99.B99.EM01.Pt.csv"))
            deleted.append(self.write(f"{folder}/EM01.Pt.csv"))
            retained.append(self.write(f"{folder}/README.md"))
            retained.append(self.write(f"{folder}/notes.csv.txt"))
            retained.append(self.write(f"{folder}/notes.txt"))
            retained.append(self.write(f"BuildingsByLocation/{location}/{building}/outside.csv"))
            retained.append(self.write(f"BuildingsByLocation/{location}/{building}/15m/unwanted.csv"))
            retained.append(self.write(f"BuildingsByLocation/{location}/{building}/{building}-topology.txt"))
        retained.append(self.write("BuildingsByLocation/L03/L03_B02/1h/unwanted.csv"))
        retained.append(self.write("BuildingsByLocation/L99/L99_B01/1h/unwanted.csv"))
        retained.append(self.write("BuildingsByLocation/L030/L03_B01/1h/unwanted.csv"))
        before = {path: path.read_bytes() for path in retained}

        result = subprocess.run(
            [sys.executable, str(Path(cleaner.__file__).resolve()), "--root", str(self.root)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        for path, original in before.items():
            self.assertEqual(path.read_bytes(), original)
        for path in deleted:
            self.assertFalse(path.exists(), str(path))
            self.assertTrue(path.parent.is_dir())
            self.assertIn(str(path), result.stdout)
        self.assertEqual(result.stdout.count("RETAINED ["), 10)
        self.assertEqual(result.stdout.count("DELETED  ["), len(deleted))
        for building in expected_channels:
            self.assertIn(f"SUMMARY [{building}]", result.stdout)

    def test_complete_components_and_case_insensitive_matching(self):
        for channel, expected in (
            ("EM01.Pt", True), ("em01.pT", True), ("EM01.ePt", True),
            ("EM02.Pt", True), ("EM02.ePt", False), ("EM01.P", False),
            ("EM01.P1", False), ("EM01.Ptt", False), ("EMO1.Pt", False),
            ("EM010.Pt", False), ("XEM01.Pt", False),
        ):
            with self.subTest(channel=channel):
                self.assertEqual(
                    cleaner.matches_channel(f"ADRENALIN.1H.l06.b01.{channel}.CSV", "L06_B01"),
                    expected,
                )
        self.assertFalse(cleaner.matches_channel("adrenalin.1h.L03.B01.EM02.ePt.csv", "L03_B01"))
        self.assertFalse(cleaner.matches_channel("adrenalin.1h.L06.B010.EM01.Pt.csv", "L06_B01"))
        self.assertFalse(cleaner.matches_channel("adrenalin.15m.L06.B01.EM01.Pt.csv", "L06_B01"))

    def test_weather_and_symbolic_links_are_not_traversed_or_deleted(self):
        weather = self.write("L03/L03_WS/nested/L03_B01/1h/unwanted.csv")
        weather_lower = self.write("L06/l06_ws/L06_B01/1h/unwanted.csv")
        unlisted = self.write("L03/L03_B02/1h/unwanted.csv")
        external = self.base / "outside"
        external.mkdir()
        target = external / "valuable.csv"
        target.write_text("keep\n")
        hourly = self.root / "L03/L03_B01/1h"
        hourly.mkdir(parents=True)
        file_link = hourly / "unwanted.csv"
        file_link.symlink_to(target)
        broken_link = hourly / "broken.csv"
        broken_link.symlink_to(external / "missing.csv")
        directory_link = hourly / "linked_directory"
        directory_link.symlink_to(external, target_is_directory=True)
        building_link = self.root / "L14_B01"
        building_link.symlink_to(external, target_is_directory=True)
        scanned = []
        original_scandir = cleaner.os.scandir

        def record_scan(path):
            scanned.append(Path(path))
            return original_scandir(path)

        with patch.object(cleaner.os, "scandir", side_effect=record_scan):
            _, count, output, errors = self.run_filter()
        self.assertEqual(count, 0, errors)
        self.assertNotIn("DELETED", output)
        for path in (weather, weather_lower, unlisted, target):
            self.assertTrue(path.exists())
        for path in (file_link, broken_link, directory_link, building_link):
            self.assertTrue(path.is_symlink())
        self.assertFalse(any(path.name.lower().endswith("_ws") for path in scanned))
        self.assertNotIn(unlisted.parent.parent, scanned)
        self.assertNotIn(external, scanned)

    def test_root_links_missing_paths_and_default_argument(self):
        link = self.base / "linked_root"
        link.symlink_to(self.root, target_is_directory=True)
        for path in (link, link / "nested"):
            with self.subTest(path=path):
                _, count, _, errors = self.run_filter(path)
                self.assertEqual(count, 1)
                self.assertIn("symbolic-link root path", errors)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cleaner.main(["--root", str(self.root / "missing")]), 1)
            with patch.object(cleaner, "filter_csv_files", return_value=({}, 0)) as run:
                self.assertEqual(cleaner.main([]), 0)
                run.assert_called_once_with(Path("./datasets"))

    def test_access_and_deletion_errors_are_reported(self):
        undeletable = self.write("L03/L03_B01/1h/unwanted.csv")
        unreadable = self.root / "L14/L14_B01"
        unreadable.mkdir(parents=True)
        original_unlink = Path.unlink
        original_scandir = cleaner.os.scandir

        def reject_unlink(path, *args, **kwargs):
            if path == undeletable:
                raise PermissionError("deletion denied for test")
            return original_unlink(path, *args, **kwargs)

        def reject_scan(path):
            if Path(path) == unreadable:
                raise PermissionError("directory access denied for test")
            return original_scandir(path)

        with patch.object(Path, "unlink", reject_unlink), patch.object(
            cleaner.os, "scandir", side_effect=reject_scan
        ):
            summaries, count, output, errors = self.run_filter()
        self.assertEqual(count, 2)
        self.assertEqual(summaries["L03_B01"].errors, 1)
        self.assertEqual(summaries["L14_B01"].errors, 1)
        self.assertIn("cannot delete file", errors)
        self.assertIn("cannot read directory", errors)
        self.assertNotIn("DELETED", output)
        self.assertTrue(undeletable.exists())

    def test_direct_building_root_and_repeat_runs(self):
        keep = self.write("l06/l06_b01/deep/1H/adrenalin.1h.l06.b01.em01.ept.CSV")
        remove = self.write("l06/l06_b01/deep/1H/adrenalin.1h.l06.b01.em02.ept.csv")
        summaries, count, _, errors = self.run_filter(keep.parents[2])
        self.assertEqual(count, 0, errors)
        self.assertEqual(summaries["L06_B01"].retained, 1)
        self.assertEqual(summaries["L06_B01"].deleted, 1)
        self.assertTrue(keep.exists())
        self.assertFalse(remove.exists())
        summaries, count, _, errors = self.run_filter(keep.parent)
        self.assertEqual(count, 0, errors)
        self.assertEqual(summaries["L06_B01"].deleted, 0)


if __name__ == "__main__":
    unittest.main()
