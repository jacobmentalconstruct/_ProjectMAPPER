"""Operation history: one bounded, content-free record per operation, from any client."""

import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.support import temporary_directory
from projectmapper.application.contracts import Event
from projectmapper.application.controller import create_application
from projectmapper.application.dispatcher import Dispatcher
from projectmapper.application.history import OperationHistory

SENTINEL = "SENTINEL-CONTENT-7f3a"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.user = Path(temporary_directory(self).name).resolve() / "user-store"
        env = patch.dict(os.environ, {"PROJECTMAPPER_USER_BACKUPS": str(self.user)})
        env.start()
        self.addCleanup(env.stop)
        self.a = self.root / "a.txt"
        self.a.write_bytes(b"v1\n")
        self.make_app()

    def make_app(self, dispatcher=None):
        self.app, self.approve = create_application(self.root, dispatcher) if dispatcher else create_application(self.root)
        self.addCleanup(self.app.close)

    def query(self, **filters):
        result = self.app.execute("history.query", filters)
        self.assertEqual(result.status, "succeeded", result.error)
        return result.data["operations"]

    def record(self, operation_id):
        (found,) = [r for r in self.query() if r["id"] == operation_id]
        return found

    def approved(self, action, payload, answer=True):
        pending = self.app.execute(action, payload)
        self.approve(pending.operation_id, answer)
        self.app.dispatcher.wait(pending.operation_id)
        return pending.operation_id

    def test_success_record_has_times_duration_origin_category_and_paths(self):
        result = self.app.execute("text.save", {"path": str(self.a), "text": "v2\n", "sha256": sha(self.a)},
                                  origin="cli-test")
        rec = self.record(result.operation_id)
        self.assertEqual((rec["action"], rec["category"], rec["origin"], rec["status"]),
                         ("text.save", "text", "cli-test", "succeeded"))
        self.assertTrue(rec["accepted_at"] and rec["started_at"] and rec["finished_at"])
        self.assertGreaterEqual(rec["duration_ms"], 0)
        self.assertEqual(rec["paths"], [str(self.a)])
        self.assertIsNone(rec["error"])
        json.dumps(rec)

    def test_failure_records_error_code_and_message(self):
        result = self.app.execute("text.save", {"path": str(self.a), "text": "v2\n", "sha256": "0" * 64})
        rec = self.record(result.operation_id)
        self.assertEqual(rec["status"], "failed")
        self.assertEqual(rec["error"]["code"], "source_changed")
        self.assertIn("changed", rec["error"]["message"])

    def test_approval_approved_and_denied(self):
        yes = self.approved("file.delete", {"path": str(self.a)}, True)
        b = self.root / "b.txt"
        b.write_bytes(b"b\n")
        no = self.approved("file.delete", {"path": str(b)}, False)
        self.assertEqual((self.record(yes)["approval"], self.record(yes)["status"]), ("approved", "succeeded"))
        self.assertEqual((self.record(no)["approval"], self.record(no)["status"]), ("denied", "cancelled"))
        self.assertIn("delete", self.record(yes)["approval_title"].lower())

    def test_recovery_outcome_names_the_generation(self):
        (self.root / "c1.txt").write_bytes(b"orig1\n")
        (self.root / "c2.txt").write_bytes(b"orig2\n")
        manifest = json.dumps({"files": [{"path": n, "hunks": [{"search_block": o, "replace_block": w}]}
                                         for n, o, w in (("c1.txt", "orig1", "new1"), ("c2.txt", "orig2", "new2"))]})
        preview = self.app.execute("project_patch.validate", {"root": str(self.root), "manifest": manifest})
        real, calls = os.replace, []

        def failing(src, dst):
            calls.append(dst)
            if len(calls) == 1:
                real(src, dst)
                (self.root / "c1.txt").write_bytes(b"external\n")
                return None
            raise PermissionError("injected")
        with patch("projectmapper.tools.project_patcher.os.replace", side_effect=failing):
            operation = self.approved("project_patch.apply", {"plan_id": preview.data["plan_id"]})
        rec = self.record(operation)
        self.assertEqual(rec["status"], "recovery_required")
        self.assertEqual(len(rec["generations"]), 1)
        self.assertRegex(rec["generations"][0], r"^\d{8}T\d{12}Z-[0-9a-z]+$")

    def test_progress_is_coalesced_into_one_record(self):
        for i in range(60):
            (self.root / f"f{i:02}.txt").write_bytes(b"x\n")
        self.app.execute("project.scan")
        compiled = self.app.execute("snapshot.compile", timeout=120)
        records = [r for r in self.query() if r["action"] == "snapshot.compile"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], compiled.operation_id)
        self.assertGreater(records[0]["progress_count"], 3)
        self.assertIn("Snapshot compiled", records[0]["last_progress"], "the latest progress message is kept")

    def test_raw_event_flood_does_not_evict_history(self):
        self.make_app(Dispatcher(history_limit=40))
        first = self.app.execute("text.save", {"path": str(self.a), "text": "v2\n", "sha256": sha(self.a)})
        for i in range(500):  # about 50 progress events: more than the 40-event raw buffer
            (self.root / f"f{i:03}.txt").write_bytes(b"x\n")
        self.app.execute("project.scan")
        self.app.execute("snapshot.compile", timeout=120)
        raw = self.app.dispatcher.events(0)
        self.assertFalse(any(e.operation_id == first.operation_id for e in raw["events"]), "raw buffer evicted it")
        self.assertEqual(self.record(first.operation_id)["status"], "succeeded", "history kept it")

    def test_history_does_not_record_its_own_queries(self):
        for _ in range(3):
            self.query()
        self.assertEqual([r for r in self.query() if r["action"] == "history.query"], [])

    def test_filters(self):
        self.app.execute("text.save", {"path": str(self.a), "text": "v2\n", "sha256": sha(self.a)})
        self.app.execute("text.save", {"path": str(self.a), "text": "v3\n", "sha256": "0" * 64})
        self.app.execute("backup.list", {})
        self.assertEqual({r["action"] for r in self.query(category="backup")}, {"backup.list"})
        self.assertEqual([r["status"] for r in self.query(outcome="failed")], ["failed"])
        self.assertTrue(all("a.txt" in json.dumps(r) for r in self.query(text="a.txt")))
        self.assertEqual(len(self.query(limit=1)), 1)
        self.assertEqual(self.app.execute("history.query", {"outcome": "bogus"}).status, "failed")

    def test_history_holds_no_file_contents(self):
        self.app.execute("text.save", {"path": str(self.a), "text": f"{SENTINEL}\n", "sha256": sha(self.a),
                                       "backup": True})
        plan = self.app.execute("patch.validate", {"path": str(self.a), "sha256": sha(self.a), "patch": json.dumps(
            {"hunks": [{"search_block": SENTINEL, "replace_block": f"{SENTINEL}-2"}]})})
        self.app.execute("text.open", {"path": str(self.a)})
        self.app.execute("backup.preview", {"scope": "project",
                                            "generation": self.app.execute("backup.list", {}).data["generations"][0]["id"]})
        self.app.execute("project.scan")
        self.app.execute("snapshot.compile")
        self.assertTrue(plan.data["text"])
        self.assertNotIn(SENTINEL, json.dumps(self.query()))

    def test_two_subscribers_agree(self):
        second = OperationHistory()
        self.app.dispatcher.subscribe(second.observe)
        self.app.execute("text.save", {"path": str(self.a), "text": "v2\n", "sha256": sha(self.a)})
        self.app.execute("text.save", {"path": str(self.a), "text": "v3\n", "sha256": "0" * 64})
        mine = [(r["id"], r["status"]) for r in self.query()]
        theirs = [(r["id"], r["status"]) for r in second.query()]
        self.assertEqual(theirs, mine)


class BoundTests(unittest.TestCase):
    def feed(self, history, operation_id, *types, action="text.save"):
        for number, kind in enumerate(types):
            history.observe(Event(number, operation_id, action, "test", kind, {}))

    def test_limit_evicts_oldest_finished_but_never_running(self):
        history = OperationHistory(limit=5)
        self.feed(history, "running", "accepted", "started")
        self.feed(history, "waiting", "accepted", "started", "awaiting_approval")
        for number in range(8):
            self.feed(history, f"done-{number}", "accepted", "started", "succeeded")
        ids = [r["id"] for r in history.query(limit=100)]
        self.assertIn("running", ids)
        self.assertIn("waiting", ids)
        self.assertEqual(len(ids), 5)
        self.assertEqual([i for i in ids if i.startswith("done")], ["done-7", "done-6", "done-5"])


if __name__ == "__main__":
    unittest.main()
