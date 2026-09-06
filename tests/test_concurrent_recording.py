"""Real spawned processes sharing one disposable NDEX data directory."""

from __future__ import annotations

import multiprocessing
import time
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ndex_common import manifest, retention, session, settings, workflow
from tests.test_workflow import patch_roots


class FixedClock:
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


def _writer(root, mode, index, start):
    with ExitStack() as stack:
        for patcher in patch_roots(root):
            stack.enter_context(patcher)
        if mode == "manifest":
            stack.enter_context(patch.object(manifest, "datetime", FixedClock))
            original = manifest._unused_path

            def slow_path(*args):
                result = original(*args)
                time.sleep(0.05)  # Enlarge the check/write race, without a lock.
                return result

            stack.enter_context(patch.object(manifest, "_unused_path", slow_path))
        elif mode == "session":
            original = session.load_session

            def slow_read(*args, **kwargs):
                result = original(*args, **kwargs)
                time.sleep(0.05)
                return result

            stack.enter_context(patch.object(session, "load_session", slow_read))
        if not start.wait(10):
            raise RuntimeError("start timed out")
        for number in range(3):
            if mode == "manifest":
                manifest.write_manifest(type="backup", app="ndex_one", source=f"{index}/{number}")
            elif mode == "session":
                session.remember("frame", folders={f"folder_{index}": f"value_{number}"},
                                 context={f"worker_{index}": number})
            else:
                def update(data):
                    time.sleep(0.05)
                    data[f"worker_{index}"] = number
                    return data
                settings.atomic_update(update)


def _paused_job(root, written, release):
    with ExitStack() as stack:
        for patcher in patch_roots(root):
            stack.enter_context(patcher)
        original = manifest.write_manifest

        def paused_write(**kwargs):
            path = original(**kwargs)
            written.set()
            if not release.wait(15):
                raise RuntimeError("release timed out")
            return path

        stack.enter_context(patch.object(manifest, "write_manifest", paused_write))
        path = workflow.record_job(app="ndex_one", type="backup", source="card")
        if path is None or not path.is_file():
            raise RuntimeError("job record disappeared before its session was saved")


def _pruner(root, started, finished):
    with ExitStack() as stack:
        for patcher in patch_roots(root):
            stack.enter_context(patcher)
        started.set()
        retention.prune_manifests(keep=1)
        finished.set()


class ConcurrentRecordingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ctx = multiprocessing.get_context("spawn")
        self.workers = []
        self.addCleanup(self.stop_workers)

    def stop_workers(self):
        for worker in self.workers:
            if worker.is_alive():
                worker.terminate()
            worker.join(5)

    def spawn(self, target, *args):
        worker = self.ctx.Process(target=target, args=(self.root, *args))
        worker.start()
        self.workers.append(worker)
        return worker

    def join_workers(self):
        for worker in self.workers:
            worker.join(20)
            self.assertFalse(worker.is_alive(), "worker deadlocked")
            self.assertEqual(worker.exitcode, 0)

    def run_writers(self, mode):
        start = self.ctx.Event()
        for index in range(4):
            self.spawn(_writer, mode, index, start)
        start.set()
        self.join_workers()

    def test_same_second_manifest_writes_never_overwrite_another_job(self):
        self.run_writers("manifest")
        paths = list((self.root / "manifests").glob("backup-*.json"))
        self.assertEqual(len(paths), 12)
        self.assertEqual({manifest.load_manifest(path)["source"] for path in paths},
                         {f"{index}/{number}" for index in range(4) for number in range(3)})

    def test_concurrent_session_merges_preserve_every_workers_fields(self):
        self.run_writers("session")
        document = session.load_session("frame", self.root)
        self.assertEqual(document["folders"], {f"folder_{i}": "value_2" for i in range(4)})
        self.assertEqual(document["context"], {f"worker_{i}": 2 for i in range(4)})
        import json
        stored = json.loads((self.root / "config" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["shared"]["sessions"]["frame"], document)

    def test_settings_updates_wait_for_the_other_process_lock(self):
        self.run_writers("settings")
        import json
        stored = json.loads((self.root / "config" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual({key: stored[key] for key in stored if key.startswith("worker_")},
                         {f"worker_{index}": 2 for index in range(4)})

    def test_pruning_waits_until_new_manifest_is_pinned_by_its_session(self):
        # An older clock makes the new job a pruning candidate immediately.
        with patch.object(manifest, "datetime") as clock:
            clock.now.return_value = datetime(2099, 1, 1, tzinfo=timezone.utc)
            manifest.write_manifest(type="backup", app="ndex_one", root=self.root)
        written, release, started, finished = [self.ctx.Event() for _ in range(4)]
        self.spawn(_paused_job, written, release)
        self.assertTrue(written.wait(10))
        self.spawn(_pruner, started, finished)
        self.assertTrue(started.wait(10))
        try:
            self.assertFalse(finished.wait(0.5), "pruning ran before the session update")
        finally:
            release.set()
        self.join_workers()
        document = session.load_session("ndex_one", self.root)
        self.assertTrue(Path(document["last_manifest"]).is_file())
        self.assertTrue(finished.is_set())


if __name__ == "__main__":
    unittest.main()
