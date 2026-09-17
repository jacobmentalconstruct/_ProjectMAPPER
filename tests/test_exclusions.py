from tests.support import temporary_directory, tk_root
import copy
import contextlib
import sqlite3
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app import ExclusionPolicy, ProjectMapperApp, S_CHECKED, S_UNCHECKED, compile_snapshot, scan_project_tree


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.root = Path(self.temp.name).resolve()
        (self.root / ".gitignore").write_text("cache/\n*.tmp\nsecret/data.txt\n")
        for directory in ("cache", "node_modules", "secret"):
            (self.root / directory).mkdir()
        for name in ("example.tmp", "package-lock.json", "secret/data.txt", "keep.txt"):
            (self.root / name).write_text("example")
        self.policy = ExclusionPolicy()
        self.policy.load_gitignore(self.root)

    def test_each_source_can_be_disabled_and_reenabled(self):
        self.policy.add_pattern("keep.txt")
        for source, pattern, path in (
            ("hardcoded_folder", "node_modules", "node_modules"),
            ("predefined_filename", "package-lock.json", "package-lock.json"),
            ("dynamic_user_pattern", "keep.txt", "keep.txt"),
            ("gitignore_dirname", "cache", "cache"),
            ("gitignore_file_pattern", "*.tmp", "example.tmp"),
            ("gitignore_path_pattern", "secret/data.txt", "secret/data.txt"),
        ):
            with self.subTest(source=source):
                self.assertTrue(self.policy.should_exclude_path(self.root / path, self.root)[0])
                self.policy.set_rule_enabled(source, pattern, False)
                self.assertFalse(self.policy.should_exclude_path(self.root / path, self.root)[0])
                rule = next(r for r in self.policy.collect_rules() if r["source"] == source and r["pattern"] == pattern)
                self.assertEqual(rule["active"], 0)
                self.policy.set_rule_enabled(source, pattern, True)
                self.assertTrue(self.policy.should_exclude_path(self.root / path, self.root)[0])

    def test_overlapping_rules_remain_independent(self):
        self.policy.add_pattern("*.tmp")
        self.policy.set_rule_enabled("gitignore_file_pattern", "*.tmp", False)
        self.assertTrue(self.policy.should_exclude_path(self.root / "example.tmp", self.root)[0])
        self.policy.delete_rule("dynamic_user_pattern", "*.tmp")
        self.assertFalse(self.policy.should_exclude_path(self.root / "example.tmp", self.root)[0])

    def test_deleted_import_survives_reload_without_changing_file(self):
        before = (self.root / ".gitignore").read_bytes()
        self.policy.delete_rule("gitignore_file_pattern", "*.tmp")
        self.policy.load_gitignore(self.root)
        self.assertFalse(self.policy.should_exclude_path(self.root / "example.tmp", self.root)[0])
        self.assertFalse(any(r["pattern"] == "*.tmp" for r in self.policy.collect_rules()))
        self.assertEqual(before, (self.root / ".gitignore").read_bytes())

    def test_import_overrides_are_scoped_to_project(self):
        self.policy.set_rule_enabled("gitignore_file_pattern", "*.tmp", False)
        other = self.root / "other"
        other.mkdir()
        (other / ".gitignore").write_text("*.tmp\n")
        self.policy.load_gitignore(other)
        self.assertTrue(self.policy.rule_enabled("gitignore_file_pattern", "*.tmp"))
        self.policy.load_gitignore(self.root)
        self.assertFalse(self.policy.rule_enabled("gitignore_file_pattern", "*.tmp"))

    def test_global_bypass_preserves_individual_states(self):
        self.policy.set_rule_enabled("hardcoded_folder", "node_modules", False)
        self.policy.respect_exclusions = False
        rows, skipped = scan_project_tree(self.root, self.policy)
        self.assertFalse(skipped)
        self.assertIn("example.tmp", {r["relative_path"] for r in rows})
        self.policy.respect_exclusions = True
        self.assertFalse(self.policy.rule_enabled("hardcoded_folder", "node_modules"))
        self.assertTrue(self.policy.should_exclude_path(self.root / "example.tmp", self.root)[0])

    def test_scan_uses_independent_policy_copy(self):
        frozen = copy.deepcopy(self.policy)
        self.policy.delete_rule("hardcoded_folder", "node_modules")
        self.assertTrue(frozen.should_exclude_path(self.root / "node_modules", self.root)[0])
        self.assertFalse(self.policy.should_exclude_path(self.root / "node_modules", self.root)[0])

    def test_snapshot_records_disabled_rules_and_updated_tree(self):
        self.policy.set_rule_enabled("gitignore_file_pattern", "*.tmp", False)
        self.policy.delete_rule("hardcoded_folder", "node_modules")
        rows, skipped = scan_project_tree(self.root, self.policy)
        snapshot = compile_snapshot(self.root, self.root / "_projectmapper", rows,
                                    {str(r["path"]): S_CHECKED for r in rows}, self.policy, skipped)
        with contextlib.closing(sqlite3.connect(snapshot)) as conn:
            self.assertEqual(conn.execute("SELECT active FROM snapshot_exclusion_rules WHERE pattern = '*.tmp'").fetchone(), (0,))
            self.assertIsNone(conn.execute("SELECT active FROM snapshot_exclusion_rules WHERE pattern = 'node_modules'").fetchone())
            self.assertIsNotNone(conn.execute("SELECT 1 FROM project_tree WHERE relative_path = 'example.tmp'").fetchone())


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.project = Path(self.temp.name).resolve()
        (self.project / "keep.txt").write_text("keep")
        (self.project / "test.tmp").write_text("temporary")
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root)
        # Keep tests deterministic: run requested workers and queued UI callbacks
        # explicitly, without launching the app's startup scan.
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.app.selected_root = self.project
        self.app.exclusion_policy.load_gitignore(self.project)
        self.app.manage_exclusions_popup()
        self.popup = self.app.exclusions_popup
        self.root.update_idletasks()

    def run_scan(self):
        if self.app.scan_after_id is not None:
            self.root.after_cancel(self.app.scan_after_id)
        with patch.object(self.app, "run_threaded_action", side_effect=lambda target, *args, **kwargs: target()):
            self.app._start_pending_scan()
        while not self.app.gui_queue.empty():
            self.app.gui_queue.get_nowait()()

    def test_selection_is_independent_and_batch_actions_refresh(self):
        before = self.app.exclusion_policy.collect_rules()
        self.popup.select_all(True)
        self.assertEqual(len(self.popup.selected), len(self.popup.rules))
        self.assertEqual(before, self.app.exclusion_policy.collect_rules())
        self.popup.select_all(False)
        self.assertFalse(self.popup.selected)
        self.assertEqual(str(self.popup.batch_buttons[-1]["state"]), "disabled")
        self.popup.select_all(True)
        self.popup.set_selected_enabled(False)
        self.assertTrue(all(not r["active"] for r in self.popup.rules))
        self.popup.set_selected_enabled(True)
        self.assertTrue(all(r["active"] for r in self.popup.rules))
        self.popup.delete_selected()
        self.assertFalse(self.popup.rules)
        self.assertFalse(self.popup.selected)
        self.assertTrue(self.app.scan_pending)
        self.run_scan()
        self.assertFalse(self.app.scan_pending)

    def test_checkbox_invocation_and_add_from_both_entries(self):
        self.popup.entry.insert(0, "*.tmp")
        self.popup.add_pattern()
        custom_index = next(i for i, r in enumerate(self.popup.rules, 1) if r["pattern"] == "*.tmp")
        checkbox = self.popup.rows_frame.grid_slaves(row=custom_index, column=1)[0]
        checkbox.invoke()
        self.assertFalse(self.app.exclusion_policy.rule_enabled("dynamic_user_pattern", "*.tmp"))
        self.app.widgets["exclusion_entry"].insert(0, "*.tmp")
        self.app.add_exclusion_from_entry()
        self.assertTrue(self.app.exclusion_policy.rule_enabled("dynamic_user_pattern", "*.tmp"))
        self.assertEqual(sum(r["pattern"] == "*.tmp" for r in self.popup.rules), 1)
        self.run_scan()
        self.assertNotIn("test.tmp", {r["relative_path"] for r in self.app.tree_rows})

    def test_rapid_changes_reject_old_scan_and_preserve_tree_selection(self):
        self.app.request_rescan_tree_silent()
        self.run_scan()
        self.app.folder_item_states[str(self.project / "keep.txt")] = S_UNCHECKED
        old_revision = self.app.scan_revision
        old_rows = list(self.app.tree_rows)
        self.app.exclusion_policy.add_pattern("*.tmp")
        self.app.exclusions_changed()
        self.app._apply_tree_scan(self.project, old_revision, [], [])
        self.assertEqual(self.app.tree_rows, old_rows)
        self.run_scan()
        self.assertNotIn("test.tmp", {r["relative_path"] for r in self.app.tree_rows})
        self.assertEqual(self.app.folder_item_states[str(self.project / "keep.txt")], S_UNCHECKED)
        self.app.widgets["respect_exclusions"].set(False)
        self.app.apply_exclusion_settings()
        self.run_scan()
        self.assertIn("test.tmp", {r["relative_path"] for r in self.app.tree_rows})

    def test_single_window_and_buttons_fit(self):
        self.root.deiconify()
        self.root.update()
        self.app.manage_exclusions_popup()
        self.assertIs(self.popup, self.app.exclusions_popup)
        for size in ("800x560", "690x420"):
            self.popup.top.geometry(size)
            self.root.update()
            for button in self.popup.batch_buttons:
                self.assertGreater(button.winfo_width(), 30, (size, button.cget("text"), self.popup.top.winfo_width(), button.master.winfo_width(), button.winfo_reqwidth()))
                self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                     self.popup.top.winfo_rootx() + self.popup.top.winfo_width())

    def test_changes_during_running_scan_are_eventually_applied(self):
        started = threading.Event()
        release = threading.Event()

        def slow_scan(*args, **kwargs):
            started.set()
            release.wait(3)
            return scan_project_tree(*args, **kwargs)

        with patch("src.app.scan_project_tree", side_effect=slow_scan):
            self.app.request_rescan_tree_silent()
            self.root.after_cancel(self.app.scan_after_id)
            self.app._start_pending_scan()
            self.assertTrue(started.wait(2))
            self.app.exclusion_policy.add_pattern("*.tmp")
            self.app.exclusions_changed()
            release.set()
            deadline = time.monotonic() + 5
            while (self.app.scan_pending or self.app.running_tasks) and time.monotonic() < deadline:
                self.root.update()
                while not self.app.gui_queue.empty():
                    self.app.gui_queue.get_nowait()()
                time.sleep(0.01)
        self.assertFalse(self.app.scan_pending)
        self.assertEqual(self.app.applied_scan_revision, self.app.scan_revision)
        self.assertNotIn("test.tmp", {r["relative_path"] for r in self.app.tree_rows})

    def test_changed_rules_block_exports_until_current_compile(self):
        self.app.exclusions_changed()
        self.assertIsNone(self.app._require_latest_snapshot())
        self.app._accept_compiled_snapshot(self.project / "old.sqlite3", self.project, self.app.scan_revision - 1)
        self.assertTrue(self.app.exclusions_dirty)
        self.app._accept_compiled_snapshot(self.project / "new.sqlite3", self.project, self.app.scan_revision)
        self.assertFalse(self.app.exclusions_dirty)


if __name__ == "__main__":
    unittest.main()
