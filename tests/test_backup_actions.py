"""Backup list, preview, restore and retention actions with trusted approval."""

import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.support import temporary_directory
from projectmapper.application.controller import create_application
from projectmapper.core.backups import BackupStore


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BackupActionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.user = Path(temporary_directory(self).name).resolve() / "user-store"
        env = patch.dict(os.environ, {"PROJECTMAPPER_USER_BACKUPS": str(self.user)})
        env.start()
        self.addCleanup(env.stop)
        self.app, self.approve = create_application(self.root)
        self.addCleanup(self.app.close)
        self.store = BackupStore.for_project(self.root)
        self.a = self.write("a.txt", b"v1\n")

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def backed_up_save(self, path, text):
        result = self.app.execute("text.save", {"path": str(path), "text": text, "sha256": sha(path), "backup": True})
        self.assertEqual(result.status, "succeeded", result.error)

    def run_approved(self, action, payload, approve=True):
        pending = self.app.execute(action, payload)
        self.assertEqual(pending.status, "awaiting_approval", pending.error)
        self.approve(pending.operation_id, approve)
        return pending, self.app.dispatcher.wait(pending.operation_id)

    def preview(self, generation, targets=None, scope="project"):
        payload = {"scope": scope, "generation": generation}
        if targets is not None:
            payload["targets"] = targets
        result = self.app.execute("backup.preview", payload)
        self.assertEqual(result.status, "succeeded", result.error)
        return result.data

    # --- list and preview ----------------------------------------------

    def test_list_reports_both_scopes(self):
        self.backed_up_save(self.a, "v2\n")
        outside = Path(temporary_directory(self).name).resolve() / "far.txt"
        outside.write_bytes(b"far\n")
        self.backed_up_save(outside, "farther\n")
        listed = self.app.execute("backup.list", {}).data["generations"]
        self.assertEqual(sorted(g["scope"] for g in listed), ["project", "user"])
        self.assertTrue(all(g["status"] == "ok" for g in listed))
        json.dumps(listed)

    def test_preview_diffs_backup_against_current(self):
        self.backed_up_save(self.a, "v2\n")
        (generation,) = self.store.list()
        data = self.preview(generation.id)
        (item,) = data["files"]
        self.assertEqual((item["target"], item["current_exists"], item["identical"]), ("a.txt", True, False))
        self.assertIn("-v2", item["diff"])
        self.assertIn("+v1", item["diff"])
        self.assertIsNotNone(data["plan_id"])

    # --- restore ---------------------------------------------------------

    def test_approved_restore_writes_backup_and_keeps_pre_restore_copy(self):
        self.backed_up_save(self.a, "v2\n")
        (generation,) = self.store.list()
        plan = self.preview(generation.id)
        pending, result = self.run_approved("backup.restore", {"plan_id": plan["plan_id"]})
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual(self.a.read_bytes(), b"v1\n")
        kinds = {g.kind: g for g in self.store.list()}
        self.assertEqual(self.store.read(kinds["pre-restore"].id, "a.txt"), b"v2\n")
        self.assertEqual(self.store.get(generation.id).status, "ok", "the backup itself is never consumed")
        self.assertIn("a.txt", pending.data["summary"]["message"])
        self.assertIn("file_transformed", self.app.state_view()["dirty_reasons"])

    def test_denied_restore_changes_nothing(self):
        self.backed_up_save(self.a, "v2\n")
        plan = self.preview(self.store.list()[0].id)
        _, result = self.run_approved("backup.restore", {"plan_id": plan["plan_id"]}, approve=False)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(self.a.read_bytes(), b"v2\n")
        self.assertEqual([g.kind for g in self.store.list()], ["backup"])

    def test_restore_refuses_changed_current_file(self):
        self.backed_up_save(self.a, "v2\n")
        plan = self.preview(self.store.list()[0].id)
        self.a.write_bytes(b"edited after preview\n")
        _, result = self.run_approved("backup.restore", {"plan_id": plan["plan_id"]})
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "source_changed")
        self.assertEqual(self.a.read_bytes(), b"edited after preview\n")
        self.assertEqual([g.kind for g in self.store.list()], ["backup"])

    def test_restore_refuses_corrupted_backup(self):
        self.backed_up_save(self.a, "v2\n")
        (generation,) = self.store.list()
        plan = self.preview(generation.id)
        (generation.path / generation.files[0]["stored"]).write_bytes(b"tampered\n")
        _, result = self.run_approved("backup.restore", {"plan_id": plan["plan_id"]})
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.a.read_bytes(), b"v2\n")

    def test_restore_failure_is_reported_and_keeps_all_recovery_material(self):
        self.write("b.txt", b"b1\n")
        preview = self.app.execute("project_patch.validate", {"root": str(self.root), "manifest": json.dumps(
            {"files": [{"path": n, "hunks": [{"search_block": o, "replace_block": w}]}
                       for n, o, w in (("a.txt", "v1", "v2"), ("b.txt", "b1", "b2"))]})})
        self.run_approved("project_patch.apply", {"plan_id": preview.data["plan_id"], "backup": True})
        (generation,) = self.store.list()
        plan = self.preview(generation.id)
        import projectmapper.application.controller as controller_module
        real, calls = controller_module.atomic_write_bytes, []

        def failing(path, data, mode=None):
            calls.append(path)
            if len(calls) == 2:
                raise PermissionError("injected")
            return real(path, data, mode=mode)
        with patch.object(controller_module, "atomic_write_bytes", side_effect=failing):
            _, result = self.run_approved("backup.restore", {"plan_id": plan["plan_id"]})
        self.assertEqual(result.status, "recovery_required")
        message = result.error["message"]
        restored, failed = ("a.txt", "b.txt") if Path(calls[0]).name == "a.txt" else ("b.txt", "a.txt")
        self.assertIn(f"restored {restored}", message)
        self.assertIn(failed, message)
        pre = [g for g in self.store.list() if g.kind == "pre-restore"]
        self.assertEqual(len(pre), 1)
        self.assertIn(pre[0].id, message)
        self.assertEqual(sorted(f["target"] for f in pre[0].files), ["a.txt", "b.txt"])
        self.assertEqual(self.store.get(generation.id).status, "ok")

    def test_restore_recreates_a_deleted_file(self):
        self.backed_up_save(self.a, "v2\n")
        self.a.unlink()
        plan = self.preview(self.store.list()[0].id)
        self.assertFalse(plan["files"][0]["current_exists"])
        _, result = self.run_approved("backup.restore", {"plan_id": plan["plan_id"]})
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual(self.a.read_bytes(), b"v1\n")
        self.assertNotIn("pre-restore", [g.kind for g in self.store.list()], "nothing existed to preserve")

    def test_restore_is_stale_after_root_change(self):
        self.backed_up_save(self.a, "v2\n")
        plan = self.preview(self.store.list()[0].id)
        other = Path(temporary_directory(self).name).resolve()
        self.app.execute("project.set_root", {"path": str(other)})
        result = self.app.execute("backup.restore", {"plan_id": plan["plan_id"]})
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.a.read_bytes(), b"v2\n")

    def test_user_scope_restore(self):
        outside = Path(temporary_directory(self).name).resolve() / "far.txt"
        outside.write_bytes(b"far\n")
        self.backed_up_save(outside, "farther\n")
        (generation,) = BackupStore.for_user().list()
        plan = self.preview(generation.id, scope="user")
        _, result = self.run_approved("backup.restore", {"plan_id": plan["plan_id"]})
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual(outside.read_bytes(), b"far\n")

    # --- retention -------------------------------------------------------

    def generations(self, count):
        for number in range(count):
            self.backed_up_save(self.a, f"v{number + 2}\n")
        return self.store.list()

    def prune_preview(self, **payload):
        result = self.app.execute("backup.prune_preview", {"scope": "project", **payload})
        self.assertEqual(result.status, "succeeded", result.error)
        return result.data

    def test_prune_preview_keeps_newest_and_never_offers_recovery_or_unverified(self):
        made = self.generations(4)
        recovery = self.store.create("recovery", "project_patch.apply", "op", [(self.a, b"orig\n", None)])
        incomplete = self.store.directory / "20200101T000000000000Z-abcdef12"
        incomplete.mkdir()
        data = self.prune_preview(keep=2)
        self.assertEqual([c["id"] for c in data["candidates"]], [g.id for g in made[2:]])
        self.assertNotIn(recovery.id, [c["id"] for c in data["candidates"]])
        self.assertIn(incomplete.name, [n["id"] for n in data["not_eligible"]])
        self.assertEqual(data["bytes"], sum(g.size for g in made[2:]))

    def test_recovery_generation_only_when_explicitly_included(self):
        self.generations(1)
        recovery = self.store.create("recovery", "project_patch.apply", "op", [(self.a, b"orig\n", None)])
        data = self.prune_preview(keep=5, include=[recovery.id])
        self.assertEqual([c["id"] for c in data["candidates"]], [recovery.id])

    def test_approved_prune_removes_only_candidates(self):
        made = self.generations(3)
        foreign = self.store.directory / "my-notes"
        foreign.mkdir()
        (foreign / "keep.txt").write_bytes(b"mine")
        data = self.prune_preview(keep=1)
        pending, result = self.run_approved("backup.prune", {"plan_id": data["plan_id"]})
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual([g.id for g in self.store.list()], [made[0].id])
        self.assertEqual((foreign / "keep.txt").read_bytes(), b"mine")
        for candidate in data["candidates"]:
            self.assertIn(candidate["id"], pending.data["summary"]["message"])

    def test_denied_prune_removes_nothing(self):
        self.generations(3)
        data = self.prune_preview(keep=1)
        _, result = self.run_approved("backup.prune", {"plan_id": data["plan_id"]}, approve=False)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(len(self.store.list()), 3)

    def test_prune_skips_candidates_changed_after_preview(self):
        made = self.generations(3)
        data = self.prune_preview(keep=1)
        tampered = made[1]
        manifest = tampered.path / "manifest.json"
        manifest.write_text(manifest.read_text(encoding="utf-8").replace("text.save", "text.save "), encoding="utf-8")
        extra = made[2].path / "unexpected.txt"
        extra.write_bytes(b"not ours")
        _, result = self.run_approved("backup.prune", {"plan_id": data["plan_id"]})
        self.assertEqual(result.status, "failed")
        message = result.error["message"]
        self.assertIn(tampered.id, message)
        self.assertIn(made[2].id, message)
        self.assertTrue(tampered.path.exists())
        self.assertEqual(extra.read_bytes(), b"not ours", "unexpected content is never deleted")

    def test_restore_refuses_targets_inside_the_output_folder(self):
        victim = self.root / "_projectmapper" / "notes.txt"
        victim.parent.mkdir(exist_ok=True)
        victim.write_bytes(b"store-adjacent\n")
        crafted = self.store.create("backup", "text.save", "op", [(victim, b"overwrite\n", None)])
        result = self.app.execute("backup.preview", {"scope": "project", "generation": crafted.id})
        self.assertEqual((result.status, result.error["code"]), ("failed", "unsafe_path"))
        self.assertEqual(victim.read_bytes(), b"store-adjacent\n")

    def test_invalid_inputs(self):
        for action, payload, code in (
                ("backup.prune_preview", {"scope": "project", "keep": -1}, "invalid_input"),
                ("backup.prune_preview", {"scope": "project", "keep": True}, "invalid_input"),
                ("backup.prune_preview", {"scope": "elsewhere", "keep": 1}, "invalid_input"),
                ("backup.prune_preview", {"scope": "project", "keep": 0,
                                          "include": ["20200101T000000000000Z-deadbeef"]}, "invalid_input"),
                ("backup.preview", {"scope": "project", "generation": "../../etc"}, "not_found")):
            with self.subTest(action=action, payload=payload):
                result = self.app.execute(action, payload)
                self.assertEqual((result.status, result.error["code"]), ("failed", code))


if __name__ == "__main__":
    unittest.main()
