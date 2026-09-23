import time
import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.support import tk_root, temporary_directory
from src.app import ProjectMapperApp
from src.core.snapshots import compile_snapshot
from src.core.tree import scan_project_tree


class LazyProjectionTests(unittest.TestCase):
    def setUp(self):
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.tree = self.app.widgets["folder_tree"]
        self.base = Path("fixture").resolve()

    def rows(self, count=3):
        def row(path, parent, directory):
            return dict(path=path, parent=parent, entry_type="dir" if directory else "file",
                        name=path.name, size_bytes=0)
        return [row(self.base, None, True), row(self.base / "folder", self.base, True)] + [
            row(self.base / "folder" / str(i), self.base / "folder", False) for i in range(count)]

    def drain(self):
        end = time.monotonic() + 5
        while self.app.tree_projection.timer is not None and time.monotonic() < end:
            self.root.update()
        self.assertIsNone(self.app.tree_projection.timer)

    def expand(self, path):
        self.tree.focus(str(path))
        self.tree.item(str(path), open=True)
        self.app.on_tree_open(SimpleNamespace(widget=self.tree))

    def test_unrendered_selection_and_refresh_navigation(self):
        rows = self.rows()
        self.app.controller.tree_model.replace(rows)
        self.app.populate_tree(rows)
        self.assertFalse(self.tree.exists(str(self.base / "folder" / "0")))
        self.app.controller.tree_model.set_selection(self.base, "unchecked")
        self.app.controller.tree_model.set_selection(self.base / "folder" / "1", "checked")
        before = dict(self.app.folder_item_states)
        self.expand(self.base / "folder")
        self.drain()
        target = str(self.base / "folder" / "1")
        self.tree.focus(target)
        self.tree.selection_set(target)
        self.app.populate_tree(rows)
        self.drain()
        self.assertEqual(self.tree.focus(), target)
        self.assertEqual(self.tree.selection(), (target,))
        self.assertEqual(before, self.app.folder_item_states)
        self.assertTrue(self.tree.item(str(self.base / "folder"), "open"))

    def test_wide_expansion_yields_and_old_batches_cannot_cross_roots(self):
        self.app.populate_tree(self.rows(3000))
        self.expand(self.base / "folder")
        heartbeat = []
        self.root.after(0, lambda: heartbeat.append(len(self.tree.get_children(str(self.base / "folder")))))
        self.root.update()
        self.assertLess(heartbeat[0], 3000)
        old_epoch = self.app.tree_projection.epoch
        self.base = self.base / "other"
        self.app.populate_tree(self.rows())
        self.app.tree_projection._batch(old_epoch)
        self.drain()
        self.assertEqual(self.tree.get_children(), (str(self.base),))

    def test_expand_indicator_does_not_toggle_capture(self):
        with patch.object(self.tree, "identify_row", return_value=str(self.base)), \
             patch.object(self.tree, "identify_column", return_value="#0"), \
             patch.object(self.tree, "identify", return_value="Treeitem.indicator"), \
             patch.object(self.app, "toggle_tree_item") as toggle:
            self.app.on_tree_item_click(SimpleNamespace(widget=self.tree, x=5, y=5))
        toggle.assert_not_called()

    def test_collapse_before_first_batch_remains_expandable(self):
        self.app.populate_tree(self.rows(300))
        folder = str(self.base / "folder")
        self.expand(folder)
        self.tree.item(folder, open=False)
        self.drain()
        self.assertEqual(len(self.tree.get_children(folder)), 1)
        self.expand(folder)
        self.drain()
        self.assertEqual(len(self.tree.get_children(folder)), 300)

    def test_root_navigation_clears_pending_old_projection_immediately(self):
        fixture = temporary_directory(self)
        self.app.populate_tree(self.rows(3000))
        self.expand(self.base / "folder")
        with patch.object(self.app, "request_rescan_tree"):
            self.app.navigate_tree_to_path(Path(fixture.name))
        self.assertEqual(self.tree.get_children(), ())
        self.assertIsNone(self.app.tree_projection.timer)

    def test_snapshot_contents_equal_before_and_after_expansion(self):
        fixture = temporary_directory(self)
        self.base = Path(fixture.name) / "project"
        folder = self.base / "folder"
        folder.mkdir(parents=True)
        (folder / "included.txt").write_text("included")
        (folder / "excluded.txt").write_text("excluded")
        policy = self.app.exclusion_policy
        rows, skipped = scan_project_tree(self.base, policy)
        model = self.app.controller.tree_model
        model.replace(rows)
        model.set_selection(self.base, "unchecked")
        model.set_selection(folder / "included.txt", "checked")
        self.app.populate_tree(rows)
        self.assertFalse(self.tree.exists(str(folder / "included.txt")))

        def capture(name):
            snapshot = compile_snapshot(self.base, Path(fixture.name) / name, rows,
                                        model.selection, policy, skipped)
            with closing(sqlite3.connect(snapshot)) as database:
                return database.execute("SELECT relative_path, content FROM project_files ORDER BY relative_path").fetchall()
        before = capture("before")
        self.expand(folder)
        self.drain()
        self.assertEqual(before, capture("after"))
        self.assertEqual(before, [("folder/included.txt", "included")])

    def test_refresh_keeps_scroll_anchor_after_insertions(self):
        self.root.deiconify()
        self.root.geometry("900x650")
        rows = self.rows(250)
        self.app.populate_tree(rows)
        self.expand(self.base / "folder")
        self.drain()
        self.root.update()
        self.tree.yview_moveto(0.5)
        self.root.update_idletasks()
        anchor = next(self.tree.identify_row(y) for y in range(self.tree.winfo_height())
                      if self.tree.identify_row(y) and self.tree.bbox(self.tree.identify_row(y)))
        box = self.tree.bbox(anchor)
        anchor_y = box[1] + box[3] // 2
        added = [dict(rows[2], path=self.base / "folder" / f"new{i}", name=f"new{i}") for i in range(300)]
        self.app.populate_tree(rows[:2] + added + rows[2:])
        self.drain()
        self.assertEqual(self.tree.identify_row(anchor_y), anchor,
                         (anchor_y, self.tree.bbox(anchor), self.tree.yview()))
