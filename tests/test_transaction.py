import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from tests.support import temporary_directory
from projectmapper.core import transaction
from projectmapper.core.changeset import parse_changeset
from projectmapper.core.paths import PathSafetyError, SourceChangedError
from projectmapper.core.transaction import (RecoveryRequiredError, _rename_no_replace,
                                            apply_operations, prepare_undo)
from projectmapper.core.vtree import VirtualTree


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.root = Path(self.temp.name).resolve()

    def simulate(self, ops):
        changeset = parse_changeset({"version": 2, "ops": ops})
        result = VirtualTree(self.root).simulate(changeset)
        self.assertTrue(result.valid, result.errors)
        return result

    def test_structural_and_content_operations_commit_in_order(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "a.txt").write_bytes(b"old\r\n")
        (self.root / "move.txt").write_bytes(b"move me\n")
        plan = self.simulate([
            {"op": "patch", "path": "src/a.txt", "hunks": [
                {"search_block": "old", "replace_block": "new"}]},
            {"op": "create", "path": "first.txt", "content": "first\r\n"},
            {"op": "move", "from": "move.txt", "to": "moved.txt"},
            {"op": "mkdir", "path": "folder"},
            {"op": "create", "path": "folder/child.txt", "content": "child"},
            {"op": "move_dir", "from": "folder", "to": "renamed"},
            {"op": "delete", "path": "renamed/child.txt"},
        ])

        result = apply_operations(self.root, plan)

        self.assertEqual((self.root / "src/a.txt").read_bytes(), b"new\r\n")
        self.assertEqual((self.root / "first.txt").read_bytes(), b"first\r\n")
        self.assertEqual((self.root / "moved.txt").read_bytes(), b"move me\n")
        self.assertTrue((self.root / "renamed").is_dir())
        self.assertFalse((self.root / "renamed/child.txt").exists())
        self.assertFalse((self.root / "_projectmapper/.pending").exists())
        self.assertEqual(len(result["operations"]), 7)

    def test_mixed_changeset_record_and_inverse_round_trip(self):
        (self.root / "a.txt").write_bytes(b"old\n")
        (self.root / "move-me.txt").write_bytes(b"move data\n")
        (self.root / "folder").mkdir()
        if os.name != "nt":
            (self.root / "folder").chmod(0o750)
        (self.root / "folder" / "nested.txt").write_bytes(b"nested data\n")
        (self.root / "move-folder").mkdir()
        (self.root / "move-folder" / "child.txt").write_bytes(b"folder move data\n")
        manifest = {"version": 2, "ops": [
            {"op": "patch", "path": "a.txt", "hunks": [
                {"search_block": "old", "replace_block": "new"}]},
            {"op": "create", "path": "created.txt", "content": "new file\n"},
            {"op": "move", "from": "move-me.txt", "to": "moved.txt"},
            {"op": "move_dir", "from": "move-folder", "to": "moved-folder"},
            {"op": "mkdir", "path": "empty"},
            {"op": "delete_dir", "path": "folder", "recursive": True},
        ]}
        plan = self.simulate(manifest["ops"])
        blobs = {}
        records = []

        def record(items, changeset):
            blobs.update({Path(path).relative_to(self.root).as_posix(): data
                          for path, data, _ in items})
            records.append(changeset)

        apply_operations(self.root, plan, record=record, forward=manifest)
        self.assertEqual(len(records), 1)

        def read_backup(key):
            return blobs[key]

        inverse = prepare_undo(self.root, records[0], read_backup)
        self.assertTrue(inverse.valid)
        apply_operations(self.root, inverse)

        self.assertEqual((self.root / "a.txt").read_bytes(), b"old\n")
        self.assertEqual((self.root / "move-me.txt").read_bytes(), b"move data\n")
        self.assertFalse((self.root / "moved.txt").exists())
        self.assertEqual((self.root / "move-folder" / "child.txt").read_bytes(),
                         b"folder move data\n")
        self.assertFalse((self.root / "moved-folder").exists())
        self.assertFalse((self.root / "created.txt").exists())
        self.assertFalse((self.root / "empty").exists())
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.root / "folder").stat().st_mode), 0o750)
        self.assertEqual((self.root / "folder" / "nested.txt").read_bytes(), b"nested data\n")

    def test_backup_callback_runs_before_the_first_mutation(self):
        target = self.root / "a.txt"
        target.write_bytes(b"old\n")
        plan = self.simulate([{"op": "patch", "path": "a.txt", "hunks": [
            {"search_block": "old", "replace_block": "new"}]}])

        def fail_backup(items):
            self.assertEqual(items[0][1], b"old\n")
            self.assertEqual(target.read_bytes(), b"old\n")
            raise OSError("backup unavailable")

        with self.assertRaisesRegex(PathSafetyError, "backup unavailable"):
            apply_operations(self.root, plan, backup=fail_backup)
        self.assertEqual(target.read_bytes(), b"old\n")

    def test_external_destination_created_after_review_is_never_overwritten(self):
        source, destination = self.root / "a.txt", self.root / "b.txt"
        source.write_bytes(b"source")
        plan = self.simulate([{"op": "move", "from": "a.txt", "to": "b.txt"}])
        destination.write_bytes(b"external")

        with self.assertRaisesRegex(SourceChangedError, "Source changed"):
            apply_operations(self.root, plan)
        self.assertEqual(source.read_bytes(), b"source")
        self.assertEqual(destination.read_bytes(), b"external")

    def test_failure_after_a_patch_rolls_back_previous_operation(self):
        target, created = self.root / "a.txt", self.root / "b.txt"
        target.write_bytes(b"old\n")
        plan = self.simulate([
            {"op": "patch", "path": "a.txt", "hunks": [
                {"search_block": "old", "replace_block": "new"}]},
            {"op": "create", "path": "b.txt", "content": "created"},
        ])
        link = os.link

        def fail_create(source, destination, *args, **kwargs):
            if Path(destination) == created:
                raise OSError("injected create failure")
            return link(source, destination, *args, **kwargs)

        with patch("projectmapper.core.transaction.os.link", side_effect=fail_create):
            with self.assertRaisesRegex(PathSafetyError, "injected create failure"):
                apply_operations(self.root, plan)
        self.assertEqual(target.read_bytes(), b"old\n")
        self.assertFalse(created.exists())

    def test_failure_at_each_operation_index_rolls_back_prior_operations(self):
        operations = [
            {"op": "patch", "path": "source.txt", "hunks": [
                {"search_block": "old", "replace_block": "new"}]},
            {"op": "create", "path": "created.txt", "content": "created"},
            {"op": "move", "from": "move.txt", "to": "moved.txt"},
            {"op": "mkdir", "path": "folder"},
            {"op": "create", "path": "folder/child.txt", "content": "child"},
            {"op": "move_dir", "from": "folder", "to": "renamed"},
            {"op": "delete", "path": "renamed/child.txt"},
        ]
        # A patch operation performs one additional state check after staging.
        operation_start_checks = (0, 2, 3, 4, 5, 6, 7)

        for failed_index, check_index in enumerate(operation_start_checks):
            with self.subTest(operation_index=failed_index):
                root = self.root / f"case-{failed_index}"
                root.mkdir()
                (root / "source.txt").write_bytes(b"old\n")
                (root / "move.txt").write_bytes(b"move")
                plan = VirtualTree(root).simulate(parse_changeset({"version": 2, "ops": operations}))
                self.assertTrue(plan.valid, plan.errors)
                ensure = transaction._ensure_state
                calls = 0

                def fail_at_operation(root_arg, states, *, aliases=()):
                    nonlocal calls
                    current = calls
                    calls += 1
                    if current == check_index:
                        raise OSError(f"injected failure at operation {failed_index}")
                    return ensure(root_arg, states, aliases=aliases)

                with patch("projectmapper.core.transaction._ensure_state",
                           side_effect=fail_at_operation):
                    with self.assertRaisesRegex(PathSafetyError,
                                                f"operation {failed_index}"):
                        apply_operations(root, plan)

                self.assertEqual((root / "source.txt").read_bytes(), b"old\n")
                self.assertEqual((root / "move.txt").read_bytes(), b"move")
                self.assertFalse((root / "created.txt").exists())
                self.assertFalse((root / "moved.txt").exists())
                self.assertFalse((root / "folder").exists())
                self.assertFalse((root / "renamed").exists())
                self.assertFalse((root / "_projectmapper/.pending").exists())

    def test_failure_restores_prior_move_and_quarantined_delete(self):
        source, victim, destination = (self.root / "source.txt", self.root / "victim.txt",
                                       self.root / "created.txt")
        source.write_bytes(b"move me")
        victim.write_bytes(b"keep me")
        plan = self.simulate([
            {"op": "move", "from": "source.txt", "to": "moved.txt"},
            {"op": "delete", "path": "victim.txt"},
            {"op": "create", "path": "created.txt", "content": "new"},
        ])
        destination.write_bytes(b"external")

        with self.assertRaises(SourceChangedError):
            apply_operations(self.root, plan)

        self.assertEqual(source.read_bytes(), b"move me")
        self.assertFalse((self.root / "moved.txt").exists())
        self.assertEqual(victim.read_bytes(), b"keep me")
        self.assertEqual(destination.read_bytes(), b"external")
        self.assertFalse((self.root / "_projectmapper/.pending").exists())

    def test_recursive_delete_is_backed_up_and_restored_as_a_tree(self):
        folder = self.root / "folder"
        folder.mkdir()
        child = folder / "child.txt"
        child.write_bytes(b"preserve me\r\n")
        plan = self.simulate([
            {"op": "delete_dir", "path": "folder", "recursive": True},
            {"op": "create", "path": "later.txt", "content": "later"},
        ])
        (self.root / "later.txt").write_text("external", encoding="utf-8")
        backed_up = []

        def backup(items):
            self.assertTrue(child.is_file())
            backed_up.extend(items)

        with self.assertRaises(SourceChangedError):
            apply_operations(self.root, plan, backup=backup)

        self.assertEqual([(path.name, data) for path, data, _ in backed_up],
                         [("child.txt", b"preserve me\r\n")])
        self.assertEqual(child.read_bytes(), b"preserve me\r\n")
        self.assertEqual((self.root / "later.txt").read_text(encoding="utf-8"), "external")
        self.assertFalse((self.root / "_projectmapper/.pending").exists())

    def test_rollback_failure_raises_typed_error_and_saves_originals(self):
        target = self.root / "a.txt"
        target.write_bytes(b"old\n")
        plan = self.simulate([
            {"op": "patch", "path": "a.txt", "hunks": [
                {"search_block": "old", "replace_block": "new"}]},
            {"op": "create", "path": "b.txt", "content": "created"},
        ])
        link = os.link
        restored = []

        def fail_create(source, destination, *args, **kwargs):
            if Path(destination).name == "b.txt":
                raise OSError("injected create failure")
            return link(source, destination, *args, **kwargs)

        with patch("projectmapper.core.transaction.os.link", side_effect=fail_create), \
                patch("projectmapper.core.transaction.atomic_write_bytes", side_effect=OSError("locked")):
            with self.assertRaises(RecoveryRequiredError):
                apply_operations(self.root, plan, recover=lambda items: restored.extend(items) or "recovery")
        self.assertEqual(restored[0][1], b"old\n")
        self.assertEqual(target.read_bytes(), b"new\n")

    def test_case_only_file_move_uses_a_safe_temporary_name(self):
        source, destination = self.root / "ReadMe.txt", self.root / "README.txt"
        source.write_bytes(b"readme")
        plan = self.simulate([{"op": "move", "from": "ReadMe.txt", "to": "README.txt"}])

        apply_operations(self.root, plan)

        self.assertTrue(destination.is_file())
        self.assertEqual(destination.read_bytes(), b"readme")
        self.assertFalse(source.exists() and not os.path.samefile(source, destination))

    @unittest.skipIf(os.name == "nt", "POSIX file moves use atomic no-replace links")
    def test_posix_move_refuses_to_replace_existing_file(self):
        source, destination = self.root / "source.txt", self.root / "destination.txt"
        source.write_bytes(b"source")
        destination.write_bytes(b"keep")

        with self.assertRaises(FileExistsError):
            _rename_no_replace(source, destination)

        self.assertEqual(source.read_bytes(), b"source")
        self.assertEqual(destination.read_bytes(), b"keep")

    @unittest.skipUnless(os.name == "nt", "Windows-only locked-folder rename failure")
    def test_locked_folder_rename_failure_leaves_source_in_place(self):
        source, destination = self.root / "locked", self.root / "renamed"
        source.mkdir()
        (source / "child.txt").write_text("keep", encoding="utf-8")
        plan = self.simulate([{"op": "move_dir", "from": "locked", "to": "renamed"}])
        rename = os.rename

        def fail_locked_folder(src, dst):
            if Path(src) == source:
                raise PermissionError("injected locked folder")
            return rename(src, dst)

        with patch("projectmapper.core.transaction.os.rename", side_effect=fail_locked_folder):
            with self.assertRaisesRegex(PathSafetyError, "locked folder"):
                apply_operations(self.root, plan)

        self.assertTrue(source.is_dir())
        self.assertEqual((source / "child.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
