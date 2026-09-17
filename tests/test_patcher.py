from tests.support import temporary_directory, tk_root
import gc
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import tkinter as tk
import unittest
from unittest.mock import patch

from src.app import ProjectMapperApp
from src.tools.patcher import PatchError, PatchSession, apply_patch_text


def hunk(search, replacement, **extra):
    return dict(search_block=search, replace_block=replacement, **extra)


def transform(source, *hunks, force=False):
    return apply_patch_text(source, {"hunks": list(hunks)}, force)


class EngineTests(unittest.TestCase):
    def test_exact_match_precedes_floating(self):
        self.assertEqual(transform("  a\na\n", hunk("a", "b")), "  a\nb\n")

    def test_floating_preserves_relative_indentation_and_trailing_spaces(self):
        self.assertEqual(transform("\told  \r\n", hunk("old", "    new\n        child  ")),
                         "\tnew\r\n\t    child  \r\n")

    def test_force_overrides_per_hunk_false(self):
        self.assertEqual(transform("  a\n", hunk("a", "b", use_patch_indent=False), force=True), "b\n")

    def test_per_hunk_indent(self):
        self.assertEqual(transform("  a\n", hunk("a", " b", use_patch_indent=True)), " b\n")

    def test_multiple_hunks_resolve_original_coordinates(self):
        self.assertEqual(transform("a\nb\nc\n", hunk("a", "x\ny"), hunk("c", "z")), "x\ny\nb\nz\n")

    def test_missing_ambiguous_and_overlapping_hunks(self):
        for source, hunks, error in [
            ("a", [hunk("b", "c")], "not found"),
            (" a\n  a", [hunk("a", "b")], "Ambiguous"),
            ("a\nb", [hunk("a\nb", "x"), hunk("b", "y")], "overlap"),
        ]:
            with self.subTest(error=error), self.assertRaisesRegex(PatchError, error):
                transform(source, *hunks)

    def test_invalid_schemas(self):
        for obj in [None, [], {}, {"hunks": []}, {"hunks": [None]},
                    {"hunks": [hunk("", "b")]}, {"hunks": [hunk(1, "b")]},
                    {"hunks": [hunk("a", "b", use_patch_indent="false")]}]:
            with self.subTest(obj=obj), self.assertRaises(PatchError):
                apply_patch_text("a", obj)

    def test_preserves_endings_and_final_newline(self):
        for ending in ("\n", "\r\n", "\r"):
            for final in ("", ending):
                with self.subTest(ending=ending, final=final):
                    self.assertEqual(transform("a" + ending + "b" + final, hunk("b", "c\nd")),
                                     "a" + ending + "c" + ending + "d" + final)
        self.assertEqual(transform("a\r\nb\nc\r", hunk("b", "x")), "a\r\nx\nc\r")

    def test_delete_entire_file_and_block(self):
        self.assertEqual(transform("a\n", hunk("a", "")), "")
        self.assertEqual(transform("a\nb\nc", hunk("b", "")), "a\nc")


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.path = Path(self.temp.name).resolve() / "target.py"
        self.path.write_bytes(b"\xef\xbb\xbfa\r\n")

    def test_roundtrip_bom_and_line_endings(self):
        session = PatchSession(self.path)
        session.save(transform(session.source, hunk("a", "b")))
        self.assertEqual(self.path.read_bytes(), b"\xef\xbb\xbfb\r\n")

    def test_external_edit_refuses_save(self):
        session = PatchSession(self.path)
        self.path.write_bytes(b"external")
        with self.assertRaisesRegex(PatchError, "changed on disk"):
            session.save("b")
        self.assertEqual(self.path.read_bytes(), b"external")

    def test_version_save_and_collision(self):
        session = PatchSession(self.path)
        result = session.save("b", "v2")
        self.assertEqual(result.name, "target_v2.py")
        self.assertEqual(self.path.read_bytes(), b"\xef\xbb\xbfa\r\n")
        with self.assertRaisesRegex(PatchError, "already exists"):
            PatchSession(self.path).save("c", "v2")

    def test_invalid_version_suffix(self):
        for suffix in ("", "../escape", "a/b", "a\\b", "a:b"):
            with self.subTest(suffix=suffix), self.assertRaises(PatchError):
                PatchSession(self.path).save("b", suffix)

    def test_failed_replace_preserves_target_and_cleans_scratch(self):
        original = self.path.read_bytes()
        with patch("src.tools.patcher.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                PatchSession(self.path).save("b")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_binary_and_invalid_utf8_rejected(self):
        for data in (b"a\x00b", b"\xff"):
            self.path.write_bytes(data)
            with self.assertRaises(PatchError):
                PatchSession(self.path)

    def test_parts_path_rejected_without_access(self):
        # No fixture is ever created inside a .parts directory.
        with self.assertRaisesRegex(PatchError, "read-only"):
            PatchSession(self.path.parent / ".parts" / "reference.py")

    def test_vendor_export_runs_without_reference_folder(self):
        from src.app import create_vendor_export
        result = create_vendor_export(export_root=self.path.parent / "exports", make_zip=False)
        exported = Path(result["export_dir"])
        self.assertFalse((exported / ".parts").exists())
        self.assertTrue((exported / "src" / "tools" / "patcher.py").is_file())
        self.assertTrue((exported / "src" / "tools" / "patcher_ui.py").is_file())
        self.assertTrue((exported / "src" / "tools" / "text_toucher.py").is_file())
        self.assertTrue((exported / "src" / "tools" / "text_editor.py").is_file())
        check = subprocess.run([
            sys.executable, "-B", "-c",
            "import runpy, sys; runpy.run_module('src.app', run_name='smoke'); "
            "sys.path.insert(0, 'src'); runpy.run_path('src/app.py', run_name='smoke')",
        ], cwd=exported, capture_output=True, text=True, timeout=20)
        self.assertEqual(check.returncode, 0, check.stderr)


class PatcherUITests(unittest.TestCase):
    def setUp(self):
        gc.collect()  # Collect Tk objects on the UI thread before starting workers.
        self.temp = temporary_directory(self)
        self.project = Path(self.temp.name).resolve()
        self.path = self.project / "target.py"
        self.path.write_bytes(b"a\r\n")
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.app.selected_root = self.project
        self.window = self.app.open_tokenizing_patcher(self.path)
        self.root.update_idletasks()

    def set_patch(self, replacement):
        self.window.patch_box.delete("1.0", "end")
        self.window.patch_box.insert("1.0", json.dumps({"hunks": [hunk("a", replacement)]}))
        self.root.update_idletasks()

    def test_preview_apply_save_and_snapshot_invalidation(self):
        self.set_patch("b")
        self.window.validate()
        self.assertEqual(self.path.read_bytes(), b"a\r\n")
        self.assertEqual(self.window.session.source, "a\r\n")
        self.window.apply()
        self.assertEqual(self.path.read_bytes(), b"a\r\n")
        self.window.save()
        self.assertEqual(self.path.read_bytes(), b"b\r\n")
        self.assertTrue(self.app.scan_pending)
        self.assertIsNone(self.app._require_latest_snapshot())
        self.app._accept_compiled_snapshot(self.project / "new.sqlite3", self.project, self.app.scan_revision)
        self.assertFalse(self.app.transformed_paths)

    def test_edited_patch_cannot_use_stale_preview(self):
        self.set_patch("b")
        self.window.validate()
        self.window.apply()
        self.set_patch("c")
        self.window.save()
        self.assertEqual(self.path.read_bytes(), b"a\r\n")
        self.assertIsNone(self.window.result)

    def test_force_change_cannot_use_stale_preview(self):
        self.set_patch("b")
        self.window.validate()
        self.window.force_indent.set(True)
        self.window.apply()
        self.assertIsNone(self.window.result)

    def test_empty_result_can_be_saved(self):
        self.set_patch("")
        self.window.validate()
        self.window.apply()
        self.window.save()
        self.assertEqual(self.path.read_bytes(), b"")

    def test_linked_buttons_both_validate_current_patch_and_apply_without_saving(self):
        self.window.link_button.invoke()
        for button, replacement in ((self.window.validate_button, "b"), (self.window.apply_button, "c")):
            self.set_patch(replacement)
            button.invoke()
            self.assertEqual(self.window.result, replacement + "\r\n")
            self.assertEqual(self.path.read_bytes(), b"a\r\n")

    def test_linked_validation_failure_stops_chain_and_clears_old_result(self):
        self.window.link_button.invoke()
        self.set_patch("b")
        self.window.validate_button.invoke()
        for invalid in ('{', json.dumps({"hunks": [hunk("missing", "c")]})):
            self.window.patch_box.delete("1.0", "end")
            self.window.patch_box.insert("1.0", invalid)
            self.root.update_idletasks()
            with patch.object(self.window, "apply") as apply:
                self.window.apply_button.invoke()
                apply.assert_not_called()
            self.assertIsNone(self.window.result)
            self.assertEqual(str(self.window.save_button["state"]), "disabled")
            self.assertIn("Validation failed", self.window.status.get())

    def test_unlink_restores_separate_actions(self):
        self.window.link_button.invoke()
        self.window.link_button.invoke()
        self.set_patch("b")
        self.assertEqual(str(self.window.apply_button["state"]), "disabled")
        self.window.validate_button.invoke()
        self.assertIsNone(self.window.result)
        self.window.apply_button.invoke()
        self.assertEqual(self.window.result, "b\r\n")

    def test_linked_empty_replacement_is_applied(self):
        self.set_patch("")
        self.window.link_button.invoke()
        self.window.apply_button.invoke()
        self.assertEqual(self.window.result, "")
        self.assertEqual(str(self.window.save_button["state"]), "normal")

    def test_file_menu_does_not_change_capture_selection(self):
        from types import SimpleNamespace
        from src.app import scan_project_tree
        rows, _ = scan_project_tree(self.project, self.app.exclusion_policy)
        self.app.populate_tree(rows)
        tree = self.app.widgets["folder_tree"]
        tree.focus(str(self.path))
        before = dict(self.app.folder_item_states)
        with patch("src.app.tk.Menu") as menu:
            self.app.on_file_context_menu(SimpleNamespace(keysym="F10"))
            self.assertEqual(menu.return_value.add_command.call_count, 5)
        self.assertEqual(self.app.folder_item_states, before)

    def test_save_waits_for_capture(self):
        self.set_patch("b")
        self.window.validate()
        self.window.apply()
        self.app.running_tasks.add("compile_snapshot")
        self.window.save()
        self.assertEqual(self.path.read_bytes(), b"a\r\n")
        self.app.running_tasks.clear()

    def test_menu_remains_available_after_posting(self):
        from types import SimpleNamespace
        from src.app import scan_project_tree
        rows, _ = scan_project_tree(self.project, self.app.exclusion_policy)
        self.app.populate_tree(rows)
        self.app.widgets["folder_tree"].focus(str(self.path))
        with patch.object(tk.Menu, "tk_popup"):
            self.app.on_file_context_menu(SimpleNamespace(keysym="F10"))
        self.assertTrue(self.app.file_context_menu.winfo_exists())
        self.assertEqual(self.app.file_context_menu.entrycget(0, "label"), "Tokenizing Patcher…")

    def test_mouse_release_posts_file_menu_and_opens_clicked_file(self):
        from src.app import scan_project_tree
        rows, _ = scan_project_tree(self.project, self.app.exclusion_policy)
        self.app.populate_tree(rows)
        self.root.deiconify()
        self.root.update()
        tree = self.app.widgets["folder_tree"]
        tree.see(str(self.path))
        self.root.update_idletasks()
        x, y, width, height = tree.bbox(str(self.path))
        before = dict(self.app.folder_item_states)
        with patch.object(tk.Menu, "tk_popup") as popup:
            tree.event_generate("<ButtonPress-3>", x=x + 60, y=y + height // 2)
            popup.assert_not_called()
            tree.event_generate("<ButtonRelease-3>", x=x + 60, y=y + height // 2)
            popup.assert_called_once()
        self.assertEqual(tree.selection(), (str(self.path),))
        self.assertEqual(self.app.folder_item_states, before)
        with patch.object(self.app, "open_tokenizing_patcher") as open_patcher:
            self.app.file_context_menu.invoke(0)
            open_patcher.assert_called_once_with(self.path)

    def test_folder_right_click_explains_file_only_operation(self):
        from types import SimpleNamespace
        from src.app import scan_project_tree
        rows, _ = scan_project_tree(self.project, self.app.exclusion_policy)
        self.app.populate_tree(rows)
        self.app.widgets["folder_tree"].focus(str(self.project))
        with patch.object(tk.Menu, "tk_popup") as popup:
            self.app.on_file_context_menu(SimpleNamespace(keysym="F10"))
            popup.assert_called_once()
        self.assertEqual(self.app.file_context_menu.entrycget(0, "state"), "disabled")
        self.assertIn("file", self.app.file_context_menu.entrycget(0, "label").lower())

    def test_controls_fit_minimum_window(self):
        self.root.deiconify()
        self.window.top.geometry("760x550")
        self.root.update()
        self.window.link_button.invoke()
        for button in (self.window.validate_button, self.window.apply_button, self.window.save_button):
            self.assertGreater(button.winfo_width(), 60)
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                 self.window.top.winfo_rootx() + self.window.top.winfo_width())


if __name__ == "__main__":
    unittest.main()
