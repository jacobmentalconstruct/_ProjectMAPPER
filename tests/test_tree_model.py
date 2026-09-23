from pathlib import Path
import unittest

from projectmapper.core.tree_model import LogicalTree


class LogicalTreeTests(unittest.TestCase):
    def rows(self):
        root = Path("root")
        return [{"path": root, "parent": None},
                {"path": root / "a", "parent": root},
                {"path": root / "a" / "old.txt", "parent": root / "a"}]

    def test_nested_new_paths_inherit_parent_intent(self):
        tree = LogicalTree(self.rows())
        tree.set_selection(Path("root"), "unchecked")
        rows = self.rows() + [
            {"path": Path("root") / "a" / "new", "parent": Path("root") / "a"},
            {"path": Path("root") / "a" / "new" / "file.txt", "parent": Path("root") / "a" / "new"},
        ]
        tree.replace(rows, tree.selection)
        self.assertFalse(tree.selected(Path("root/a/new/file.txt")))

    def test_child_override_survives_unrelated_refresh(self):
        tree = LogicalTree(self.rows())
        tree.set_selection(Path("root"), "unchecked")
        tree.set_selection(Path("root/a/old.txt"), "checked")
        tree.replace(self.rows(), tree.selection)
        self.assertTrue(tree.selected(Path("root/a/old.txt")))
        self.assertFalse(tree.selected(Path("root/a")))

    def test_removed_override_is_forgotten_and_folder_toggle_replaces_children(self):
        tree = LogicalTree(self.rows())
        tree.set_selection(Path("root"), "unchecked")
        tree.set_selection(Path("root/a/old.txt"), "checked")
        tree.replace(self.rows()[:-1], tree.selection)
        tree.replace(self.rows(), tree.selection)
        self.assertFalse(tree.selected(Path("root/a/old.txt")))
        tree.set_selection(Path("root"), "checked")
        self.assertTrue(all(value == "checked" for value in tree.selection.values()))
