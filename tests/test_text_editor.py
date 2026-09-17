from tests.support import temporary_directory, tk_root
import gc
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from src.app import ProjectMapperApp, scan_project_tree


class EditorTests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.temp = temporary_directory(self)
        self.folder = Path(self.temp.name).resolve()
        self.path = self.folder / "sample.py"
        self.path.write_bytes(b"print('hello')\r\n")
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.app.selected_root = self.folder
        self.window = self.app.open_text_editor(self.path)
        self.root.update_idletasks()

    def set_content(self, text):
        self.window.editor.delete("1.0", "end")
        self.window.editor.insert("1.0", text)
        self.window.editor.edit_modified(True)
        self.window.changed()
        self.root.update_idletasks()

    def test_editor_loads_and_tracks_dirty_state(self):
        self.assertEqual(self.window.content(), "print('hello')\r\n")
        self.set_content("print('goodbye')\r\n")
        self.assertTrue(self.window.dirty)
        self.assertIn("•", self.window.top.title())

    def test_guarded_save_preserves_line_endings_and_invalidates_snapshot(self):
        self.set_content("print('goodbye')\r\n")
        self.window.save()
        self.assertEqual(self.path.read_bytes(), b"print('goodbye')\r\n")
        self.assertFalse(self.window.dirty)
        self.assertTrue(self.app.scan_pending)

    def test_external_change_refuses_save(self):
        self.set_content("changed\r\n")
        self.path.write_bytes(b"external\r\n")
        self.window.save()
        self.assertEqual(self.path.read_bytes(), b"external\r\n")
        self.assertIn("Save failed", self.window.status.get())

    def test_replace_all_requires_confirmation(self):
        with patch("src.tools.text_editor.messagebox.askyesno", return_value=False):
            self.window.replace_all("hello", "goodbye")
        self.assertIn("hello", self.window.content())
        with patch("src.tools.text_editor.messagebox.askyesno", return_value=True):
            self.window.replace_all("hello", "goodbye")
        self.assertEqual(self.window.content(), "print('goodbye')\r\n")
        self.assertTrue(self.window.dirty)

    def test_read_only_blocks_save_and_replace(self):
        self.window.read_only_var.set(True)
        self.window.toggle_read_only()
        self.assertEqual(str(self.window.editor["state"]), "disabled")
        self.window.replace_all("hello", "goodbye")
        self.window.save()
        self.assertEqual(self.path.read_bytes(), b"print('hello')\r\n")

    def test_patcher_action_targets_current_file(self):
        with patch.object(self.app, "open_tokenizing_patcher") as open_patcher:
            self.window.open_patcher()
            open_patcher.assert_called_once_with(self.path)

    def test_context_menu_editor_is_file_only(self):
        rows, _ = scan_project_tree(self.folder, self.app.exclusion_policy)
        self.app.populate_tree(rows)
        self.app.widgets["folder_tree"].focus(str(self.path))
        with patch.object(tk.Menu, "tk_popup"):
            self.app.on_file_context_menu(type("Event", (), {"keysym": "F10"})())
        menu = self.app.file_context_menu
        self.assertEqual(menu.entrycget(1, "label"), "Open Text Editor…")
        self.assertEqual(menu.entrycget(1, "state"), "normal")


if __name__ == "__main__":
    unittest.main()
