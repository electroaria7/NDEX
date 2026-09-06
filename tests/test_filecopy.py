from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ndex_common.filecopy import copy_verified


class VerifiedCopyTests(unittest.TestCase):
    def test_failed_or_corrupt_copy_preserves_destination(self):
        for failure in ("disk_full", "same_size_corruption", "truncated"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, destination = root / "source", root / "destination"
                source.write_bytes(b"new data")
                destination.write_bytes(b"original")

                def damaged_copy(src, tmp):
                    Path(tmp).write_bytes(b"bad data" if failure == "same_size_corruption" else b"bad")
                    if failure == "disk_full":
                        raise OSError("disk full")

                with patch("ndex_common.filecopy.shutil.copy2", side_effect=damaged_copy):
                    with self.assertRaises(OSError):
                        copy_verified(source, destination, overwrite=True)
                self.assertEqual(destination.read_bytes(), b"original")
                self.assertEqual(source.read_bytes(), b"new data")
                self.assertEqual(set(root.iterdir()), {source, destination})

    def test_destination_created_during_copy_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "source", root / "destination"
            source.write_bytes(b"new data")
            real_copy = shutil.copy2

            def competing_copy(src, tmp):
                real_copy(src, tmp)
                destination.write_bytes(b"other writer")

            with patch("ndex_common.filecopy.shutil.copy2", side_effect=competing_copy):
                with self.assertRaises(FileExistsError):
                    copy_verified(source, destination)
            self.assertEqual(destination.read_bytes(), b"other writer")
            self.assertEqual(set(root.iterdir()), {source, destination})

    def test_verified_overwrite_and_same_file_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "source", root / "destination"
            source.write_bytes(b"new data")
            destination.write_bytes(b"old data")
            copy_verified(source, destination, overwrite=True)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            with self.assertRaises(shutil.SameFileError):
                copy_verified(source, source, overwrite=True)
            self.assertEqual(set(root.iterdir()), {source, destination})
