from tests.support import temporary_directory, tk_root
import gc
from datetime import datetime
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from src.app import ProjectMapperApp, scan_project_tree
from src.tools.patcher import PatchError
from src.tools.text_toucher import create_text_file, file_name


class FileCreationTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.folder = Path(self.temp.name).resolve()

    def test_extensions_and_timestamps(self):
        for name, extension, expected in [("notes", ".txt", "notes.txt"),
                                           ("code.rs", ".txt", "code.rs"),
                                           ("LICENSE", "(None)", "LICENSE"),
                                           (".gitignore", ".txt", ".gitignore")]:
            self.assertEqual(file_name(name, extension), expected)
        self.assertEqual(file_name("file.py", timestamp=True, now=datetime(2026, 9, 16, 12, 34, 56)),
                         "file_2026-09-16_12-34-56.py")

    def test_invalid_names_cannot_escape_or_use_reserved_paths(self):
        for name in ("", "..", "../outside", "a/b", "a\\b", "C:\\file", "a:b", "CON", "nul.txt", "bad.", "a\x00b"):
            with self.subTest(name=name), self.assertRaises(PatchError):
                create_text_file(self.folder, name, "content")
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_content_is_exact_and_empty_file_is_empty(self):
        for name, text in (("empty", ""), ("unicode", "héllo"), ("lines", "a\r\nb\n")):
            path = create_text_file(self.folder, name, text)
            self.assertEqual(path.read_bytes(), text.encode("utf-8"))

    def test_existing_file_never_overwritten(self):
        path = create_text_file(self.folder, "keep", "original")
        with self.assertRaises(FileExistsError):
            create_text_file(self.folder, "keep", "replacement")
        self.assertEqual(path.read_text(), "original")

    def test_parts_is_rejected_without_creating_it(self):
        with self.assertRaisesRegex(PatchError, "read-only"):
            create_text_file(self.folder / ".parts", "test", "data")
        self.assertFalse((self.folder / ".parts").exists())

    def test_missing_destination(self):
        with self.assertRaisesRegex(PatchError, "no longer exists"):
            create_text_file(self.folder / "missing", "test", "data")


class CreatorUITests(unittest.TestCase):
    def setUp(self):
        gc.collect()
        self.temp = temporary_directory(self)
        self.folder = Path(self.temp.name).resolve()
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.app.selected_root = self.folder
        self.window = self.app.open_text_toucher(self.folder)
        self.assertIsNotNone(self.window)
        self.root.update_idletasks()

    def test_creation_resets_form_refreshes_tree_and_invalidates_snapshot(self):
        self.window.name.set("hello")
        self.window.content.insert("1.0", "hello")
        self.window.create_button.invoke()
        self.assertEqual((self.folder / "hello.txt").read_bytes(), b"hello")
        self.assertEqual(self.window.name.get(), "")
        self.assertEqual(self.window.content.get("1.0", "end-1c"), "")
        self.assertTrue(self.app.scan_pending)
        self.assertIsNone(self.app._require_latest_snapshot())

    def test_collision_keeps_form_and_existing_content(self):
        (self.folder / "keep.txt").write_text("original")
        self.window.name.set("keep")
        self.window.content.insert("1.0", "replacement")
        self.window.create()
        self.assertEqual((self.folder / "keep.txt").read_text(), "original")
        self.assertEqual(self.window.content.get("1.0", "end-1c"), "replacement")
        self.assertIn("already exists", self.window.status.get())

    def test_waits_for_active_capture(self):
        self.window.name.set("new")
        self.app.running_tasks.add("compile_snapshot")
        self.window.create()
        self.assertFalse((self.folder / "new.txt").exists())
        self.app.running_tasks.clear()

    def test_context_menu_actions_depend_on_target(self):
        child = self.folder / "child"
        child.mkdir()
        target = child / "existing.txt"
        target.write_text("existing")
        rows, _ = scan_project_tree(self.folder, self.app.exclusion_policy)
        self.app.populate_tree(rows)
        for path in (child, target):
            self.app.widgets["folder_tree"].focus(str(path))
            with patch.object(tk.Menu, "tk_popup"):
                self.app.on_file_context_menu(SimpleNamespace(keysym="F10"))
            with patch.object(self.app, "open_text_toucher") as open_creator:
                self.assertEqual(self.app.file_context_menu.entrycget(0, "state"),
                                 "normal" if path == target else "disabled")
                self.assertEqual(self.app.file_context_menu.entrycget(1, "state"),
                                 "normal" if path == target else "disabled")
                self.assertEqual(self.app.file_context_menu.entrycget(2, "state"),
                                 "disabled" if path == target else "normal")
                self.assertEqual(self.app.file_context_menu.entrycget(4, "state"),
                                 "normal" if path == target else "disabled")
                self.app.file_context_menu.invoke(2)
                if path == child:
                    open_creator.assert_called_once_with(child)
                else:
                    open_creator.assert_not_called()

    def test_mouse_empty_space_uses_root_instead_of_previous_selection(self):
        child = self.folder / "child"
        child.mkdir()
        rows, _ = scan_project_tree(self.folder, self.app.exclusion_policy)
        self.app.populate_tree(rows)
        tree = self.app.widgets["folder_tree"]
        tree.focus(str(child))
        tree.selection_set(str(child))
        self.root.deiconify()
        self.root.update()
        y = tree.winfo_height() - 5
        self.assertEqual(tree.identify_row(y), "")
        before = dict(self.app.folder_item_states)
        with patch.object(tk.Menu, "tk_popup") as popup:
            tree.event_generate("<ButtonRelease-3>", x=40, y=y)
            popup.assert_called_once()
        self.assertEqual(self.app.file_context_menu.entrycget(0, "state"), "disabled")
        self.assertEqual(self.app.file_context_menu.entrycget(1, "state"), "disabled")
        self.assertEqual(self.app.file_context_menu.entrycget(2, "state"), "normal")
        self.assertEqual(self.app.file_context_menu.entrycget(4, "state"), "disabled")
        self.assertEqual(tree.selection(), ())
        self.assertEqual(self.app.folder_item_states, before)
        with patch.object(self.app, "open_text_toucher") as open_creator:
            self.app.file_context_menu.invoke(2)
            open_creator.assert_called_once_with(self.folder)

    def test_keyboard_without_focused_row_uses_root(self):
        self.app.widgets["folder_tree"].focus("")
        with patch.object(tk.Menu, "tk_popup") as popup:
            self.app.on_file_context_menu(SimpleNamespace(keysym="F10"))
            popup.assert_called_once()
        with patch.object(self.app, "open_text_toucher") as open_creator:
            self.app.file_context_menu.invoke(2)
            open_creator.assert_called_once_with(self.folder)

    def test_choose_parts_is_refused(self):
        with patch("src.tools.text_toucher.filedialog.askdirectory", return_value=str(self.folder / ".parts")):
            self.window.choose_folder()
        self.assertEqual(self.window.folder, self.folder)
        self.assertIn("read-only", self.window.status.get())

    def test_controls_fit_minimum_size(self):
        self.root.deiconify()
        self.window.top.geometry("650x480")
        self.root.update()
        for widget in (self.window.name_entry, self.window.extension_box, self.window.content, self.window.create_button):
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreater(widget.winfo_width(), 60)
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                 self.window.top.winfo_rootx() + self.window.top.winfo_width())


if __name__ == "__main__":
    unittest.main()
