"""Managed backup generations: scoped store, ownership, integrity and safe listing."""

import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from tests.support import temporary_directory
from projectmapper.core import backups
from projectmapper.core.backups import BackupError, BackupStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.target = self.root / "src" / "a.txt"
        self.target.parent.mkdir()
        self.target.write_bytes(b"alpha\r\n")
        self.store = BackupStore.for_project(self.root)

    def create(self, *targets, kind="backup"):
        return self.store.create(kind, "text.save", "op-1234567890",
                                 [(path, path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in targets])

    def test_generation_round_trip(self):
        generation = self.create(self.target)
        self.assertEqual(generation.status, "ok")
        self.assertEqual(generation.kind, "backup")
        self.assertEqual(generation.scope, "project")
        self.assertEqual(generation.files[0]["target"], "src/a.txt")
        self.assertEqual(self.store.read(generation.id, "src/a.txt"), b"alpha\r\n")
        self.assertTrue(generation.path.is_relative_to(self.root / "_projectmapper" / "backups"))
        listed = self.store.list()
        self.assertEqual([(g.id, g.status) for g in listed], [(generation.id, "ok")])
        manifest = json.loads((generation.path / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["format"], manifest["version"]), (backups.FORMAT, backups.VERSION))

    def test_repeated_backups_create_distinct_generations(self):
        first = self.create(self.target)
        self.target.write_bytes(b"bravo\r\n")
        second = self.create(self.target)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(self.store.read(first.id, "src/a.txt"), b"alpha\r\n")
        self.assertEqual(self.store.read(second.id, "src/a.txt"), b"bravo\r\n")
        self.assertEqual([g.id for g in self.store.list()], [second.id, first.id], "newest first")

    def test_name_collision_retries_with_a_new_name(self):
        fixed = backups.datetime(2026, 9, 24, 12, 0, 0, 123456, tzinfo=backups.timezone.utc)

        class FrozenClock(backups.datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed
        suffixes = iter(["same", "same", "other"])
        with patch.object(backups, "datetime", FrozenClock), \
                patch.object(backups, "_suffix", side_effect=lambda: next(suffixes)) as suffix:
            first = self.create(self.target)
            second = self.create(self.target)
        self.assertEqual(suffix.call_count, 3, "the second create collided once and retried")
        self.assertTrue(first.id.endswith("-same"))
        self.assertTrue(second.id.endswith("-other"))
        self.assertEqual(len(self.store.list()), 2)

    def test_linked_generation_directories_are_ignored(self):
        generation = self.create(self.target)
        outside = Path(temporary_directory(self).name).resolve()
        link = self.store.directory / "20260101T000000000000Z-linked"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            import subprocess
            made = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                                  capture_output=True, text=True)
            if made.returncode:
                self.skipTest(f"cannot create a symlink or junction here: {made.stderr.strip()}")
        self.assertEqual([g.id for g in self.store.list()], [generation.id])
        with self.assertRaises(BackupError):
            self.store.get(link.name)

    def test_multi_file_generation(self):
        other = self.root / "b.txt"
        other.write_bytes(b"bee\n")
        generation = self.create(self.target, other)
        self.assertEqual(sorted(f["target"] for f in generation.files), ["b.txt", "src/a.txt"])
        self.assertEqual(self.store.read(generation.id, "b.txt"), b"bee\n")

    def test_missing_manifest_is_incomplete_and_unreadable(self):
        generation = self.create(self.target)
        (generation.path / "manifest.json").unlink()
        (listed,) = self.store.list()
        self.assertEqual(listed.status, "incomplete")
        with self.assertRaises(BackupError):
            self.store.read(generation.id, "src/a.txt")

    def test_tampered_blob_is_corrupt(self):
        generation = self.create(self.target)
        blob = generation.path / generation.files[0]["stored"]
        blob.write_bytes(b"tampered\r\n")
        (listed,) = self.store.list()
        self.assertEqual(listed.status, "corrupt")
        self.assertIn("sha256", listed.problem)
        with self.assertRaises(BackupError):
            self.store.read(generation.id, "src/a.txt")

    def test_malformed_and_unsafe_manifests_are_corrupt(self):
        cases = {
            "bad kind": lambda m: m.update(kind="whatever"),
            "stored traversal": lambda m: m["files"][0].update(stored="../../outside.bin"),
            "target traversal": lambda m: m["files"][0].update(target="../escape.txt"),
            "absolute target in project scope": lambda m: m["files"][0].update(target=str(self.target)),
            "wrong format": lambda m: m.update(format="something-else"),
            "future version": lambda m: m.update(version=99),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                generation = self.create(self.target)
                path = generation.path / "manifest.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                mutate(manifest)
                path.write_text(json.dumps(manifest), encoding="utf-8")
                self.assertEqual(self.store.get(generation.id).status, "corrupt")
                with self.assertRaises(BackupError):
                    self.store.read(generation.id, "src/a.txt")

    def test_foreign_entries_are_ignored_and_untouched(self):
        self.create(self.target)
        foreign_dir = self.store.directory / "my-notes"
        foreign_dir.mkdir()
        (foreign_dir / "keep.txt").write_bytes(b"mine")
        (self.store.directory / "loose-file.txt").write_bytes(b"loose")
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual((foreign_dir / "keep.txt").read_bytes(), b"mine")
        self.assertEqual((self.store.directory / "loose-file.txt").read_bytes(), b"loose")

    def test_sibling_bak_is_never_created_or_touched(self):
        bak = self.target.with_name("a.txt.bak")
        bak.write_bytes(b"user's own backup")
        self.create(self.target)
        self.create(self.target)
        self.assertEqual(bak.read_bytes(), b"user's own backup")
        self.assertEqual(sorted(p.name for p in self.target.parent.iterdir()), ["a.txt", "a.txt.bak"])

    def test_failure_while_writing_removes_only_its_own_partial_generation(self):
        self.create(self.target)
        other = self.root / "b.txt"
        other.write_bytes(b"bee\n")
        real = backups._write_blob
        calls = []

        def failing(path, data, mode):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(path, data, mode)
        with patch.object(backups, "_write_blob", side_effect=failing), self.assertRaises(BackupError):
            self.create(self.target, other)
        self.assertEqual([g.status for g in self.store.list()], ["ok"])

    def test_invalid_kind_and_outside_scope_target_are_refused(self):
        with self.assertRaises(BackupError):
            self.create(self.target, kind="nightly")
        outside = Path(temporary_directory(self).name).resolve() / "x.txt"
        outside.write_bytes(b"x")
        with self.assertRaises(BackupError):
            self.store.create("backup", "text.save", "op", [(outside, b"x", None)])

    def test_mode_is_recorded(self):
        generation = self.create(self.target)
        self.assertEqual(generation.files[0]["mode"], stat.S_IMODE(self.target.stat().st_mode))


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.user = Path(temporary_directory(self).name).resolve() / "user-backups"
        patcher = patch.dict(os.environ, {"PROJECTMAPPER_USER_BACKUPS": str(self.user)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_store_for_selects_project_or_user_scope(self):
        inside = self.root / "a.txt"
        outside = Path(temporary_directory(self).name).resolve() / "elsewhere.txt"
        self.assertEqual(BackupStore.for_target(inside, self.root).scope, "project")
        user = BackupStore.for_target(outside, self.root)
        self.assertEqual((user.scope, user.directory), ("user", self.user))

    def test_user_scope_records_absolute_targets(self):
        outside = Path(temporary_directory(self).name).resolve() / "elsewhere.txt"
        outside.write_bytes(b"far away\n")
        store = BackupStore.for_target(outside, self.root)
        generation = store.create("backup", "text.save", "op", [(outside, b"far away\n", None)])
        self.assertEqual(generation.files[0]["target"], str(outside))
        self.assertEqual(store.read(generation.id, str(outside)), b"far away\n")
        self.assertFalse((self.root / "_projectmapper").exists())

    def test_user_default_location_without_override(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROJECTMAPPER_USER_BACKUPS", None)
            with patch.dict(os.environ, {"LOCALAPPDATA": str(self.user.parent)}), \
                    patch.object(backups.sys, "platform", "win32"):
                self.assertEqual(backups.user_backup_dir(), self.user.parent / "ProjectMapper" / "backups")


if __name__ == "__main__":
    unittest.main()
