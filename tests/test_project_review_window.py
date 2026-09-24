"""Project Patcher review window: file list, per-file views, navigation and approval summary."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.support import temporary_directory, tk_root
from projectmapper.app import ProjectMapperApp
from projectmapper.application.controller import create_application
from projectmapper.tools.project_patcher import EXAMPLE_MANIFEST
from projectmapper.tools.project_patcher_ui import SKELETON

ORIGINAL = "".join(f"line {i}\n" for i in range(30))


def hunk(search, replace):
    return {"search_block": search, "replace_block": replace}


class ReviewWindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(temporary_directory(self).name).resolve()
        (self.folder / "a.py").write_bytes(ORIGINAL.encode())
        (self.folder / "b.py").write_bytes(b"same\n")
        (self.folder / "c.py").write_bytes(b"gamma\n")
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root, self.folder)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.window = self.app.open_project_patcher(self.folder)
        self.addCleanup(lambda: self.window.top.winfo_exists() and self.window.top.destroy())

    def set_manifest(self, *entries):
        self.window.manifest_box.delete("1.0", "end")
        self.window.manifest_box.insert("1.0", json.dumps({"version": 1, "files": list(entries)}))
        self.window.manifest_box.edit_modified(False)

    def valid_manifest(self):
        self.set_manifest({"path": "a.py", "hunks": [hunk("line 2", "LINE 2"), hunk("line 25", "LINE 25")]},
                          {"path": "b.py", "hunks": [hunk("same", "same")]})
        self.assertTrue(self.window.validate())

    def press(self, widget, sequence):
        # Tk delivers generated key events to the focused widget; its bindtags include the window.
        widget.focus_force()
        self.root.update()
        widget.event_generate(sequence, when="now")
        self.root.update()

    def cells(self, iid, *columns):
        return [self.window.file_list.set(iid, column) for column in columns]

    def tagged_lines(self, box):
        ranges = box.tag_ranges("current_hunk")
        return int(str(ranges[0]).split(".")[0]), int(str(ranges[1]).split(".")[0])

    def state(self, button):
        return str(button["state"])

    def test_new_window_starts_with_valid_skeleton(self):
        self.assertEqual(self.window.manifest_box.get("1.0", "end-1c"), SKELETON)
        self.assertEqual(json.loads(SKELETON), {"version": 1, "files": []})
        self.assertEqual(self.window.position.get(), "No review yet")

    def test_review_lists_files_with_status_and_counts(self):
        self.valid_manifest()
        listed = [self.window.file_list.item(iid)["text"] for iid in self.window.file_list.get_children()]
        self.assertEqual(listed, ["a.py", "b.py"])
        self.assertEqual(self.cells("0", "status", "add", "del", "hunks"), ["changed", "+2", "-2", "2"])
        self.assertEqual(self.cells("1", "status")[0], "no change")
        self.assertEqual(self.window.file_list.selection(), ("0",))
        self.assertEqual(self.window.position.get(), "File 1/2 · Hunk 1/2")
        self.assertEqual(self.window.source_box.get("1.0", "end-1c"), ORIGINAL)
        self.assertIn("LINE 25", self.window.result_box.get("1.0", "end-1c"))
        self.assertIn("-line 2", self.window.diff_box.get("1.0", "end-1c"))

    def test_hunk_navigation_highlights_every_view_and_respects_bounds(self):
        self.valid_manifest()
        window = self.window
        self.assertEqual(self.state(window.prev_hunk_button), "disabled")
        self.assertEqual(self.tagged_lines(window.source_box), (1, 7))  # lines 0-5 incl. context
        self.press(window.file_list, "<F8>")
        self.assertEqual(window.position.get(), "File 1/2 · Hunk 2/2")
        self.assertEqual(self.tagged_lines(window.result_box), (23, 30))
        first = self.tagged_lines(window.diff_box)[0]
        self.assertTrue(window.diff_box.get(f"{first}.0", f"{first}.end").startswith("@@"))
        self.assertEqual(self.state(window.next_hunk_button), "disabled")
        window.step_hunk(1)
        self.assertEqual(window.hunk_index, 1)
        self.press(window.file_list, "<Shift-F8>")
        self.assertEqual(window.hunk_index, 0)

    def test_file_navigation_by_keyboard_and_selection(self):
        self.valid_manifest()
        window = self.window
        self.assertEqual(self.state(window.prev_file_button), "disabled")
        self.press(window.file_list, "<Alt-Down>")
        self.assertEqual(window.file_index, 1)
        self.assertEqual(window.file_list.selection(), ("1",))
        self.assertEqual(window.position.get(), "File 2/2 · no line changes")
        self.assertIn("No differences", window.diff_box.get("1.0", "end-1c"))
        self.assertEqual(self.state(window.next_file_button), "disabled")
        window.step_file(1)
        self.assertEqual(window.file_index, 1)
        window.file_list.selection_set("0")
        self.root.update()
        self.assertEqual(window.file_index, 0)
        self.press(window.file_list, "<Alt-Up>")
        self.assertEqual(window.file_index, 0)

    def test_invalid_manifest_shows_errors_and_blocks_apply(self):
        self.set_manifest({"path": "a.py", "hunks": [hunk("line 2", "LINE 2")]},
                          {"path": "c.py", "hunks": [hunk("missing", "x")]},
                          {"path": "b.py", "hunks": [hunk("same", "same")]})
        self.assertFalse(self.window.validate())
        self.assertIn("1 of 3", self.window.status.get())
        self.assertEqual(self.window.file_list.item("1")["tags"], ["error"])
        self.assertEqual(self.cells("1", "add", "del"), ["", ""])
        self.assertEqual(self.window.file_index, 1, "the first error is shown")
        self.assertIn("c.py: Hunk 1", self.window.diff_box.get("1.0", "end-1c"))
        self.assertEqual(self.window.position.get(), "File 2/3 · validation error")
        self.assertEqual(self.state(self.window.apply_button), "disabled")
        with patch("projectmapper.tools.project_patcher_ui.messagebox.askyesno") as approve:
            self.window.apply()
        approve.assert_not_called()

    def test_edit_after_review_clears_it(self):
        self.valid_manifest()
        self.window.manifest_box.insert("end", " ")
        self.root.update()
        self.assertEqual(self.window.file_list.get_children(), ())
        self.assertEqual(self.window.position.get(), "No review yet")
        self.assertEqual(self.window.source_box.get("1.0", "end-1c"), "")
        self.assertEqual(self.state(self.window.apply_button), "disabled")

    def test_ctrl_enter_in_manifest_validates_without_inserting_newline(self):
        self.set_manifest({"path": "b.py", "hunks": [hunk("same", "same")]})
        before = self.window.manifest_box.get("1.0", "end-1c")
        self.press(self.window.manifest_box, "<Control-Return>")
        self.assertEqual(self.window.manifest_box.get("1.0", "end-1c"), before)
        self.assertIsNotNone(self.window.session)

    def test_add_file_on_skeleton_or_untouched_example_validates(self):
        for starting in (SKELETON, json.dumps(EXAMPLE_MANIFEST, indent=2)):
            with self.subTest(starting=starting[:20]):
                self.window.manifest_box.delete("1.0", "end")
                self.window.manifest_box.insert("1.0", starting)
                with patch("projectmapper.tools.project_patcher_ui.filedialog.askopenfilename",
                           return_value=str(self.folder / "c.py")):
                    self.window.add_file()
                manifest = json.loads(self.window.manifest_box.get("1.0", "end-1c"))
                self.assertEqual([item["path"] for item in manifest["files"]], ["c.py"])
                self.assertTrue(self.window.validate(), self.window.status.get())

    def test_disabled_apply_is_visibly_distinct_and_scrollbars_are_themed(self):
        window, theme = self.window, self.app.theme
        self.assertEqual(window.apply_button.cget("bg"), theme["panel_alt_bg"])
        self.valid_manifest()
        self.assertEqual(self.state(window.apply_button), "normal")
        self.assertEqual(window.apply_button.cget("bg"), theme["accent"])
        window.manifest_box.insert("end", " ")
        self.root.update()
        self.assertEqual(window.apply_button.cget("bg"), theme["panel_alt_bg"])
        scrollbars = [child for child in window.diff_box.frame.winfo_children() if child.winfo_class() == "TScrollbar"]
        self.assertEqual([str(bar.cget("style")) for bar in scrollbars], ["Review.Vertical.TScrollbar"])

    def test_copy_schema_copies_the_full_example(self):
        self.window.copy_schema()
        self.assertEqual(json.loads(self.window.top.clipboard_get()), EXAMPLE_MANIFEST)

    def test_approval_summary_lists_per_file_counts(self):
        self.valid_manifest()
        # The desktop adapter imports this same tkinter.messagebox module object.
        with patch("projectmapper.tools.project_patcher_ui.messagebox.askyesno", return_value=False) as approve:
            self.window.apply()
        message = approve.call_args.args[1]
        self.assertIn("2 file(s) (+2 / -2)", message)
        self.assertIn("+2 / -2   a.py", message)
        self.assertIn("+0 / -0   b.py", message)
        self.assertEqual((self.folder / "a.py").read_bytes(), ORIGINAL.encode())


class ReviewLayoutTests(unittest.TestCase):
    """Measured geometry at the minimum size with long paths; keyboard reachability."""

    def setUp(self):
        base = Path(temporary_directory(self).name).resolve()
        self.folder = base / ("very_long_project_folder_name_" * 2) / ("nested_directory_level_" * 2)
        self.relative = "src/" + "deeply_nested_module_" * 3 + "/file_with_a_long_name.py"
        (self.folder / self.relative).parent.mkdir(parents=True)
        (self.folder / self.relative).write_bytes(ORIGINAL.encode())
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root, self.folder)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.window = self.app.open_project_patcher(self.folder)
        self.addCleanup(lambda: self.window.top.winfo_exists() and self.window.top.destroy())
        self.window.manifest_box.delete("1.0", "end")
        self.window.manifest_box.insert("1.0", json.dumps({"files": [{"path": self.relative, "hunks": [
            hunk("line 2", "LINE 2"), hunk("line 25", "LINE 25")]}]}))
        self.window.manifest_box.edit_modified(False)
        self.root.update()
        self.assertTrue(self.window.validate())

    def test_every_control_visible_at_minimum_size(self):
        window = self.window
        window.top.geometry("720x500")
        self.root.update()
        top = window.top
        width, height = top.winfo_width(), top.winfo_height()
        controls = [window.validate_button, window.link_button, window.apply_button, window.prev_file_button,
                    window.next_file_button, window.prev_hunk_button, window.next_hunk_button,
                    window.position_label, window.status_label, window.file_list, window.views, window.manifest_box]

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        controls += [w for w in walk(top) if w.winfo_class() in ("Button", "Checkbutton")]
        for widget in controls:
            with self.subTest(widget=str(widget)):
                x, y = widget.winfo_rootx() - top.winfo_rootx(), widget.winfo_rooty() - top.winfo_rooty()
                self.assertTrue(widget.winfo_ismapped())
                self.assertGreater(widget.winfo_width(), 1)
                self.assertLessEqual(x + widget.winfo_width(), width)
                self.assertLessEqual(y + widget.winfo_height(), height)
                if widget.winfo_class() in ("Button", "Checkbutton"):
                    self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth(), "text clipped")

    def test_keyboard_traversal_reaches_every_enabled_control(self):
        window, chain, current = self.window, [], self.window.manifest_box
        for _ in range(60):
            current = current.tk_focusNext()
            if current is None or current in chain:
                break
            chain.append(current)
        expected = [window.validate_button, window.link_button, window.apply_button, window.file_list,
                    window.next_hunk_button, window.views]
        expected += [w for w in window.top.winfo_children()[0].winfo_children() if w.winfo_class() == "Button"]
        for widget in expected:
            self.assertIn(widget, chain, str(widget))
        self.assertIn(window.manifest_box, chain + [window.manifest_box])


class AddEntryTemplateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.app, _ = create_application(self.root)
        self.addCleanup(self.app.close)

    def add(self, name, data):
        (self.root / name).write_bytes(data)
        result = self.app.execute("project_patch.add_entry", {
            "root": str(self.root), "path": str(self.root / name), "manifest": SKELETON})
        return json.loads(result.data["text"])["files"][0]["hunks"][0]["search_block"]

    def test_template_uses_first_uniquely_matching_line(self):
        self.assertEqual(self.add("dup.py", b"}\n\n    }\ndef unique():\n}\n"), "def unique():")

    def test_template_falls_back_to_whole_file_without_a_unique_line(self):
        self.assertEqual(self.add("same.py", b"x\n  x\n"), "x\n  x\n")


if __name__ == "__main__":
    unittest.main()
