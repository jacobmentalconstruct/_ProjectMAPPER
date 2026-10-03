from pathlib import Path
import unittest

from projectmapper.core.changeset import parse_changeset
from projectmapper.core.config import OUTPUT_ROOT_NAME
from projectmapper.core.vtree import VirtualTree


class VirtualTreeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]

    def test_sequential_patch_and_move_keep_bytes_and_line_endings(self):
        changeset = parse_changeset({"version": 2, "ops": [
            {"op": "create", "path": "__virtual_mixed__.py",
             "content": "\ufeffhead\r\n\told\rchild\nlast"},
            {"op": "patch", "path": "__virtual_mixed__.py", "hunks": [
                {"search_block": "old", "replace_block": "    new\n        nested"}]},
            {"op": "move", "from": "__virtual_mixed__.py", "to": "__virtual_renamed__.py"},
            {"op": "patch", "path": "__virtual_renamed__.py", "hunks": [
                {"search_block": "nested", "replace_block": "inner"}]},
        ]})

        result = VirtualTree(self.root).simulate(changeset)

        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.final_files["__virtual_renamed__.py"],
                         b"\xef\xbb\xbfhead\r\n\tnew\r\t    inner\rchild\nlast")
        self.assertNotIn("__virtual_mixed__.py", result.final_files)

    def test_sequential_create_move_and_patch_use_overlay_paths(self):
        changeset = parse_changeset({"version": 2, "ops": [
            {"op": "create", "path": "__virtual_new__.txt", "content": "first\r\nsecond"},
            {"op": "move", "from": "__virtual_new__.txt", "to": "__virtual_renamed__.txt"},
            {"op": "patch", "path": "__virtual_renamed__.txt", "hunks": [
                {"search_block": "second", "replace_block": "last"}]},
        ]})

        result = VirtualTree(self.root).simulate(changeset)

        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.final_files, {"__virtual_renamed__.txt": b"first\r\nlast"})
        self.assertEqual(result.operations[0]["before"]["__virtual_new__.txt"]["kind"], "missing")
        self.assertEqual(result.operations[1]["before"]["__virtual_renamed__.txt"]["kind"], "missing")

    def test_collects_conflicts_and_continues_to_later_operations(self):
        changeset = parse_changeset({"version": 2, "ops": [
            {"op": "move", "from": "missing.txt", "to": "elsewhere.txt"},
            {"op": "create", "path": "README.md", "content": "collision"},
            {"op": "move_dir", "from": "src/projectmapper/core", "to": "src/projectmapper/core/inside"},
            {"op": "delete_dir", "path": "src/projectmapper/core"},
            {"op": "create", "path": "__virtual_later__.txt", "content": "still simulated"},
        ]})

        result = VirtualTree(self.root).simulate(changeset)

        self.assertFalse(result.valid)
        self.assertEqual(len(result.errors), 4)
        self.assertEqual(result.final_files["__virtual_later__.txt"], b"still simulated")

    def test_protected_folder_operation_is_a_conflict(self):
        changeset = parse_changeset({"version": 2, "ops": [
            {"op": "mkdir", "path": "_projectmapper/cache"},
        ]})

        result = VirtualTree(self.root).simulate(changeset)

        self.assertFalse(result.valid)
        self.assertIn("read-only", result.errors[0]["error"])

    def test_project_root_under_same_named_parent_is_not_mistaken_for_output_store(self):
        root = self.root.parent / OUTPUT_ROOT_NAME / "checkout"
        changeset = parse_changeset({"version": 2, "ops": [
            {"op": "create", "path": "new.txt", "content": "safe"},
        ]})

        result = VirtualTree(root).simulate(changeset)

        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.final_files, {"new.txt": b"safe"})

    def test_directory_moves_keep_sequential_virtual_descendants(self):
        changeset = parse_changeset({"version": 2, "ops": [
            {"op": "move_dir", "from": "src/projectmapper/core",
             "to": "src/projectmapper/renamed_core"},
            {"op": "move_dir", "from": "src/projectmapper",
             "to": "src/renamed_projectmapper"},
        ]})

        result = VirtualTree(self.root).simulate(changeset)

        self.assertTrue(result.valid, result.errors)
        self.assertIn("src/renamed_projectmapper/renamed_core/vtree.py", result.final_files)
        self.assertNotIn("src/projectmapper/core/vtree.py", result.final_files)

    def test_case_only_rename_is_allowed_but_casefolded_create_collides(self):
        rename = parse_changeset({"version": 2, "ops": [
            {"op": "move", "from": "README.md", "to": "readme.md"},
        ]})
        renamed = VirtualTree(self.root).simulate(rename)
        self.assertTrue(renamed.valid, renamed.errors)
        self.assertIn("readme.md", renamed.final_files)
        self.assertNotIn("README.md", renamed.final_files)

        create = parse_changeset({"version": 2, "ops": [
            {"op": "create", "path": "readme.md", "content": "duplicate"},
        ]})
        collision = VirtualTree(self.root).simulate(create)
        self.assertFalse(collision.valid)
        self.assertIn("already exists", collision.errors[0]["error"])


if __name__ == "__main__":
    unittest.main()
