import unittest

from projectmapper.core.changeset import inverse_operation, parse_changeset
from projectmapper.core.paths import PathSafetyError


class ChangeSetParsingTests(unittest.TestCase):
    def test_v1_files_normalize_to_v2_patch_ops_without_changing_hunk_text(self):
        hunk = {"search_block": "\told\r\n", "replace_block": "\tnew\r\n",
                "use_patch_indent": False}
        parsed = parse_changeset({"description": "legacy", "files": [
            {"path": "src/example.py", "sha256": "a" * 64, "hunks": [hunk]}
        ]})

        self.assertEqual(parsed.as_dict(), {"version": 2, "description": "legacy", "ops": [
            {"op": "patch", "path": "src/example.py", "sha256": "a" * 64, "hunks": [hunk]}
        ]})
        self.assertEqual(hunk["search_block"], "\told\r\n")

    def test_v2_aliases_normalize_to_canonical_names(self):
        parsed = parse_changeset({"version": 2, "ops": [
            {"op": "rename", "from": "old.py", "to": "new.py"},
            {"op": "rename_dir", "from": "old", "to": "new"},
        ]})

        self.assertEqual([op.kind for op in parsed.ops], ["move", "move_dir"])
        self.assertEqual(parsed.ops[0].source, "old.py")
        self.assertEqual(parsed.ops[0].destination, "new.py")

    def test_create_accepts_empty_content_and_delete_dir_defaults_to_nonrecursive(self):
        parsed = parse_changeset({"version": 2, "ops": [
            {"op": "create", "path": "empty.txt", "content": ""},
            {"op": "delete_dir", "path": "empty"},
        ]})

        self.assertEqual(parsed.ops[0].content, "")
        self.assertFalse(parsed.ops[1].recursive)

    def test_malformed_manifest_shapes_are_refused(self):
        cases = [
            [],
            {"version": 3, "ops": []},
            {"files": []},
            {"version": 2, "files": []},
            {"version": 2, "ops": []},
            {"version": 2, "ops": [{"op": "move", "from": "a"}]},
            {"version": 2, "ops": [{"op": "create", "path": "a"}]},
            {"version": 2, "ops": [{"op": "delete_dir", "path": "a", "recursive": 1}]},
            {"version": 2, "ops": [{"op": "patch", "path": "a", "hunks": []}]},
            {"version": 2, "ops": [{"op": "patch", "path": "a", "hunks": [{"search_block": "a"}]}]},
            {"version": 2, "ops": [{"op": "patch", "path": "a", "hunks": [
                {"search_block": "a", "replace_block": "b", "use_patch_indent": 1}]}]},
            {"version": 2, "ops": [{"op": "patch", "path": "a", "sha256": "z" * 64,
                                      "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"version": 2, "ops": [{"op": "mkdir", "path": "a", "unknown": True}]},
            {"version": 2, "ops": [{"op": "mkdir", "path": "a"}], "unknown": True},
        ]
        for manifest in cases:
            with self.subTest(manifest=manifest), self.assertRaises(PathSafetyError):
                parse_changeset(manifest)

    def test_inverse_shapes_and_captured_file_bytes(self):
        patch, create, delete, move, mkdir, move_dir, delete_dir = parse_changeset({
            "version": 2, "ops": [
                {"op": "patch", "path": "file.py", "hunks": [
                    {"search_block": "old", "replace_block": "new"}]},
                {"op": "create", "path": "new.py", "content": "new"},
                {"op": "delete", "path": "gone.py"},
                {"op": "move", "from": "a.py", "to": "b.py"},
                {"op": "mkdir", "path": "new-dir"},
                {"op": "move_dir", "from": "a", "to": "b"},
                {"op": "delete_dir", "path": "empty"},
            ]}).ops

        with self.assertRaises(ValueError):
            inverse_operation(patch)
        self.assertEqual(inverse_operation(patch, original_bytes=b"old").kind, "restore")
        self.assertEqual(inverse_operation(create).kind, "delete")
        self.assertEqual(inverse_operation(delete, original_bytes=b"gone").original_bytes, b"gone")
        self.assertEqual((inverse_operation(move).source, inverse_operation(move).destination),
                         ("b.py", "a.py"))
        self.assertEqual(inverse_operation(mkdir).kind, "delete_dir")
        self.assertEqual((inverse_operation(move_dir).source, inverse_operation(move_dir).destination),
                         ("b", "a"))
        self.assertEqual(inverse_operation(delete_dir).kind, "mkdir")
        with self.assertRaisesRegex(ValueError, "expanded"):
            inverse_operation(parse_changeset({"version": 2, "ops": [
                {"op": "delete_dir", "path": "tree", "recursive": True}
            ]}).ops[0])


if __name__ == "__main__":
    unittest.main()
