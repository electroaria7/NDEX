from datetime import datetime
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from dsb_image_manager.dsb_image_manager.core.models import ImageRecord, ExportOptions
from dsb_image_manager.dsb_image_manager.services.backup import BackupService
from dsb_image_manager.dsb_image_manager.services.exporter import ExportService
from dsb_image_manager.dsb_image_manager.ui.tk_app import ImageManagerApp


def record(path, identifier):
    return ImageRecord(identifier, path, ".jpg", path.stem, "jpg", path.stem, "jpg_only",
                       None, None, None, None, datetime(2026, 9, 6))


class CopySafetyTests(unittest.TestCase):
    def test_mixed_backup_only_marks_success_and_records_failed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good, missing = record(root / "good.jpg", 1), record(root / "missing.jpg", 2)
            good.file_path.write_bytes(b"photo")
            catalog = Mock()
            catalog.list_images.return_value = [good, missing]
            app = SimpleNamespace(catalog=catalog, source_dir=root, refresh_records=Mock())
            with patch("dsb_image_manager.dsb_image_manager.ui.tk_app.filedialog.askdirectory",
                       return_value=str(root / "backup")), \
                 patch("dsb_image_manager.dsb_image_manager.ui.tk_app.messagebox.showinfo"), \
                 patch("ndex_common.workflow.record_job") as recorded:
                ImageManagerApp.backup_picked(app)
            catalog.update_backup_status.assert_called_once_with(1, "backed_up")
            self.assertEqual(recorded.call_args.kwargs["counts"]["failed"], 1)
            failed = [item for item in recorded.call_args.kwargs["items"] if item["status"] == "failed"]
            self.assertEqual(failed[0]["path"], str(missing.file_path))

    def test_manager_overwrite_failures_leave_previous_content(self):
        for operation in ("backup", "export"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                photo = record(root / "photo.jpg", 1)
                photo.file_path.write_bytes(b"new photo")
                destination = root / "out"
                target = (BackupService.destination_dir(destination, photo) / photo.file_path.name
                          if operation == "backup" else destination / photo.file_path.name)
                target.parent.mkdir(parents=True)
                target.write_bytes(b"previous photo")
                with patch("ndex_common.filecopy.shutil.copy2", side_effect=OSError("disk full")):
                    if operation == "backup":
                        result = BackupService().backup([photo], destination, "overwrite")
                    else:
                        result = ExportService().export([photo], ExportOptions(destination, "{name}", 1, "overwrite"))
                self.assertEqual((result.errors, result.overwritten), (1, 0))
                self.assertEqual(target.read_bytes(), b"previous photo")
                self.assertFalse(list(destination.rglob("*.ndex_tmp")))
