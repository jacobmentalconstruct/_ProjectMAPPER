"""Write paths use managed backup generations; recovery material is durable and reported truthfully."""

import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.support import temporary_directory
from projectmapper.application.controller import create_application
from projectmapper.core.backups import BackupError, BackupStore
from projectmapper.tools.patcher import PatchError
from projectmapper.tools.project_patcher import ProjectPatchSession


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(*pairs):
    return json.dumps({"files": [{"path": path, "hunks": [{"search_block": old, "replace_block": new}]}
                                 for path, old, new in pairs]})


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.user = Path(temporary_directory(self).name).resolve() / "user-store"
        env = patch.dict(os.environ, {"PROJECTMAPPER_USER_BACKUPS": str(self.user)})
        env.start()
        self.addCleanup(env.stop)
        self.app, self.approve = create_application(self.root)
        self.addCleanup(self.app.close)
        self.store = BackupStore.for_project(self.root)

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def save(self, path, text, backup=True):
        return self.app.execute("text.save", {"path": str(path), "text": text, "sha256": sha(path), "backup": backup})

    def apply(self, text, backup=False):
        preview = self.app.execute("project_patch.validate", {"root": str(self.root), "manifest": text})
        self.assertTrue(preview.data["valid"], preview.data)
        pending = self.app.execute("project_patch.apply", {"plan_id": preview.data["plan_id"], "backup": backup})
        self.approve(pending.operation_id, True)
        return self.app.dispatcher.wait(pending.operation_id)

    # --- entry finding 1: repeated backed-up saves ---------------------

    def test_repeated_backed_up_saves_each_create_a_generation(self):
        path = self.write("a.txt", b"v1\n")
        for text in ("v2\n", "v3\n", "v4\n"):
            result = self.save(path, text)
            self.assertEqual(result.status, "succeeded", result.error)
        generations = self.store.list()
        self.assertEqual([g.kind for g in generations], ["backup"] * 3)
        self.assertEqual([self.store.read(g.id, "a.txt") for g in generations], [b"v3\n", b"v2\n", b"v1\n"])
        self.assertEqual(path.read_bytes(), b"v4\n")
        self.assertFalse((self.root / "a.txt.bak").exists())

    def test_save_without_backup_writes_no_generation(self):
        path = self.write("a.txt", b"v1\n")
        self.assertEqual(self.save(path, "v2\n", backup=False).status, "succeeded")
        self.assertEqual(self.store.list(), [])

    def test_single_file_patcher_save_uses_generations(self):
        path = self.write("a.txt", b"old\n")
        plan = self.app.execute("patch.validate", {"path": str(path), "sha256": sha(path),
                                                   "patch": json.dumps({"hunks": [{"search_block": "old", "replace_block": "new"}]})})
        self.app.execute("patch.result", {"plan_id": plan.data["plan_id"]})
        saved = self.app.execute("patch.save", {"plan_id": plan.data["plan_id"], "backup": True})
        self.assertEqual(saved.status, "succeeded", saved.error)
        (generation,) = self.store.list()
        self.assertEqual(self.store.read(generation.id, "a.txt"), b"old\n")
        self.assertEqual(generation.action, "patch.save")

    def test_requested_backup_failure_stops_the_save(self):
        path = self.write("a.txt", b"v1\n")
        with patch.object(BackupStore, "create", side_effect=BackupError("Backup was not written: disk full")):
            result = self.save(path, "v2\n")
        self.assertEqual(result.status, "failed")
        self.assertIn("Backup was not written", result.error["message"])
        self.assertEqual(path.read_bytes(), b"v1\n")

    def test_outside_root_save_uses_the_user_store(self):
        outside = Path(temporary_directory(self).name).resolve() / "elsewhere.txt"
        outside.write_bytes(b"far\n")
        self.assertEqual(self.save(outside, "farther\n").status, "succeeded")
        (generation,) = BackupStore.for_user().list()
        self.assertEqual(generation.scope, "user")
        self.assertEqual(BackupStore.for_user().read(generation.id, str(outside)), b"far\n")
        self.assertEqual(self.store.list(), [])

    # --- entry finding 2: existing .bak must not block ------------------

    def test_existing_bak_neither_blocks_apply_nor_is_touched(self):
        self.write("b.txt", b"old\n")
        self.write("c.txt", b"cold\n")
        bak = self.write("b.txt.bak", b"someone else's backup\n")
        result = self.apply(manifest(("b.txt", "old", "new"), ("c.txt", "cold", "warm")), backup=True)
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual(bak.read_bytes(), b"someone else's backup\n")
        (generation,) = self.store.list()
        self.assertEqual(generation.action, "project_patch.apply")
        self.assertEqual(sorted(f["target"] for f in generation.files), ["b.txt", "c.txt"])
        self.assertEqual(self.store.read(generation.id, "c.txt"), b"cold\n")

    def test_requested_backup_failure_stops_apply_before_any_replacement(self):
        self.write("b.txt", b"old\n")
        with patch.object(BackupStore, "create", side_effect=BackupError("Backup was not written: disk full")):
            result = self.apply(manifest(("b.txt", "old", "new")), backup=True)
        self.assertEqual(result.status, "failed")
        self.assertIn("Backup was not written", result.error["message"])
        self.assertEqual((self.root / "b.txt").read_bytes(), b"old\n")

    # --- entry finding 3: durable, truthful recovery material ----------

    def conflicted_apply(self):
        first = self.write("c1.txt", b"orig1\n")
        self.write("c2.txt", b"orig2\n")
        real, calls = os.replace, []

        def failing(src, dst):
            calls.append(dst)
            if len(calls) == 1:
                real(src, dst)
                first.write_bytes(b"external edit\n")
                return None
            raise PermissionError("injected")
        with patch("projectmapper.tools.project_patcher.os.replace", side_effect=failing):
            return self.apply(manifest(("c1.txt", "orig1", "new1"), ("c2.txt", "orig2", "new2")))

    def test_rollback_conflict_saves_originals_in_a_recovery_generation(self):
        result = self.conflicted_apply()
        self.assertEqual(result.status, "recovery_required")
        message = result.error["message"]
        self.assertNotIn("retained in this session", message)
        (generation,) = self.store.list()
        self.assertEqual(generation.kind, "recovery")
        self.assertIn(generation.id, message)
        self.assertEqual(self.store.read(generation.id, "c1.txt"), b"orig1\n")
        self.assertEqual((self.root / "c1.txt").read_bytes(), b"external edit\n", "external edit preserved")
        self.assertEqual((self.root / "c2.txt").read_bytes(), b"orig2\n")

    def test_recovery_store_failure_is_reported_truthfully(self):
        with patch.object(BackupStore, "create", side_effect=BackupError("Backup was not written: disk full")):
            result = self.conflicted_apply()
        self.assertEqual(result.status, "recovery_required")
        self.assertIn("could not be saved", result.error["message"])
        self.assertNotIn("retained in this session", result.error["message"])

    def test_engine_without_a_recovery_store_does_not_claim_retention(self):
        self.write("c1.txt", b"orig1\n")
        self.write("c2.txt", b"orig2\n")
        session = ProjectPatchSession(self.root, manifest(("c1.txt", "orig1", "new1"), ("c2.txt", "orig2", "new2")))
        session.validate_all()
        real, calls = os.replace, []

        def failing(src, dst):
            calls.append(dst)
            if len(calls) == 1:
                real(src, dst)
                (self.root / "c1.txt").write_bytes(b"external edit\n")
                return None
            raise PermissionError("injected")
        with patch("projectmapper.tools.project_patcher.os.replace", side_effect=failing), \
                self.assertRaises(PatchError) as raised:
            session.apply_all()
        self.assertIn("Recovery required", str(raised.exception))
        self.assertIn("not saved", str(raised.exception))
        self.assertNotIn("retained in this session", str(raised.exception))

    # --- managed storage is not a patch target -------------------------

    def test_output_folder_is_not_a_project_patch_target(self):
        self.save(self.write("a.txt", b"v1\n"), "v2\n")
        (generation,) = self.store.list()
        blob = f"_projectmapper/backups/{generation.id}/0001.bin"
        preview = self.app.execute("project_patch.validate", {"root": str(self.root),
                                                              "manifest": manifest((blob, "v1", "tampered"))})
        self.assertEqual(preview.status, "failed")
        self.assertIn("_projectmapper", preview.error["message"])
        self.assertEqual(self.store.list()[0].status, "ok")


if __name__ == "__main__":
    unittest.main()
