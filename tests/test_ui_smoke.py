"""Smoke checks for desktop entry points that had no test (Phase 8 UI map).

Each drives the real widget or handler; dialogs, the OS file browser and the vendor
export are patched so nothing leaves the temporary fixture.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from tests.support import temporary_directory, tk_root
from projectmapper.app import ProjectMapperApp
from projectmapper.core.backups import BackupStore
from projectmapper.core.config import OUTPUT_ROOT_NAME

# Every modal the app can open. A real one would block the suite until someone clicks it.
MODALS = {"tkinter.messagebox": ("showerror", "showwarning", "showinfo", "askyesno"),
          "tkinter.filedialog": ("askopenfilename", "asksaveasfilename", "askdirectory")}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DesktopCase(unittest.TestCase):
    def setUp(self):
        base = Path(temporary_directory(self).name).resolve()
        self.folder = base / "project"
        (self.folder / "src").mkdir(parents=True)
        self.a = self.folder / "src" / "a.py"
        self.a.write_bytes(b"alpha = 1\n")
        (self.folder / "README.md").write_bytes(b"# Demo\n")
        self.user = base / "user-store"
        env = patch.dict(os.environ, {"PROJECTMAPPER_USER_BACKUPS": str(self.user)})
        env.start()
        self.addCleanup(env.stop)
        self.guard_modals()
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root, self.folder)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.scan()

    def guard_modals(self):
        """No test may open a real dialog: an unexpected one is recorded and fails the test.

        Tests that expect a dialog patch it themselves; that inner patch takes precedence."""
        unexpected = []
        for module, names in MODALS.items():
            for name in names:
                def record(*args, _name=name, **kwargs):
                    unexpected.append((_name, args[:1]))
                    return False if _name == "askyesno" else ""  # decline, or no file chosen
                guard = patch(f"{module}.{name}", side_effect=record)
                guard.start()
                self.addCleanup(guard.stop)
        self.addCleanup(lambda: self.assertEqual(unexpected, [], "a real dialog would have opened"))

    def fire_binding(self, widget, sequence):
        """Run the widget's real Tk binding for a key sequence.

        Simulated keys only reach the window with keyboard focus, and Windows will not give
        a test window focus while someone is using another application; this calls the
        registered binding through Tcl instead, so it works whatever has focus."""
        script = widget.bind(sequence)
        funcid = re.search(r"\[(\S+) %#", script).group(1)
        # The fields of a plain KeyPress (type 2); tkinter parses them into the Event.
        fields = dict.fromkeys(widget._subst_format, "0")
        fields.update({"%A": "", "%T": "2", "%K": sequence.strip("<>"), "%W": str(widget)})
        fields = [fields[name] for name in widget._subst_format]
        return widget.tk.call(funcid, *fields)

    def scan(self):
        app = self.app
        app.scan_revision = app.project_state.mark_scan_requested()
        app.action("project.scan", {"revision": app.scan_revision})
        app._apply_tree_scan(app.selected_root, app.scan_revision, app.controller.rows, app.controller.skipped)

    def pump(self, task=None, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            while not self.app.gui_queue.empty():
                self.app.gui_queue.get_nowait()()
            self.root.update()
            if task is None or task not in self.app.running_tasks:
                if task is None:
                    return
                break
            time.sleep(0.02)
        while not self.app.gui_queue.empty():
            self.app.gui_queue.get_nowait()()

    def button(self, top, text):
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        (found,) = [w for w in walk(top) if w.winfo_class() == "Button" and w.cget("text") == text]
        return found

    def log(self):
        return self.app.widgets["log_box"].get("1.0", "end-1c")

    def output(self, suffix):
        return self.folder / OUTPUT_ROOT_NAME / f"{self.folder.name}_{suffix}"


class RootNavigationTests(DesktopCase):
    def test_choose_button_sets_root_from_dialog(self):
        with patch("projectmapper.app.filedialog.askdirectory", return_value=str(self.folder / "src")):
            self.button(self.root, "Choose...").invoke()
        self.assertEqual(self.app.selected_root, self.folder / "src")
        self.assertEqual(self.app.widgets["selected_root_var"].get(), str(self.folder / "src"))

    def test_cancelled_choose_changes_nothing(self):
        with patch("projectmapper.app.filedialog.askdirectory", return_value=""):
            self.button(self.root, "Choose...").invoke()
        self.assertEqual(self.app.selected_root, self.folder)

    def test_up_button_goes_to_parent(self):
        self.app.navigate_tree_to_path(self.folder / "src")
        self.button(self.root, "↑").invoke()
        self.assertEqual(self.app.selected_root, self.folder)

    def test_path_entry_return_sets_root_and_rejects_invalid(self):
        entry = self.app.widgets["project_path_entry"]
        self.app.widgets["selected_root_var"].set(str(self.folder / "src"))
        self.fire_binding(entry, "<Return>")
        self.assertEqual(self.app.selected_root, self.folder / "src")
        self.app.widgets["selected_root_var"].set(str(self.folder / "missing"))
        with patch("projectmapper.app.messagebox.showerror") as shown:
            self.fire_binding(entry, "<Return>")
        shown.assert_called_once()
        self.assertEqual(shown.call_args.args[0], "Invalid Project Root")
        self.assertEqual(self.app.selected_root, self.folder / "src")


class SnapshotButtonTests(DesktopCase):
    def test_compile_and_every_export_button(self):
        self.button(self.root, "Compile Snapshot").invoke()
        self.pump("compile_snapshot")
        self.assertIn("Snapshot compiled", self.log())
        for text, suffix, expected in (("Export Tree MD", "project_tree.md", "a.py"),
                                       ("Export Filedump MD", "project_filedump.md", "alpha = 1"),
                                       ("Export Tree+Dump MD", "project_tree_and_filedump.md", "README.md")):
            with self.subTest(button=text):
                self.button(self.root, text).invoke()
                self.pump("export_snapshot")
                self.assertIn(expected, self.output(suffix).read_text(encoding="utf-8"))

    def test_tree_in_filedump_checkbox_adds_the_tree(self):
        self.button(self.root, "Compile Snapshot").invoke()
        self.pump("compile_snapshot")
        self.button(self.root, "Export Filedump MD").invoke()
        self.pump("export_snapshot")
        without = self.output("project_filedump.md").read_text(encoding="utf-8")
        self.app.widgets["include_tree_in_filedump"].set(True)
        self.button(self.root, "Export Filedump MD").invoke()
        self.pump("export_snapshot")
        with_tree = self.output("project_filedump.md").read_text(encoding="utf-8")
        self.assertGreater(len(with_tree), len(without))

    def test_export_before_compile_is_refused_with_a_label(self):
        self.button(self.root, "Export Tree MD").invoke()
        self.pump("export_snapshot")
        self.assertIn("The snapshot is out of date", self.log())
        self.assertFalse(self.output("project_tree.md").exists())


class MainWindowButtonTests(DesktopCase):
    def test_diagnostics_button_reports(self):
        with patch("projectmapper.app.messagebox.showinfo") as info, \
                patch("projectmapper.app.messagebox.showwarning") as warning:
            self.button(self.root, "Diagnostics").invoke()
        self.assertEqual(info.call_count + warning.call_count, 1)
        self.assertIn("ProjectMapper diagnostics", self.log())

    def test_open_output_folder_button_opens_the_resolved_folder(self):
        opened = []
        with patch("projectmapper.app.platform.system", return_value="Windows"), \
                patch("projectmapper.app.os.startfile", create=True, side_effect=opened.append):
            self.button(self.root, "Open Output Folder").invoke()
        self.assertEqual([Path(p) for p in opened], [self.folder / OUTPUT_ROOT_NAME])
        self.assertTrue((self.folder / OUTPUT_ROOT_NAME).is_dir())

    def test_vendor_export_button_runs_the_action(self):
        calls = []

        def fake_export(**kwargs):
            calls.append(kwargs)
            return {"export_dir": "X", "included_count": 1, "skipped_count": 0}
        with patch("projectmapper.core.exports.create_vendor_export", side_effect=fake_export):
            self.button(self.root, "Export Vendor App").invoke()
            self.pump("vendor_export")
        self.assertEqual(len(calls), 1)
        self.assertIn("Vendor export ready", self.log())


class ToolWindowEntryTests(DesktopCase):
    def test_patcher_reload_and_load_patch_json(self):
        window = self.app.open_tokenizing_patcher(self.a)
        self.addCleanup(window.top.destroy)
        self.a.write_bytes(b"alpha = 99\n")
        self.button(window.top, "Reload Target").invoke()
        self.assertEqual(window.session.source, "alpha = 99\n")
        patch_file = self.folder / "p.json"
        patch_file.write_text(json.dumps({"hunks": [{"search_block": "alpha = 99", "replace_block": "x"}]}),
                              encoding="utf-8")
        with patch("projectmapper.tools.patcher_ui.filedialog.askopenfilename", return_value=str(patch_file)):
            self.button(window.top, "Load Patch JSON").invoke()
        self.assertIn("alpha = 99", window.patch_box.get("1.0", "end-1c"))
        self.assertTrue(window.validate())

    def test_patcher_keep_backup_checkbox_creates_a_generation(self):
        window = self.app.open_tokenizing_patcher(self.a)
        self.addCleanup(window.top.destroy)
        window.patch_box.delete("1.0", "end")
        window.patch_box.insert("1.0", json.dumps({"hunks": [{"search_block": "alpha = 1", "replace_block": "alpha = 2"}]}))
        self.assertTrue(window.validate())
        window.apply()
        window.backup.set(True)
        window.save()
        (generation,) = BackupStore.for_project(self.folder).list()
        self.assertEqual(BackupStore.for_project(self.folder).read(generation.id, "src/a.py"), b"alpha = 1\n")

    def test_project_patcher_load_json_and_keep_backups(self):
        window = self.app.open_project_patcher(self.folder)
        self.addCleanup(window.top.destroy)
        manifest = self.folder / "m.json"
        manifest.write_text(json.dumps({"files": [{"path": "src/a.py", "hunks": [
            {"search_block": "alpha = 1", "replace_block": "alpha = 3"}]}]}), encoding="utf-8")
        with patch("projectmapper.tools.project_patcher_ui.filedialog.askopenfilename", return_value=str(manifest)):
            self.button(window.top, "Load Patch JSON").invoke()
        self.assertTrue(window.validate())
        window.backup.set(True)
        with patch("tkinter.messagebox.askyesno", return_value=True):
            window.apply()
        self.assertEqual(self.a.read_bytes(), b"alpha = 3\n")
        self.assertEqual(len(BackupStore.for_project(self.folder).list()), 1)

    def test_editor_open_and_save_as(self):
        editor = self.app.open_text_editor(self.a)
        self.addCleanup(editor.top.destroy)
        readme = self.folder / "README.md"
        with patch("projectmapper.tools.text_editor.filedialog.askopenfilename", return_value=str(readme)):
            self.button(editor.top, "Open…").invoke()
        self.assertEqual(editor.session.path, readme)
        copy = self.folder / "copy.md"
        with patch("projectmapper.tools.text_editor.filedialog.asksaveasfilename", return_value=str(copy)):
            self.button(editor.top, "Save As…").invoke()
        self.assertEqual(copy.read_bytes(), b"# Demo\n")
        self.assertEqual(editor.session.path, copy)

    def test_backups_store_selector_drives_clean_up_scope(self):
        outside = self.user.parent / "far.txt"
        outside.write_bytes(b"far\n")
        for text in ("farther\n", "farthest\n"):
            self.app.action("text.save", {"path": str(outside), "text": text, "sha256": sha(outside), "backup": True})
        window = self.app.open_backups()
        self.addCleanup(window.top.destroy)
        window.cleanup_scope.set("user")
        window.keep.set("1")
        with patch("tkinter.messagebox.askyesno", return_value=True) as asked:
            window.clean_up()
        self.assertIn("user store", asked.call_args.args[1])
        self.assertEqual(len(BackupStore.for_user().list()), 1)


class EditorBackupTests(DesktopCase):
    """Decision E2: the text editor offers Keep backup for Save and Save As overwrites."""

    def editor(self):
        editor = self.app.open_text_editor(self.a)
        self.addCleanup(editor.top.destroy)
        return editor

    def test_save_with_keep_backup_creates_a_generation(self):
        editor = self.editor()
        editor.editor.insert("end", "beta = 2\n")
        editor.backup.set(True)
        editor.save()
        (generation,) = BackupStore.for_project(self.folder).list()
        self.assertEqual(BackupStore.for_project(self.folder).read(generation.id, "src/a.py"), b"alpha = 1\n")
        self.assertEqual(generation.action, "text.save")

    def test_save_without_keep_backup_creates_none(self):
        editor = self.editor()
        editor.editor.insert("end", "beta = 2\n")
        editor.save()
        self.assertEqual(BackupStore.for_project(self.folder).list(), [])

    def test_save_as_overwrite_with_keep_backup_keeps_the_overwritten_bytes(self):
        editor = self.editor()
        readme = self.folder / "README.md"
        editor.backup.set(True)
        with patch("projectmapper.tools.text_editor.filedialog.asksaveasfilename", return_value=str(readme)), \
                patch("tkinter.messagebox.askyesno", return_value=True):
            editor.save_as()
        self.assertEqual(readme.read_bytes(), b"alpha = 1\n")
        (generation,) = BackupStore.for_project(self.folder).list()
        self.assertEqual(BackupStore.for_project(self.folder).read(generation.id, "README.md"), b"# Demo\n")


class MainWindowLayoutTests(DesktopCase):
    """Step 8.2: the main window's minimum size is measured and nothing clips at it."""

    def controls(self):
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        return [w for w in walk(self.root) if w.winfo_class() in ("Button", "Checkbutton", "Entry")]

    def show(self, width, height):
        self.root.deiconify()
        self.addCleanup(self.root.withdraw)
        self.root.geometry(f"{width}x{height}")
        self.root.update()

    def test_every_control_fits_at_the_minimum_size(self):
        width, height = self.root.minsize()
        self.assertLessEqual(width, 800, "the main window should fit an 800 px wide screen")
        self.show(width, height)
        self.assertEqual((self.root.winfo_width(), self.root.winfo_height()), (width, height))
        for widget in self.controls():
            with self.subTest(widget=widget.cget("text") if widget.winfo_class() != "Entry" else str(widget)):
                x = widget.winfo_rootx() - self.root.winfo_rootx()
                y = widget.winfo_rooty() - self.root.winfo_rooty()
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreaterEqual(min(x, y), 0)
                self.assertLessEqual(x + widget.winfo_width(), width)
                self.assertLessEqual(y + widget.winfo_height(), height)
                if widget.winfo_class() != "Entry":
                    self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth(), "text clipped")
        tree, log = self.app.widgets["folder_tree"], self.app.widgets["log_box"]
        rows = tree.winfo_height() // 20
        self.assertGreaterEqual(rows, 4, "tree too short to use")
        self.assertGreaterEqual(log.winfo_height(), 3 * 15, "log too short to read")
        self.assertTrue(self.app.widgets["status_bar"].winfo_ismapped())

    def test_the_tree_name_column_takes_extra_width(self):
        self.show(1200, 850)
        tree = self.app.widgets["folder_tree"]
        self.assertGreater(int(tree.column("#0", "width")), 700)


class EditorLayoutTests(DesktopCase):
    """Step 8.5 layout probe: Keep backup (8.2) was squeezed at the editor's old 700 px minimum."""

    def test_toolbar_fits_at_the_minimum_size(self):
        editor = self.app.open_text_editor(self.a)
        self.addCleanup(editor.top.destroy)
        width, height = editor.top.minsize()
        editor.top.geometry(f"{width}x{height}")
        self.root.update()
        right = editor.top.winfo_rootx() + editor.top.winfo_width()
        for widget in editor.toolbar.winfo_children():
            with self.subTest(control=widget.cget("text")):
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth(), "text clipped")
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right)


class RemainingEntryPointTests(DesktopCase):
    """UI-map gaps found in step 8.2; each drives the real binding or button."""

    def test_progress_cancel_button_stops_the_task_and_closes(self):
        started = []

        def work():
            started.append(True)
            self.app.stop_event.wait(10)
        self.app.run_threaded_action(work, "probe", use_popup=True)
        popup = self.app.current_progress_popup
        deadline = time.monotonic() + 5
        while not started and time.monotonic() < deadline:
            time.sleep(0.01)
        self.button(popup.top, "CANCEL OPERATION").invoke()
        began = time.monotonic()
        self.pump("probe", seconds=5)
        self.assertLess(time.monotonic() - began, 5)
        self.assertNotIn("probe", self.app.running_tasks)
        self.assertIn("Stop signal sent", self.log())
        self.assertIsNone(self.app.current_progress_popup)
        self.assertFalse(popup.top.winfo_exists())

    def test_tree_navigation_columns(self):
        tree = self.app.widgets["folder_tree"]
        src = str(self.folder / "src")
        for column, expected in (("#1", self.folder), ("#2", self.folder / "src"), ("#0", None)):
            with self.subTest(column=column),                     patch.object(tree, "identify_row", return_value=src),                     patch.object(tree, "identify_column", return_value=column),                     patch.object(tree, "identify", return_value="text"),                     patch.object(self.app, "navigate_tree_to_path") as navigate,                     patch.object(self.app, "toggle_tree_item") as toggle:
                self.app.on_tree_item_click(SimpleNamespace(widget=tree, x=5, y=5))
            if expected is None:
                navigate.assert_not_called()
                toggle.assert_called_once_with(src)
            else:
                navigate.assert_called_once_with(expected)
                toggle.assert_not_called()

    def test_escape_closes_the_exclusions_window(self):
        self.button(self.root, "Exclusions").invoke()
        top = self.app.exclusions_popup.top
        self.fire_binding(top, "<Escape>")
        self.assertFalse(top.winfo_exists())

    def test_history_refresh_key(self):
        window = self.app.open_history()
        self.addCleanup(lambda: window.top.winfo_exists() and window.top.destroy())
        with patch.object(window, "refresh") as refreshed:
            self.assertEqual(self.fire_binding(window.top, "<F5>"), "break")
        refreshed.assert_called_once()

    def test_editor_find_next_highlights_the_match(self):
        editor = self.app.open_text_editor(self.a)
        self.addCleanup(editor.top.destroy)
        self.button(editor.top, "Find / Replace").invoke()
        (entry, _replace) = [w for w in editor.find_window.winfo_children() if w.winfo_class() == "Entry"]
        entry.insert(0, "= 1")
        self.button(editor.find_window, "Find Next").invoke()
        self.assertEqual(editor.editor.tag_ranges("found")[0].string, "1.6")
        self.assertIs(self.app.action("text.find", {"text": "x", "query": "y"})["index"], -1)

    def test_patcher_copy_schema_button(self):
        window = self.app.open_tokenizing_patcher(self.a)
        self.addCleanup(window.top.destroy)
        self.button(window.top, "Copy Schema").invoke()
        self.assertIn("hunks", json.loads(window.top.clipboard_get()))

    def test_project_patcher_force_indentation_reaches_validation(self):
        window = self.app.open_project_patcher(self.folder)
        self.addCleanup(window.top.destroy)
        window.manifest_box.delete("1.0", "end")
        window.manifest_box.insert("1.0", json.dumps({"files": [{"path": "src/a.py", "hunks": [
            {"search_block": "alpha = 1", "replace_block": "alpha = 3"}]}]}))
        seen = []
        real = self.app.action

        def spy(name, payload=None, **kwargs):
            if name == "project_patch.validate":
                seen.append(payload["force_indent"])
            return real(name, payload, **kwargs)
        with patch.object(self.app, "action", side_effect=spy):
            for value in (False, True):
                window.force_indent.set(value)
                window.validate()
        self.assertEqual(seen, [False, True])

    def test_editor_close_asks_before_discarding(self):
        editor = self.app.open_text_editor(self.a)
        editor.editor.insert("end", "edit\n")
        self.root.update()  # <<Modified>> is delivered by the event loop
        self.assertTrue(editor.dirty)
        with patch("projectmapper.tools.text_editor.messagebox.askyesno", return_value=False) as asked:
            editor.close()
        asked.assert_called_once()
        self.assertTrue(editor.top.winfo_exists())
        with patch("projectmapper.tools.text_editor.messagebox.askyesno", return_value=True):
            editor.close()
        self.assertFalse(editor.top.winfo_exists())


def close_box(top):
    """Press the window manager's close box: run the WM_DELETE_WINDOW handler."""
    top.tk.call(top.protocol("WM_DELETE_WINDOW"))


class ClosingAndScrollingTests(DesktopCase):
    """UI-map gaps found in the 8.2 review: close boxes and the exclusion list's wheel."""

    def assert_close_box_guards(self, window, dirty, module):
        dirty()
        self.root.update()  # <<Modified>> is delivered by the event loop
        with patch(f"projectmapper.tools.{module}.messagebox.askyesno", return_value=False) as asked:
            close_box(window.top)
        asked.assert_called_once()
        self.assertTrue(window.top.winfo_exists())
        with patch(f"projectmapper.tools.{module}.messagebox.askyesno", return_value=True):
            close_box(window.top)
        self.assertFalse(window.top.winfo_exists())

    def test_patcher_close_box_asks_before_discarding_a_result(self):
        window = self.app.open_tokenizing_patcher(self.a)
        window.patch_box.delete("1.0", "end")
        window.patch_box.insert("1.0", json.dumps({"hunks": [{"search_block": "alpha = 1", "replace_block": "a = 2"}]}))
        self.root.update()  # deliver the edit's <<Modified>> now, as a user's typing would be
        self.assertTrue(window.validate())
        self.assert_close_box_guards(window, window.apply, "patcher_ui")

    def test_project_patcher_close_box_asks_before_discarding_a_manifest(self):
        window = self.app.open_project_patcher(self.folder)
        self.assert_close_box_guards(window, lambda: window.manifest_box.insert("1.0", "{}"), "project_patcher_ui")

    def test_new_file_close_box_asks_before_discarding_a_name(self):
        window = self.app.open_text_toucher(self.folder)
        self.assert_close_box_guards(window, lambda: window.name.set("draft"), "text_toucher")

    def test_clean_windows_close_without_asking(self):
        with patch("tkinter.messagebox.askyesno") as asked:
            for window in (self.app.open_tokenizing_patcher(self.a), self.app.open_project_patcher(self.folder),
                           self.app.open_text_toucher(self.folder), self.app.open_text_editor(self.a)):
                with self.subTest(window=window.top.title()):
                    close_box(window.top)
                    self.assertFalse(window.top.winfo_exists())
        asked.assert_not_called()

    def test_history_close_box_stops_live_updates(self):
        window = self.app.open_history()
        with patch.object(window, "unsubscribe", wraps=window.unsubscribe) as unsubscribed:
            close_box(window.top)
        unsubscribed.assert_called()
        self.assertFalse(window.top.winfo_exists())
        self.app.action("history.query")  # a new event reaches no destroyed window
        self.root.update()

    def test_exclusions_mouse_wheel_scrolls_the_rule_list(self):
        self.root.deiconify()
        self.addCleanup(self.root.withdraw)
        for index in range(40):
            self.app.action("exclusions.update", {"operation": "add", "pattern": f"*.probe{index}"})
        self.button(self.root, "Exclusions").invoke()
        popup = self.app.exclusions_popup
        popup.top.geometry("700x420")
        self.root.update()
        canvas = popup.canvas
        self.assertLess(canvas.yview()[1], 1.0, "the list must overflow for this check")
        popup.top.event_generate("<MouseWheel>", delta=-120, when="now")
        self.assertGreater(canvas.yview()[0], 0.0)
        popup.top.event_generate("<MouseWheel>", delta=120, when="now")
        self.assertEqual(canvas.yview()[0], 0.0)
        # X11 reports the wheel as buttons 4 and 5.
        popup.top.event_generate("<Button-5>", when="now")
        self.assertGreater(canvas.yview()[0], 0.0)
        popup.top.event_generate("<Button-4>", when="now")
        self.assertEqual(canvas.yview()[0], 0.0)


class MainWindowCloseTests(unittest.TestCase):
    """Closing the main window shuts the action layer down (the root's <Destroy> binding)."""

    def test_destroying_the_main_window_closes_the_controller(self):
        folder = Path(temporary_directory(self).name).resolve()
        root = tk.Tk()
        root.withdraw()
        try:
            app = ProjectMapperApp(root, folder)
            # Pending timers of a destroyed root would fire in a later test's event loop.
            for timer in root.tk.call("after", "info"):
                root.after_cancel(timer)
            with patch.object(app.controller, "close", wraps=app.controller.close) as closed:
                root.destroy()
            closed.assert_called_once()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass  # already destroyed by the test


if __name__ == "__main__":
    unittest.main()
