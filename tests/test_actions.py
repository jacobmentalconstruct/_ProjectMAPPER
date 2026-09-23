import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest

from tests.support import temporary_directory
from projectmapper.application import ActionError, Dispatcher, Request
from projectmapper.application.controller import create_application


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.folder = Path(self.temp.name).resolve()
        self.path = self.folder / "example.txt"
        self.path.write_bytes(b"old\r\n")
        self.app, self.approve = create_application(self.folder)
        self.addCleanup(self.app.close)

    def test_headless_import(self):
        run = subprocess.run([sys.executable, "-B", "-c",
                              "import sys; from projectmapper.application.controller import create_application; assert 'tkinter' not in sys.modules"],
                             capture_output=True, text=True, timeout=10,
                             env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_cancellation_at_approval_publication_is_terminal(self):
        dispatcher = self.app.dispatcher
        finish = dispatcher._finish
        def cancel_at_boundary(operation, status, data=None, error=None):
            if status == "awaiting_approval":
                dispatcher.cancel(operation["id"])
            return finish(operation, status, data, error)
        dispatcher._finish = cancel_at_boundary
        result = self.app.execute("file.delete", {"path": str(self.path)})
        self.assertEqual(result.status, "cancelled")
        self.assertTrue(self.path.exists())

    def test_close_from_observer_does_not_join_itself(self):
        self.app.dispatcher.subscribe(lambda event: self.app.close() if event.type == "started" else None)
        result = self.app.execute("text.open", {"path": str(self.path)})
        self.assertEqual(result.status, "cancelled")
        self.assertFalse(self.app.dispatcher.observer_errors)

    def test_new_nested_paths_inherit_unchecked_parent(self):
        self.app.execute("project.scan")
        self.app.execute("selection.set", {"state": "unchecked"})
        nested = self.folder / "new" / "nested"
        nested.mkdir(parents=True)
        target = nested / "new.txt"
        target.write_text("new")
        self.app.execute("project.scan")
        self.assertEqual(self.app.selection[str(target)], "unchecked")

    def test_obsolete_scan_cannot_publish_rows(self):
        scan = self.app.scan_fn
        def superseded(*args):
            rows = scan(*args)
            self.app.state.mark_scan_requested()
            return rows
        self.app.scan_fn = superseded
        result = self.app.execute("project.scan")
        self.assertEqual(result.error["code"], "stale_scan")
        self.assertEqual(self.app.rows, [])

    def test_binary_hash_helper(self):
        from projectmapper.core.helpers import sha256_bytes
        import hashlib
        data = bytes(range(256))
        self.assertEqual(sha256_bytes(data), hashlib.sha256(data).hexdigest())

    def test_binary_capture_stores_bytes_and_hash(self):
        import sqlite3
        import hashlib
        from contextlib import closing
        data = bytes(range(256))
        (self.folder / "image.png").write_bytes(data)
        self.app.execute("capture.configure", {"include_binary": True})
        result = self.app.execute("snapshot.compile")
        self.assertEqual(result.status, "succeeded", result.error)
        with closing(sqlite3.connect(result.data["path"])) as connection:
            row = connection.execute("SELECT sha256, blob_content FROM project_blobs").fetchone()
        self.assertEqual(row, (hashlib.sha256(data).hexdigest(), data))

    def test_project_preview_cannot_apply_changed_source(self):
        manifest = {"files": [{"path": self.path.name, "hunks": [
            {"search_block": "old", "replace_block": "new"}]}]}
        preview = self.app.execute("project_patch.validate", {"root": str(self.folder), "manifest": manifest})
        self.assertEqual(preview.status, "succeeded", preview.error)
        self.path.write_bytes(b"old\r\nexternal\r\n")
        apply = self.app.execute("project_patch.apply", {"plan_id": preview.data["plan_id"]})
        self.assertEqual(apply.status, "awaiting_approval")
        self.approve(apply.operation_id, True)
        result = self.app.dispatcher.wait(apply.operation_id)
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.path.read_bytes(), b"old\r\nexternal\r\n")

    def test_read_scan_save_shared_events_and_state(self):
        first, second = [], []
        self.app.dispatcher.subscribe(first.append)
        self.app.dispatcher.subscribe(lambda e: (_ for _ in ()).throw(ValueError("broken listener")))
        unsubscribe = self.app.dispatcher.subscribe(second.append)
        opened = self.app.execute("text.open", {"path": str(self.path)})
        self.assertEqual(opened.status, "succeeded")
        scanned = self.app.execute("project.scan")
        self.assertEqual(scanned.data["count"], 2)
        result = self.app.execute("text.save", {"path": str(self.path), "text": "new\r\n", "sha256": opened.data["sha256"]})
        self.assertEqual(result.status, "succeeded", result)
        self.assertEqual(self.path.read_bytes(), b"new\r\n")
        self.app.close()
        self.assertEqual(first, second)
        self.assertEqual([e.sequence for e in first], sorted(e.sequence for e in first))
        self.assertTrue(self.app.dispatcher.observer_errors)
        self.assertIn("file_transformed", self.app.state_view()["dirty_reasons"])
        self.assertNotIn('"text":', json.dumps([e.to_dict() for e in first]))
        unsubscribe()

    def test_duplicate_request_does_not_repeat_save(self):
        opened = self.app.execute("text.open", {"path": str(self.path)})
        payload = {"path": str(self.path), "text": "new", "sha256": opened.data["sha256"]}
        first = self.app.execute("text.save", payload, request_id="same")
        second = self.app.execute("text.save", payload, request_id="same")
        self.assertEqual(first, second)
        self.assertEqual(first.status, "succeeded")
        with self.assertRaises(ActionError):
            self.app.execute("text.save", dict(payload, text="other"), request_id="same")

    def test_approval_required_and_forged_flag_rejected(self):
        forged = self.app.execute("file.delete", {"path": str(self.path), "approved": True})
        self.assertEqual(forged.error["code"], "invalid_input")
        result = self.app.execute("file.delete", {"path": str(self.path)})
        self.assertEqual(result.status, "awaiting_approval")
        self.assertTrue(self.path.exists())
        # Other actions can execute while this one waits for human approval.
        self.assertEqual(self.app.execute("project.scan").status, "succeeded")
        self.approve(result.operation_id, False)
        self.assertEqual(self.app.dispatcher.wait(result.operation_id).status, "cancelled")
        self.assertTrue(self.path.exists())
        with self.assertRaises(ActionError):
            self.approve(result.operation_id, True)

    def test_approval_rechecks_external_changes_and_root_generation(self):
        for change in (lambda: self.path.write_bytes(b"external"),
                       lambda: self.app.execute("project.set_root", {"path": str(self.folder)})):
            result = self.app.execute("file.delete", {"path": str(self.path)})
            change()
            self.approve(result.operation_id, True)
            result = self.app.dispatcher.wait(result.operation_id)
            self.assertEqual(result.error["code"], "stale_plan")
            self.assertTrue(self.path.exists())

    def test_approved_delete_marks_state(self):
        result = self.app.execute("file.delete", {"path": str(self.path)})
        self.approve(result.operation_id, True)
        result = self.app.dispatcher.wait(result.operation_id)
        self.assertEqual(result.status, "succeeded")
        self.assertFalse(self.path.exists())
        self.assertIn("file_transformed", self.app.state_view()["dirty_reasons"])

    def test_serialization_and_per_operation_cancellation(self):
        dispatcher = self.app.dispatcher
        entered = threading.Event()
        release = threading.Event()
        writes = []
        def slow(payload, context):
            entered.set()
            release.wait(3)
            context.check_cancelled()
            writes.append(payload["name"])
            return {}
        dispatcher.register("test.slow", slow)
        first = dispatcher.submit(Request("test.slow", {"name": "first"}))
        self.assertTrue(entered.wait(2))
        second = dispatcher.submit(Request("test.slow", {"name": "second"}))
        self.assertEqual(dispatcher.get(second).status, "queued")
        dispatcher.cancel(first)
        release.set()
        self.assertEqual(dispatcher.wait(first).status, "cancelled")
        self.assertEqual(dispatcher.wait(second).status, "succeeded")
        self.assertEqual(writes, ["second"])

    def test_event_retention_and_independent_result_copies(self):
        dispatcher = Dispatcher(history_limit=2)
        self.addCleanup(dispatcher.close)
        dispatcher.register("echo", lambda payload, ctx: payload)
        request = Request("echo", {"nested": {"a": 1}})
        result = dispatcher.execute(request)
        result.data["nested"]["a"] = 999
        self.assertEqual(dispatcher.get(result.operation_id).data["nested"]["a"], 1)
        dispatcher.close()
        self.assertTrue(dispatcher.events()["resync_required"])
        self.assertEqual(len(dispatcher.events()["events"]), 2)
