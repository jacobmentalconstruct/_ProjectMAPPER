"""Agent adapter session (step 9.1): exposure, root confinement, forced backups,
approval by a trusted human only, and bounded results."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tests.support import temporary_directory
from projectmapper.adapters.bounds import bound, encoded_size
from projectmapper.adapters.session import EXPOSED, NOT_EXPOSED, AdapterSession
from projectmapper.core.settings import Settings

SRC = Path(__file__).resolve().parents[1] / "src"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Approver:
    """Stands in for the trusted approval window; records what it was shown."""

    def __init__(self, answer=True):
        self.answer = answer
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class SessionCase(unittest.TestCase):
    ask = True

    def setUp(self):
        self.temp = temporary_directory(self)
        base = Path(self.temp.name).resolve()
        self.root = base / "project"
        self.outside = base / "outside"
        self.root.mkdir()
        self.outside.mkdir()
        (self.outside / "secret.txt").write_text("secret\n", encoding="utf-8")
        self.a = self.root / "a.py"
        self.b = self.root / "b.py"
        self.a.write_bytes(b"alpha = 1\n")
        self.b.write_bytes(b"beta = 2\n")

    def session(self, approver=None, **settings):
        settings.setdefault("ask_before_single_file_writes", self.ask)
        session = AdapterSession(self.root, "mcp", approver=approver, settings=Settings(**settings))
        self.addCleanup(session.close)
        return session

    def backups(self, session):
        return session.call("backup.list")["data"]["count"]


class ExposureTests(SessionCase):
    def test_every_registered_action_is_classified_once(self):
        session = self.session()
        registered = set(session.controller.dispatcher.actions())
        self.assertEqual(set(EXPOSED) | set(NOT_EXPOSED), registered)
        self.assertEqual(set(EXPOSED) & set(NOT_EXPOSED), set())
        self.assertEqual(session.actions(), tuple(sorted(EXPOSED)))

    def test_unexposed_actions_are_refused_and_do_nothing(self):
        session = self.session(Approver(True))
        for action, payload in (("file.delete", {"path": "a.py"}), ("project.set_root", {"path": str(self.outside)}),
                                ("text.save_as", {"path": "a.py", "text": "x"}), ("backup.restore", {"plan_id": "x"}),
                                ("no.such.action", {})):
            with self.subTest(action=action):
                outcome = session.call(action, payload)
                self.assertEqual((outcome["status"], outcome["error"]["code"]), ("failed", "invalid_input"))
        self.assertTrue(self.a.exists())
        self.assertEqual(session.root, self.root)

    def test_payload_must_be_an_object(self):
        self.assertEqual(self.session().call("state.get", ["x"])["error"]["code"], "invalid_input")

    def test_backup_listing_is_limited_to_the_project(self):
        session = self.session()
        self.assertEqual(session.call("backup.list", {"scope": "user"})["error"]["code"], "invalid_input")
        self.assertEqual(session.call("backup.list")["status"], "succeeded")


class ConfinementTests(SessionCase):
    def test_relative_paths_resolve_inside_the_root(self):
        outcome = self.session().call("text.open", {"path": "a.py"})
        self.assertEqual(outcome["status"], "succeeded")
        self.assertEqual(outcome["data"]["text"], "alpha = 1\n")

    def test_paths_outside_the_root_are_refused(self):
        session = self.session()
        for path in (str(self.outside / "secret.txt"), "../outside/secret.txt", "sub/../../outside/secret.txt",
                     str(self.root.parent)):
            with self.subTest(path=path):
                outcome = session.call("text.open", {"path": path})
                self.assertEqual(outcome["error"]["code"], "unsafe_path")
                self.assertNotIn("secret", json.dumps(outcome["data"]))
        self.assertEqual(session.call("patch.load", {"path": "../outside/secret.txt"})["error"]["code"], "unsafe_path")
        self.assertEqual(session.call("project_patch.validate", {"root": str(self.outside),
                                                                 "manifest": {"files": []}})["error"]["code"],
                         "unsafe_path")

    def test_reference_folder_and_output_folder(self):
        (self.root / ".parts").mkdir()
        (self.root / ".parts" / "x.txt").write_text("x", encoding="utf-8")
        output = self.root / "_projectmapper"
        output.mkdir()
        (output / "note.md").write_text("note\n", encoding="utf-8")
        session = self.session(Approver(True))
        self.assertEqual(session.call("text.open", {"path": ".parts/x.txt"})["error"]["code"], "unsafe_path")
        # Reading ProjectMapper's own output is allowed; writing there is not.
        opened = session.call("text.open", {"path": "_projectmapper/note.md"})
        self.assertEqual(opened["status"], "succeeded")
        saved = session.call("text.save", {"path": "_projectmapper/note.md", "text": "x",
                                           "sha256": opened["data"]["sha256"]})
        self.assertEqual(saved["error"]["code"], "unsafe_path")
        created = session.call("file.create", {"folder": "_projectmapper", "name": "n.txt", "content": "x"})
        self.assertEqual(created["error"]["code"], "unsafe_path")
        self.assertEqual((output / "note.md").read_text(encoding="utf-8"), "note\n")

    def test_manifest_paths_cannot_escape(self):
        manifest = {"files": [{"path": "../outside/secret.txt", "sha256": sha(b"secret\n"),
                               "hunks": [{"search_block": "secret", "replace_block": "open"}]}]}
        outcome = self.session(Approver(True)).call("project_patch.validate", {"manifest": manifest})
        self.assertNotEqual(outcome["status"], "succeeded")
        self.assertEqual((self.outside / "secret.txt").read_text(encoding="utf-8"), "secret\n")

    def test_linked_folder_is_refused(self):
        link = self.root / "linked"
        try:
            os.symlink(self.outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("creating symbolic links is not permitted here")
        outcome = self.session().call("text.open", {"path": "linked/secret.txt"})
        self.assertEqual(outcome["error"]["code"], "unsafe_path")


class SingleFileWriteTests(SessionCase):
    def open(self, session, path="a.py"):
        return session.call("text.open", {"path": path})["data"]

    def test_without_an_approver_nothing_is_written(self):
        session = self.session()
        opened = self.open(session)
        outcome = session.call("text.save", {"path": "a.py", "text": "alpha = 9\n", "sha256": opened["sha256"]})
        self.assertEqual((outcome["status"], outcome["error"]["code"]), ("approval_required", "approval_required"))
        self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")
        self.assertFalse((self.root / "n.txt").exists())
        created = session.call("file.create", {"folder": ".", "name": "n.txt", "content": "x"})
        self.assertEqual(created["status"], "approval_required")
        self.assertFalse((self.root / "n.txt").exists())

    def test_approved_save_shows_the_exact_diff_and_keeps_a_backup(self):
        approver = Approver(True)
        session = self.session(approver)
        opened = self.open(session)
        outcome = session.call("text.save", {"path": "a.py", "text": "alpha = 9\n", "sha256": opened["sha256"]})
        self.assertEqual(outcome["status"], "succeeded")
        self.assertEqual(self.a.read_bytes(), b"alpha = 9\n")
        [request] = approver.requests
        self.assertEqual((request.action, request.origin), ("text.save", "mcp"))
        self.assertIn("-alpha = 1", request.diff)
        self.assertIn("+alpha = 9", request.diff)
        self.assertEqual(request.paths, (str(self.a),))
        self.assertEqual(self.backups(session), 1)
        history = session.call("history.query", {"text": "text.save"})["data"]["operations"]
        self.assertEqual([op["origin"] for op in history], ["mcp"])

    def test_denial_in_any_form_writes_nothing(self):
        for answer in (False, "yes", 1, RuntimeError("window failed")):
            with self.subTest(answer=answer):
                session = self.session(Approver(answer))
                opened = self.open(session)
                outcome = session.call("text.save", {"path": "a.py", "text": "x\n", "sha256": opened["sha256"]})
                self.assertEqual((outcome["status"], outcome["error"]["code"]), ("cancelled", "approval_denied"))
                self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")

    def test_changes_a_line_diff_hides_are_stated(self):
        self.a.write_bytes(b"one\r\ntwo\r\n")
        approver = Approver(False)
        session = self.session(approver)
        digest = self.open(session)["sha256"]
        session.call("text.save", {"path": "a.py", "text": "one\ntwo\n", "sha256": digest})
        session.call("text.save", {"path": "a.py", "text": "one\r\ntwo", "sha256": digest})
        first, second = approver.requests
        self.assertEqual(first.diff, "(No differences)")
        self.assertIn("Line endings change from CRLF to LF.", first.message)
        self.assertIn("The final newline is removed.", second.message)
        self.assertNotIn("Line endings", second.message)

    def test_unexpected_faults_become_results(self):
        session = self.session(Approver(True))
        def broken(request):
            raise RuntimeError("adapter fault")
        session.controller.dispatcher.submit = broken
        outcome = session.call("state.get")
        self.assertEqual(outcome["error"], {"code": "action_failed", "message": "RuntimeError: adapter fault"})

    def test_changed_file_is_refused_before_asking(self):
        approver = Approver(True)
        session = self.session(approver)
        outcome = session.call("text.save", {"path": "a.py", "text": "x\n", "sha256": sha(b"stale")})
        self.assertEqual(outcome["error"]["code"], "source_changed")
        self.assertEqual(approver.requests, [])

    def test_agents_cannot_turn_backups_off(self):
        session = self.session(Approver(True))
        opened = self.open(session)
        for value in (False, True):
            outcome = session.call("text.save", {"path": "a.py", "text": "x\n", "sha256": opened["sha256"],
                                                 "backup": value})
            self.assertEqual(outcome["error"]["code"], "invalid_input")
        self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")

    def test_patch_flow_is_approved_on_its_diff_and_backed_up(self):
        approver = Approver(True)
        session = self.session(approver)
        opened = self.open(session)
        patch = {"hunks": [{"search_block": "alpha = 1", "replace_block": "alpha = 2"}]}
        validated = session.call("patch.validate", {"path": "a.py", "patch": patch, "sha256": opened["sha256"]})
        self.assertEqual(validated["status"], "succeeded")
        self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")
        saved = session.call("patch.save", {"plan_id": validated["data"]["plan_id"]})
        self.assertEqual(saved["status"], "succeeded", saved)
        self.assertEqual(self.a.read_bytes(), b"alpha = 2\n")
        self.assertIn("+alpha = 2", approver.requests[0].diff)
        self.assertEqual(self.backups(session), 1)
        reused = session.call("patch.save", {"plan_id": validated["data"]["plan_id"]})
        self.assertEqual(reused["error"]["code"], "stale_plan")
        forged = session.call("patch.save", {"plan_id": "0" * 36})
        self.assertEqual(forged["error"]["code"], "stale_plan")
        self.assertEqual(len(approver.requests), 1)

    def test_create_never_overwrites(self):
        approver = Approver(True)
        session = self.session(approver)
        created = session.call("file.create", {"folder": ".", "name": "new.md", "content": "hello\n"})
        self.assertEqual(created["status"], "succeeded")
        self.assertEqual((self.root / "new.md").read_text(encoding="utf-8"), "hello\n")
        self.assertIn("+hello", approver.requests[0].diff)
        again = session.call("file.create", {"folder": ".", "name": "new.md", "content": "other\n"})
        self.assertEqual(again["status"], "failed")
        self.assertEqual((self.root / "new.md").read_text(encoding="utf-8"), "hello\n")


class SingleFileWithoutAskingTests(SessionCase):
    ask = False

    def test_setting_lets_guarded_saves_through_with_backups(self):
        session = self.session()  # no approver at all
        opened = session.call("text.open", {"path": "a.py"})["data"]
        outcome = session.call("text.save", {"path": "a.py", "text": "alpha = 3\n", "sha256": opened["sha256"]})
        self.assertEqual(outcome["status"], "succeeded")
        self.assertEqual(self.backups(session), 1)
        stale = session.call("text.save", {"path": "a.py", "text": "x", "sha256": opened["sha256"]})
        self.assertEqual(stale["error"]["code"], "source_changed")

    def test_project_apply_still_needs_approval(self):
        session = self.session()
        manifest = {"files": [{"path": "a.py", "sha256": sha(self.a.read_bytes()),
                               "hunks": [{"search_block": "alpha = 1", "replace_block": "alpha = 5"}]}]}
        plan = session.call("project_patch.validate", {"manifest": manifest})["data"]["plan_id"]
        outcome = session.call("project_patch.apply", {"plan_id": plan})
        self.assertEqual(outcome["status"], "approval_required")
        self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")


class ProjectPatchTests(SessionCase):
    def manifest(self):
        return {"files": [
            {"path": "a.py", "sha256": sha(self.a.read_bytes()),
             "hunks": [{"search_block": "alpha = 1", "replace_block": "alpha = 10"}]},
            {"path": "b.py", "sha256": sha(self.b.read_bytes()),
             "hunks": [{"search_block": "beta = 2", "replace_block": "beta = 20"}]}]}

    def test_multi_file_apply_is_approved_on_the_validated_diff(self):
        approver = Approver(True)
        session = self.session(approver)
        validated = session.call("project_patch.validate", {"manifest": self.manifest()})
        self.assertTrue(validated["data"]["valid"])
        applied = session.call("project_patch.apply", {"plan_id": validated["data"]["plan_id"]})
        self.assertEqual(applied["status"], "succeeded", applied)
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (b"alpha = 10\n", b"beta = 20\n"))
        [request] = approver.requests
        self.assertEqual(request.diff, validated["data"]["diff"])
        self.assertEqual(request.title, "Apply project patch?")
        self.assertEqual(self.backups(session), 2, "the project patch keeps its undo changeset")
        reused = session.call("project_patch.apply", {"plan_id": validated["data"]["plan_id"]})
        self.assertNotEqual(reused["status"], "succeeded")
        self.assertEqual(len(approver.requests), 1)

    def test_denied_or_unapproved_apply_writes_nothing(self):
        for approver, status in ((None, "approval_required"), (Approver(False), "cancelled")):
            with self.subTest(status=status):
                session = self.session(approver)
                plan = session.call("project_patch.validate", {"manifest": self.manifest()})["data"]["plan_id"]
                outcome = session.call("project_patch.apply", {"plan_id": plan})
                self.assertEqual(outcome["status"], status)
                self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (b"alpha = 1\n", b"beta = 2\n"))
                self.assertEqual(self.backups(session), 0)

    def test_agent_payload_cannot_forge_project_approval(self):
        session = self.session()
        plan = session.call("project_patch.validate", {"manifest": self.manifest()})["data"]["plan_id"]
        outcome = session.call("project_patch.apply", {"plan_id": plan, "approved": True})
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["error"]["code"], "invalid_input")
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (b"alpha = 1\n", b"beta = 2\n"))
        self.assertEqual(self.backups(session), 0)

    def test_file_changed_after_approval_preview_is_refused(self):
        def change_then_approve(request):
            self.b.write_bytes(b"beta = 99\n")
            return True
        session = self.session(change_then_approve)
        plan = session.call("project_patch.validate", {"manifest": self.manifest()})["data"]["plan_id"]
        outcome = session.call("project_patch.apply", {"plan_id": plan})
        self.assertEqual(outcome["error"]["code"], "source_changed")
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), (b"alpha = 1\n", b"beta = 99\n"))

    def test_agents_cannot_turn_project_backups_off(self):
        session = self.session(Approver(True))
        plan = session.call("project_patch.validate", {"manifest": self.manifest()})["data"]["plan_id"]
        outcome = session.call("project_patch.apply", {"plan_id": plan, "backup": False})
        self.assertEqual(outcome["error"]["code"], "invalid_input")
        self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")


class BoundTests(SessionCase):
    def test_limits_come_from_settings_and_agents_may_only_lower_them(self):
        self.a.write_bytes(b"x = 1\n" * 5000)  # 30 KB
        session = self.session(max_result_bytes=16 * 1024)
        full = session.call("text.open", {"path": "a.py"})
        self.assertLessEqual(encoded_size(full), 16 * 1024)
        self.assertEqual(full["truncated"][0]["field"], "data.text")
        self.assertEqual(full["truncated"][0]["original_chars"], 30000)
        higher = session.call("text.open", {"path": "a.py"}, max_bytes=1024 * 1024)
        self.assertLessEqual(encoded_size(higher), 16 * 1024)
        lower = session.call("text.open", {"path": "a.py"}, max_bytes=8192)
        self.assertLessEqual(encoded_size(lower), 8192)
        for bad in (100, "big", True):
            self.assertEqual(session.call("state.get", max_bytes=bad)["error"]["code"], "invalid_input")

    def test_truncated_text_cannot_be_saved_back_whole(self):
        self.a.write_bytes(b"x = 1\n" * 5000)
        session = self.session(Approver(True), max_result_bytes=16 * 1024)
        opened = session.call("text.open", {"path": "a.py"})
        self.assertIn("truncated", opened)
        outcome = session.call("text.save", {"path": "a.py", "text": opened["data"]["text"],
                                             "sha256": opened["data"]["sha256"]})
        self.assertEqual(outcome["error"]["code"], "invalid_input")
        self.assertEqual(len(self.a.read_bytes()), 30000)
        # Patching still works: the engine reads the whole file itself.
        patch = {"hunks": [{"search_block": "x = 1\n" * 5000, "replace_block": "x = 2\n"}]}
        validated = session.call("patch.validate", {"path": "a.py", "patch": patch,
                                                    "sha256": opened["data"]["sha256"]})
        self.assertEqual(validated["status"], "succeeded", validated)

    def test_bound_cuts_text_first_and_reports_items(self):
        value = {"data": {"text": "é" * 5000, "rows": [{"n": i} for i in range(10)]}}
        bounded, cuts, total = bound(value, 2000)
        self.assertEqual(total, encoded_size(value))
        self.assertLessEqual(encoded_size(bounded), 2000)
        self.assertEqual([cut["field"] for cut in cuts], ["data.text"])
        self.assertEqual(bounded["data"]["rows"], value["data"]["rows"])
        rows = {"rows": [{"path": f"file{i}.py"} for i in range(1000)]}
        bounded, cuts, _ = bound(rows, 1000)
        self.assertLessEqual(encoded_size(bounded), 1000)
        self.assertEqual(cuts[0]["original_items"], 1000)
        self.assertEqual(cuts[0]["kept_items"], len(bounded["rows"]))
        self.assertEqual(bound({"a": 1}, 100), ({"a": 1}, [], 8))


class HeadlessTests(unittest.TestCase):
    def test_session_use_never_imports_tkinter(self):
        temp = temporary_directory(self)
        (Path(temp.name) / "a.txt").write_text("a\n", encoding="utf-8")
        script = ("import sys\n"
                  "from projectmapper.adapters.session import AdapterSession\n"
                  "from projectmapper.core.settings import Settings\n"
                  f"s = AdapterSession({temp.name!r}, 'cli', settings=Settings())\n"
                  "assert s.call('project.scan')['status'] == 'succeeded'\n"
                  "assert s.call('text.open', {'path': 'a.txt'})['status'] == 'succeeded'\n"
                  "assert s.call('snapshot.compile')['status'] == 'succeeded'\n"
                  "s.close()\n"
                  "assert 'tkinter' not in sys.modules, 'tkinter imported'\n")
        run = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=60,
                             env={**os.environ, "PYTHONPATH": str(SRC)})
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
