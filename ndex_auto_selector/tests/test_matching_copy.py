from __future__ import annotations

import queue
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ndex_auto_selector.ndex_auto_selector.services.selector import AutoSelectorService


def _folders(root: Path):
    raw, jpg, work = root / "raw", root / "jpg", root / "work"
    for folder in (raw, jpg, work):
        folder.mkdir()
    return raw, jpg, work


class ExactStemTests(unittest.TestCase):
    def test_exact_stem_beats_suffixed_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = _folders(Path(tmp))
            (raw / "IMG_1234.CR3").write_bytes(b"a")
            (raw / "IMG_1234-2.CR3").write_bytes(b"b")
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            match = AutoSelectorService().analyze(raw, jpg).matches[0]
        self.assertEqual((match.status, match.raw_path.name), ("matched", "IMG_1234.CR3"))

    def test_appledouble_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = _folders(Path(tmp))
            (raw / "IMG_1234.CR3").write_bytes(b"a")
            (raw / "._IMG_1234.CR3").write_bytes(b"junk")
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            (jpg / "._IMG_1234.jpg").write_bytes(b"junk")
            summary = AutoSelectorService().analyze(raw, jpg)
        self.assertEqual(summary.selected_count, 1)
        self.assertEqual(summary.matches[0].status, "matched")

    def test_same_exact_name_in_two_folders_stays_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = _folders(Path(tmp))
            for sub in ("a", "b"):
                (raw / sub).mkdir()
                (raw / sub / "IMG_1234.CR3").write_bytes(sub.encode())
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            self.assertEqual(AutoSelectorService().analyze(raw, jpg).matches[0].status, "ambiguous")

    def test_camera_id_fallback_still_works_without_exact_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = _folders(Path(tmp))
            (raw / "IMG_1234.CR3").write_bytes(b"a")
            (jpg / "IMG_1234_edit.jpg").write_bytes(b"j")
            match = AutoSelectorService().analyze(raw, jpg).matches[0]
        self.assertEqual((match.status, match.raw_path.name), ("matched", "IMG_1234.CR3"))


class IdBoundaryTests(unittest.TestCase):
    def _status(self, raw_name: str, jpg_name: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = _folders(Path(tmp))
            (raw / raw_name).write_bytes(b"a")
            (jpg / jpg_name).write_bytes(b"j")
            return AutoSelectorService().analyze(raw, jpg).matches[0].status

    def test_longer_numbers_do_not_match(self):
        self.assertEqual(self._status("IMG_12345.CR3", "IMG_1234.jpg"), "missing")
        self.assertEqual(self._status("_DSC01234.NEF", "_DSC0123.jpg"), "missing")

    def test_prefixed_raw_does_not_match(self):
        self.assertEqual(self._status("Trip_IMG_1234.CR3", "IMG_1234.jpg"), "missing")
        self.assertEqual(self._status("XIMG_1234.CR3", "IMG_1234_edit.jpg"), "missing")

    def test_nikon_variants_match(self):
        self.assertEqual(self._status("_DSC0001.NEF", "_DSC0001_edit.jpg"), "matched")
        self.assertEqual(self._status("DSC_0001.NEF", "DSC_0001_edit.jpg"), "matched")
        self.assertEqual(self._status("DSC00001.ARW", "pick_DSC00001.jpg"), "matched")


class CopyRunTests(unittest.TestCase):
    def test_two_jpgs_for_one_raw_copy_it_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = _folders(Path(tmp))
            (raw / "IMG_1234.CR3").write_bytes(b"raw")
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            (jpg / "IMG_1234_b.jpg").write_bytes(b"j")
            service = AutoSelectorService()
            result = service.copy_matches(service.analyze(raw, jpg).matches, work, "rename")
            names = sorted(p.name for p in work.glob("*.CR3"))
        self.assertEqual(names, ["IMG_1234.CR3"])
        self.assertEqual((result.copied, result.skipped, result.errors), (1, 1, 0))
        self.assertIn("already copied in this run", [i.get("detail") for i in result.items])

    def test_failed_copy_does_not_mark_raw_as_copied_for_the_next_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = _folders(Path(tmp))
            (raw / "IMG_1234.CR3").write_bytes(b"raw")
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            (jpg / "IMG_1234_b.jpg").write_bytes(b"j")
            service = AutoSelectorService()
            matches = service.analyze(raw, jpg).matches
            module = "ndex_auto_selector.ndex_auto_selector.services.selector"
            real_copy = __import__(module, fromlist=["copy_verified"]).copy_verified
            calls = []

            def flaky_copy(*args, **kwargs):
                calls.append(args)
                if len(calls) == 1:
                    raise OSError("disk hiccup")
                return real_copy(*args, **kwargs)

            with patch(f"{module}.copy_verified", side_effect=flaky_copy):
                result = service.copy_matches(matches, work, "rename")
            names = sorted(p.name for p in work.glob("*.CR3"))
        self.assertEqual(names, ["IMG_1234.CR3"])
        self.assertEqual((result.copied, result.errors), (1, 1))

    def test_rerun_skips_identical_copy_and_writes_missing_xmp_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = _folders(Path(tmp))
            (raw / "IMG_1234.CR3").write_bytes(b"raw")
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            service = AutoSelectorService()
            matches = service.analyze(raw, jpg).matches
            service.copy_matches(matches, work, "rename")
            again = service.copy_matches(matches, work, "rename", write_xmp=True)
            self.assertEqual(sorted(p.name for p in work.glob("*.CR3")), ["IMG_1234.CR3"])
            self.assertEqual((again.copied, again.skipped, again.xmp_written), (0, 1, 1))
            self.assertTrue((work / "IMG_1234.xmp").exists())
            (work / "IMG_1234.xmp").write_bytes(b"edits")
            third = service.copy_matches(matches, work, "rename", write_xmp=True)
            self.assertEqual((third.skipped, third.xmp_written), (1, 0))
            self.assertEqual((work / "IMG_1234.xmp").read_bytes(), b"edits")
        self.assertIn("identical copy already in work folder", again.items[0]["detail"])

    def test_different_existing_file_still_renames(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = _folders(Path(tmp))
            (raw / "IMG_1234.CR3").write_bytes(b"raw")
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            (work / "IMG_1234.CR3").write_bytes(b"other")
            service = AutoSelectorService()
            result = service.copy_matches(service.analyze(raw, jpg).matches, work, "rename")
            self.assertTrue((work / "IMG_1234_001.CR3").exists())
        self.assertEqual(result.copied, 1)

    def test_xmp_failure_is_one_failed_item_and_retry_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = _folders(Path(tmp))
            (raw / "IMG_1234.CR3").write_bytes(b"raw")
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            service = AutoSelectorService()
            matches = service.analyze(raw, jpg).matches
            with patch.object(AutoSelectorService, "_write_selected_xmp", side_effect=OSError("locked")):
                result = service.copy_matches(matches, work, "rename", write_xmp=True)
            self.assertEqual((result.copied, result.errors, result.xmp_written), (0, 1, 0))
            self.assertEqual([i["status"] for i in result.items], ["failed"])
            self.assertIn("RAW copied to", result.items[0]["detail"])
            self.assertIn("XMP write failed", result.items[0]["detail"])
            retry = service.copy_matches(matches, work, "rename", write_xmp=True)
            self.assertEqual(sorted(p.name for p in work.glob("*.CR3")), ["IMG_1234.CR3"])
            self.assertTrue((work / "IMG_1234.xmp").exists())
        self.assertEqual((retry.errors, retry.xmp_written), (0, 1))


class ExcludeAndHandoffTests(unittest.TestCase):
    def test_work_folder_inside_raw_source_is_not_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, jpg = root / "raw", root / "jpg"
            work = raw / "work"
            for folder in (raw, jpg, work):
                folder.mkdir(parents=True, exist_ok=True)
            (raw / "IMG_1234.CR3").write_bytes(b"raw")
            (work / "IMG_1234.CR3").write_bytes(b"raw")
            (jpg / "IMG_1234.jpg").write_bytes(b"j")
            service = AutoSelectorService()
            self.assertEqual(service.analyze(raw, jpg).matches[0].status, "ambiguous")
            match = service.analyze(raw, jpg, exclude=work).matches[0]
        self.assertEqual((match.status, match.raw_path), ("matched", raw / "IMG_1234.CR3"))

    def test_cache_thumbnails_are_not_selected_jpgs(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = _folders(Path(tmp))
            (raw / "IMG_0001.CR3").write_bytes(b"raw")
            (raw / "IMG_0002.CR3").write_bytes(b"raw")
            (jpg / "IMG_0001.jpg").write_bytes(b"j")
            cache = jpg / ".dsb_cache" / "thumbnails"
            cache.mkdir(parents=True)
            (cache / "IMG_0002.jpg").write_bytes(b"t")
            (jpg / ".dsb_cache" / "IMG_0002_proxy.jpg").write_bytes(b"t")
            summary = AutoSelectorService().analyze(raw, jpg)
        self.assertEqual([m.jpg_path.name for m in summary.matches], ["IMG_0001.jpg"])

    def test_jpg_files_restricts_the_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, _ = _folders(Path(tmp))
            for n in (1, 2):
                (raw / f"IMG_000{n}.CR3").write_bytes(b"raw")
                (jpg / f"IMG_000{n}.jpg").write_bytes(b"j")
            summary = AutoSelectorService().analyze(raw, jpg, jpg_files=[jpg / "IMG_0002.jpg"])
        self.assertEqual([m.jpg_path.name for m in summary.matches], ["IMG_0002.jpg"])

    def test_load_handoff_reads_picked_jpgs_only(self):
        from ndex_common.jsonio import write_json_atomic
        from ndex_auto_selector.ndex_auto_selector.services.selector import load_handoff

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pick, png = root / "a.jpg", root / "b.png"
            pick.write_bytes(b"j")
            png.write_bytes(b"p")
            manifest = root / "handoff.json"
            write_json_atomic(
                manifest,
                {
                    "kind": "ndex.manifest",
                    "type": "select_handoff",
                    "source": str(root),
                    "items": [{"path": str(pick)}, {"path": str(png)}],
                },
            )
            source, files = load_handoff(manifest)
            with self.assertRaises(ValueError):
                load_handoff(root / "missing.json")
        self.assertEqual((source, files), (root, [pick]))


class CliTests(unittest.TestCase):
    def _run(self, argv, result_errors=0):
        import ndex_auto_selector.main as cli

        out: list[str] = []
        with patch.object(sys, "argv", ["prog", *argv]), \
                patch.object(cli, "_emit", out.append), \
                patch("ndex_common.workflow.record_extract") as record:
            code = cli.main()
        return code, out, record

    def test_cli_records_recursive_prints_ambiguous_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = _folders(Path(tmp))
            (raw / "IMG_0001.CR3").write_bytes(b"raw")
            (jpg / "IMG_0001.jpg").write_bytes(b"j")
            code, out, record = self._run(
                ["--raw-source", str(raw), "--selected-jpg", str(jpg), "--work-folder", str(work),
                 "--copy", "--no-recursive"]
            )
        self.assertEqual(code, 0)
        self.assertIn("Ambiguous: 0", out)
        self.assertIs(record.call_args.kwargs["recursive"], False)

    def test_cli_exit_code_nonzero_on_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpg, work = _folders(Path(tmp))
            (raw / "IMG_0001.CR3").write_bytes(b"raw")
            (jpg / "IMG_0001.jpg").write_bytes(b"j")
            with patch("ndex_common.filecopy.shutil.copy2", side_effect=OSError("disk full")):
                code, _, _ = self._run(
                    ["--raw-source", str(raw), "--selected-jpg", str(jpg),
                     "--work-folder", str(work), "--copy"]
                )
        self.assertEqual(code, 1)


class QueueResilienceTests(unittest.TestCase):
    def test_handler_failure_still_reschedules_and_unfreezes(self):
        from ndex_auto_selector.ndex_auto_selector.ui.tk_app import AutoSelectorApp

        events = queue.Queue()
        events.put(("analysis_done", object()))
        events.put(("progress", 1, 2, "x"))
        calls = SimpleNamespace(after=[], busy=[], failures=0)
        fake = SimpleNamespace(ui_queue=events)
        fake.after = lambda ms, fn: calls.after.append(ms)

        def dispatch(event):
            if event[0] == "analysis_done":
                raise RuntimeError("boom")

        fake._process_queue = lambda: None
        fake._dispatch_event = dispatch

        def failure():
            calls.failures += 1

        fake._report_handler_failure = failure
        AutoSelectorApp._process_queue(fake)
        self.assertEqual(calls.after, [100])
        self.assertEqual(calls.failures, 1)
        self.assertTrue(events.empty())


if __name__ == "__main__":
    unittest.main()
