"""Backups window: list, compare, restore, clean up; layout and keyboard reach."""

import hashlib
import json
import os
from pathlib import Path
import unittest
from tkinter import ttk
from unittest.mock import patch

from tests.support import temporary_directory, tk_root
from projectmapper.app import ProjectMapperApp
from projectmapper.core.backups import BackupStore
from projectmapper.tools.patcher import PatchError


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BackupsWindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(temporary_directory(self).name).resolve()
        self.user = Path(temporary_directory(self).name).resolve() / "user-store"
        env = patch.dict(os.environ, {"PROJECTMAPPER_USER_BACKUPS": str(self.user)})
        env.start()
        self.addCleanup(env.stop)
        self.a = self.folder / "a.txt"
        self.a.write_bytes(b"v1\n")
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root, self.folder)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.store = BackupStore.for_project(self.folder)

    def save(self, text):
        self.app.action("text.save", {"path": str(self.a), "text": text, "sha256": sha(self.a), "backup": True})

    def open(self):
        window = self.app.open_backups()
        self.addCleanup(lambda: window.top.winfo_exists() and window.top.destroy())
        return window

    def approve(self, answer=True):
        return patch("tkinter.messagebox.askyesno", return_value=answer)

    def keys(self, window):
        return list(window.generation_list.get_children())

    def select(self, window, index):
        key = self.keys(window)[index]
        window.generation_list.selection_set(key)
        window.on_generation_selected()
        return window.generations[key]

    def state(self, button):
        return str(button["state"])

    def test_lists_generations_and_shows_file_comparison(self):
        self.save("v2\n")
        self.save("v3\n")
        window = self.open()
        self.assertEqual(len(self.keys(window)), 2)
        generation = self.select(window, 0)  # newest: holds v2
        self.assertEqual(window.file_list.item("0")["text"], "a.txt")
        self.assertEqual(window.file_list.set("0", "state"), "differs")
        self.assertEqual(window.current_box.get("1.0", "end-1c"), "v3\n")
        self.assertEqual(window.backup_box.get("1.0", "end-1c"), "v2\n")
        self.assertIn("+v2", window.diff_box.get("1.0", "end-1c"))
        self.assertIn(generation["id"], window.detail.get())
        self.assertEqual(self.state(window.restore_file_button), "normal")

    def test_restore_file_with_approval(self):
        self.save("v2\n")
        window = self.open()
        self.select(window, 0)
        with self.approve(True) as asked:
            window.restore_file()
        self.assertEqual(self.a.read_bytes(), b"v1\n")
        self.assertIn("a.txt", asked.call_args.args[1])
        self.assertIn("Restored 1 file", window.status.get())
        kinds = sorted(window.generations[key]["kind"] for key in self.keys(window))
        self.assertEqual(kinds, ["backup", "pre-restore"])

    def test_denied_restore_changes_nothing(self):
        self.save("v2\n")
        window = self.open()
        self.select(window, 0)
        with self.approve(False):
            window.restore_file()
        self.assertEqual(self.a.read_bytes(), b"v2\n")
        self.assertIn("did not complete", window.status.get())
        self.assertEqual(len(self.keys(window)), 1)

    def test_restore_all_files_of_a_generation(self):
        b = self.folder / "b.txt"
        b.write_bytes(b"b1\n")
        preview = self.app.action("project_patch.validate", {"root": str(self.folder), "manifest": json.dumps(
            {"files": [{"path": n, "hunks": [{"search_block": o, "replace_block": w}]}
                       for n, o, w in (("a.txt", "v1", "v2"), ("b.txt", "b1", "b2"))]})})
        with self.approve(True):
            self.app.action("project_patch.apply", {"plan_id": preview["plan_id"], "backup": True})
        window = self.open()
        self.select(window, 0)
        with self.approve(True):
            window.restore_all()
        self.assertEqual((self.a.read_bytes(), b.read_bytes()), (b"v1\n", b"b1\n"))

    def test_corrupt_generation_is_shown_but_never_actionable(self):
        self.save("v2\n")
        (generation,) = self.store.list()
        (generation.path / generation.files[0]["stored"]).write_bytes(b"tampered\n")
        window = self.open()
        self.assertEqual(window.generation_list.item(self.keys(window)[0])["tags"], ["problem"])
        self.select(window, 0)
        self.assertIn("corrupt", window.diff_box.get("1.0", "end-1c"))
        for button in (window.restore_file_button, window.restore_all_button, window.delete_button):
            self.assertEqual(self.state(button), "disabled")
        self.assertIn("incomplete or corrupt", window.status.get())

    def test_clean_up_keeps_newest_with_approval(self):
        for text in ("v2\n", "v3\n", "v4\n"):
            self.save(text)
        window = self.open()
        window.keep.set("1")
        with self.approve(True) as asked:
            window.clean_up()
        self.assertIn("2 backup generation(s)", asked.call_args.args[1])
        self.assertIn("bytes", asked.call_args.args[1])
        self.assertEqual(len(self.keys(window)), 1)
        self.assertIn("Deleted 2 generation", window.status.get())
        with self.approve(True) as asked:
            window.clean_up()
        asked.assert_not_called()
        self.assertIn("Nothing to clean up", window.status.get())

    def test_invalid_keep_value(self):
        window = self.open()
        window.keep.set("-3")
        window.clean_up()
        self.assertIn("whole number", window.status.get())

    def test_delete_selected_removes_a_recovery_generation_explicitly(self):
        self.save("v2\n")
        recovery = self.store.create("recovery", "project_patch.apply", "op", [(self.a, b"orig\n", None)])
        window = self.open()
        key = f"project:{recovery.id}"
        self.assertEqual(window.generation_list.item(key)["tags"], ["recovery"])
        window.keep.set("0")
        with self.approve(True):
            window.clean_up()
        self.assertIn(key, self.keys(window), "keep-N clean-up never removes recovery generations")
        window.generation_list.selection_set(key)
        window.on_generation_selected()
        with self.approve(True):
            window.delete_selected()
        self.assertNotIn(key, self.keys(window))

    def test_single_instance_and_refresh_key(self):
        window = self.open()
        self.assertIs(self.app.open_backups(), window)
        self.assertEqual(self.keys(window), [])
        self.save("v2\n")
        window.top.focus_force()
        self.root.update()
        window.top.event_generate("<F5>", when="now")
        self.assertEqual(len(self.keys(window)), 1)

    def test_every_control_visible_at_minimum_size(self):
        self.save("v2\n")
        window = self.open()
        self.select(window, 0)
        window.top.geometry("760x520")
        self.root.update()
        top = window.top

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        controls = [w for w in walk(top) if w.winfo_class() in ("Button", "Radiobutton", "TSpinbox")]
        controls += [window.generation_list, window.file_list, window.views, window.status_label]
        for widget in controls:
            with self.subTest(widget=str(widget)):
                x = widget.winfo_rootx() - top.winfo_rootx()
                y = widget.winfo_rooty() - top.winfo_rooty()
                self.assertTrue(widget.winfo_ismapped())
                self.assertLessEqual(x + widget.winfo_width(), top.winfo_width())
                self.assertLessEqual(y + widget.winfo_height(), top.winfo_height())
                if widget.winfo_class() in ("Button", "Radiobutton"):
                    self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth(), "text clipped")

    def test_keep_newest_spinbox_follows_the_dark_theme(self):
        window = self.open()
        self.assertEqual(str(window.keep_box.cget("style")), "Review.TSpinbox")
        style = ttk.Style(window.top)
        colors = window.colors
        for option, expected in (("fieldbackground", colors["field_bg"]), ("background", colors["panel_alt_bg"]),
                                 ("arrowcolor", colors["text"]), ("lightcolor", colors["panel_alt_bg"])):
            with self.subTest(option=option):
                self.assertEqual(str(style.lookup("Review.TSpinbox", option)), expected)
        window.keep_box.event_generate("<<Increment>>", when="now")
        self.assertEqual(window.keep.get(), "11")

    def test_keyboard_traversal_reaches_controls(self):
        self.save("v2\n")
        window = self.open()
        self.select(window, 0)
        self.root.update()  # focus traversal only visits viewable (drawn) widgets
        chain, current = [], window.generation_list
        for _ in range(60):
            current = current.tk_focusNext()
            if current is None or current in chain:
                break
            chain.append(current)
        for widget in (window.file_list, window.restore_file_button, window.restore_all_button, window.views,
                       window.cleanup_button, window.delete_button):
            self.assertIn(widget, chain, str(widget))

    def test_project_patcher_points_to_backups_after_recovery(self):
        window = self.app.open_project_patcher(self.folder)
        self.addCleanup(window.top.destroy)
        window.session, window.results = "plan", []
        window.validated_inputs = window.inputs()
        with patch.object(self.app, "action", side_effect=PatchError(
                "Recovery required: x; originals saved in recovery backup 20260924T000000000000Z-ab (project store)")):
            window.apply()
        self.assertIn("Open Backups", window.status.get())


if __name__ == "__main__":
    unittest.main()
