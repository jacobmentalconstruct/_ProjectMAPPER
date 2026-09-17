import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.support import temporary_directory, tk_root
from src.core.state import ProjectState
from src.core.diagnostics import collect_diagnostics
from src.tools.patcher import PatchError
from src.tools.project_patcher import ProjectPatchSession
from src.core.writes import stage_bytes
from src.core.writes import create_backup
from src.app import ProjectMapperApp, S_UNCHECKED, compile_snapshot, scan_project_tree


def manifest(*names):
    return {"files": [{"path": name, "hunks": [{"search_block": "old", "replace_block": "new"}]}
                      for name in names]}


class WriteSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.folder = Path(self.temp.name).resolve()
        for name in ("a.txt", "b.txt"):
            (self.folder / name).write_bytes(b"old\r\n")

    def session(self):
        session = ProjectPatchSession(self.folder, manifest("a.txt", "b.txt"))
        session.validate_all()
        return session

    def test_staging_conflict_does_not_restore_untouched_files(self):
        session = self.session()
        def stage(destination, data, **kwargs):
            scratch = stage_bytes(destination, data, **kwargs)
            (self.folder / "a.txt").write_bytes(b"external")
            return scratch
        with patch("src.tools.project_patcher.stage_bytes", side_effect=stage):
            with self.assertRaises(PatchError):
                session.apply_all()
        self.assertEqual((self.folder / "a.txt").read_bytes(), b"external")
        self.assertEqual((self.folder / "b.txt").read_bytes(), b"old\r\n")
        self.assertFalse(list(self.folder.glob('.project-patch-*')))

    def test_replacement_failure_restores_only_committed_files(self):
        session = self.session()
        import os
        replace = os.replace
        def failing_replace(source, destination):
            if Path(destination).name == "b.txt":
                (self.folder / "b.txt").write_bytes(b"external")
                raise PermissionError("injected replacement failure")
            return replace(source, destination)
        with patch("src.tools.project_patcher.os.replace", side_effect=failing_replace):
            with self.assertRaises(PatchError):
                session.apply_all()
        self.assertEqual((self.folder / "a.txt").read_bytes(), b"old\r\n")
        self.assertEqual((self.folder / "b.txt").read_bytes(), b"external")

    def test_rollback_preserves_external_edit_to_already_replaced_file(self):
        session = self.session()
        import os
        replace = os.replace
        def failing_replace(source, destination):
            if Path(destination).name == "b.txt":
                (self.folder / "a.txt").write_bytes(b"external after first replacement")
                raise PermissionError("injected failure")
            return replace(source, destination)
        with patch("src.tools.project_patcher.os.replace", side_effect=failing_replace):
            with self.assertRaisesRegex(PatchError, "[Rr]ecovery"):
                session.apply_all()
        self.assertEqual((self.folder / "a.txt").read_bytes(), b"external after first replacement")

    def test_failed_revalidation_clears_previous_results(self):
        session = self.session()
        (self.folder / "b.txt").write_bytes(b"no match")
        with self.assertRaises(PatchError):
            session.validate_all()
        self.assertFalse(session.results)

    def test_diagnostics_does_not_clobber_fixed_name_file(self):
        output = self.folder / "out"
        output.mkdir()
        sentinel = output / ".projectmapper-diagnostic"
        sentinel.write_bytes(b"owned by someone else")
        report = collect_diagnostics(SimpleNamespace(selected_root=self.folder, get_output_dir=lambda: output))
        self.assertTrue(report["ok"], report)
        self.assertEqual(sentinel.read_bytes(), b"owned by someone else")
        self.assertEqual(list(output.iterdir()), [sentinel])

    def test_backup_never_overwrites_existing_file(self):
        backup = self.folder / "a.txt.bak"
        backup.write_bytes(b"unrelated")
        with self.assertRaises(FileExistsError):
            create_backup(self.folder / "a.txt")
        self.assertEqual(backup.read_bytes(), b"unrelated")


class StateSafetyTests(unittest.TestCase):
    def test_root_roundtrip_never_reuses_scan_revision(self):
        state = ProjectState(Path.cwd())
        original = state.mark_scan_requested()
        state.set_root(Path.cwd().parent)
        state.set_root(Path.cwd())
        current = state.mark_scan_requested()
        self.assertNotEqual(original, current)
        self.assertFalse(state.mark_scan_applied(original, 10))


class UISafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.folder = Path(self.temp.name).resolve()
        self.path = self.folder / "a.txt"
        self.path.write_bytes(b"old\r\n")
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.app.selected_root = self.folder
        self.app.project_state.set_root(self.folder)
        self.app.scan_revision = self.app.project_state.mark_scan_requested()
        self.app.action("project.scan", {"revision": self.app.scan_revision})
        rows, skipped = self.app.controller.rows, self.app.controller.skipped
        self.app._apply_tree_scan(self.folder, self.app.scan_revision, rows, skipped)

    def project_window(self):
        window = self.app.open_project_patcher(self.folder)
        window.manifest_box.delete("1.0", "end")
        window.manifest_box.insert("1.0", json.dumps(manifest("a.txt")))
        window.manifest_box.edit_modified(False)
        self.assertTrue(window.validate())
        return window

    def drain_action_events(self):
        while not self.app.gui_queue.empty():
            self.app.gui_queue.get_nowait()()

    def test_headless_client_updates_desktop_controls_and_tree(self):
        controller = self.app.controller
        # The default origin label is deliberately shared: identity, not attribution,
        # determines whether this desktop submitted an operation.
        result = controller.execute("selection.set", {"state": "unchecked"})
        self.assertEqual(result.status, "succeeded")
        self.drain_action_events()
        self.assertEqual(self.app.folder_item_states[str(self.path)], "unchecked")
        controller.execute("capture.configure", {"include_binary": True})
        revision = controller.state.capture_revision
        self.drain_action_events()
        self.assertTrue(self.app.widgets["include_binary_blobs"].get())
        self.assertEqual(controller.state.capture_revision, revision)
        controller.execute("exclusions.update", {"operation": "respect", "respect": False})
        self.drain_action_events()
        self.assertFalse(self.app.widgets["respect_exclusions"].get())
        other = self.folder / "other"
        other.mkdir()
        controller.execute("project.set_root", {"path": str(other)})
        self.drain_action_events()
        self.assertEqual(self.app.widgets["selected_root_var"].get(), str(other))
        controller.execute("project.scan")
        self.drain_action_events()
        self.assertTrue(self.app.widgets["folder_tree"].exists(str(other)))

    def test_headless_write_marks_editor_stale_without_discarding_buffer(self):
        editor = self.app.open_text_editor(self.path)
        editor.editor.insert("end", "unsaved")
        buffer = editor.content()
        controller = self.app.controller
        source = controller.execute("text.open", {"path": str(self.path)}).data
        result = controller.execute("text.save", {"path": str(self.path), "text": "external",
            "sha256": source["sha256"]}, origin="headless")
        self.assertEqual(result.status, "succeeded")
        self.drain_action_events()
        self.assertTrue(editor.stale)
        self.assertEqual(editor.content(), buffer)
        self.assertIn("preserved", editor.status.get())

    def test_programmatic_manifest_edit_cannot_apply_old_preview(self):
        window = self.project_window()
        window.manifest_box.insert("end", "invalid")
        with patch("src.tools.project_patcher_ui.messagebox.askyesno", return_value=True) as approve:
            window.apply()
        self.assertEqual(self.path.read_bytes(), b"old\r\n")
        approve.assert_not_called()

    def test_displayed_plan_rejects_external_change_without_revalidation(self):
        window = self.project_window()
        self.path.write_bytes(b"old\r\nexternal\r\n")
        with patch("src.tools.project_patcher_ui.messagebox.askyesno", return_value=True):
            window.apply()
        self.assertEqual(self.path.read_bytes(), b"old\r\nexternal\r\n")
        self.assertIn("failed", window.status.get().lower())

    def test_approved_project_patch_notifies_observers_and_invalidates_snapshot(self):
        window = self.project_window()
        self.app.project_state.mark_snapshot(self.folder / "previous.sqlite3")
        first, second = [], []
        self.app.controller.dispatcher.subscribe(first.append)
        self.app.controller.dispatcher.subscribe(second.append)
        with patch("src.tools.project_patcher_ui.messagebox.askyesno", return_value=True):
            window.apply()
        self.assertEqual(first, second)
        self.assertTrue(any(e.action == "project_patch.apply" and e.type == "succeeded" for e in first))
        self.assertIn(self.path, self.app.project_state.transformed_paths)
        self.assertIsNone(self.app.project_state.snapshot_path)
        self.assertTrue(self.app.scan_pending)

    def test_denied_project_patch_does_not_dirty_state(self):
        window = self.project_window()
        snapshot = self.folder / "previous.sqlite3"
        self.app.project_state.mark_snapshot(snapshot)
        with patch("src.tools.project_patcher_ui.messagebox.askyesno", return_value=False):
            window.apply()
        self.assertEqual(self.path.read_bytes(), b"old\r\n")
        self.assertEqual(self.app.project_state.snapshot_path, snapshot)
        self.assertFalse(self.app.project_state.transformed_paths)

    def test_edit_during_approval_cannot_apply(self):
        window = self.project_window()
        def approve(*args, **kwargs):
            window.manifest_box.insert("end", "invalid")
            return True
        with patch("src.tools.project_patcher_ui.messagebox.askyesno", side_effect=approve):
            window.apply()
        self.assertEqual(self.path.read_bytes(), b"old\r\n")

    def test_existing_snapshot_can_be_discovered(self):
        snapshot = compile_snapshot(self.folder, self.folder / "_projectmapper", self.app.tree_rows,
                                    self.app.folder_item_states, self.app.exclusion_policy, [])
        self.app.latest_snapshot_path = None
        self.app.project_state.snapshot_path = None
        self.assertEqual(self.app._require_latest_snapshot(), snapshot)

    def test_capture_selection_invalidates_snapshot(self):
        self.app._accept_compiled_snapshot(self.folder / "snapshot.sqlite3", self.folder, self.app.scan_revision)
        self.app.set_global_selection(S_UNCHECKED)
        self.assertFalse(self.app.project_state.can_export())

    def test_capture_option_invalidates_snapshot(self):
        self.app._accept_compiled_snapshot(self.folder / "snapshot.sqlite3", self.folder, self.app.scan_revision)
        self.app.widgets["include_binary_blobs"].set(True)
        self.assertFalse(self.app.project_state.can_export())

    def test_cancelled_compile_preserves_previous_snapshot(self):
        import threading
        output = self.folder / "_projectmapper"
        args = (self.folder, output, self.app.tree_rows, self.app.folder_item_states, self.app.exclusion_policy, [])
        snapshot = compile_snapshot(*args)
        before = snapshot.read_bytes()
        stopped = threading.Event()
        stopped.set()
        with self.assertRaisesRegex(Exception, "[Cc]ancel"):
            compile_snapshot(*args, stop_event=stopped)
        self.assertEqual(snapshot.read_bytes(), before)

    def test_failed_snapshot_replace_preserves_previous_snapshot(self):
        output = self.folder / "_projectmapper"
        args = (self.folder, output, self.app.tree_rows, self.app.folder_item_states, self.app.exclusion_policy, [])
        snapshot = compile_snapshot(*args)
        before = snapshot.read_bytes()
        with patch("src.app.os.replace", side_effect=PermissionError("injected")):
            with self.assertRaises(PermissionError):
                compile_snapshot(*args)
        self.assertEqual(snapshot.read_bytes(), before)
