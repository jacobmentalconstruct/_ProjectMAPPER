"""Per-file project patch review: every problem reported together, plans only when valid."""

import json
from pathlib import Path
import unittest

from tests.support import temporary_directory
from projectmapper.application.controller import create_application
from projectmapper.core.diff import DiffFile
from projectmapper.tools.patcher import PatchError
from projectmapper.tools.project_patcher import ProjectPatchSession


def hunk(search, replace):
    return {"search_block": search, "replace_block": replace}


def entry(path, *hunks, **extra):
    return {"path": path, "hunks": list(hunks), **extra}


class ReviewEngineTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.write("a.py", b"alpha\n")
        self.write("b.py", b"bravo\n")

    def write(self, name, data):
        (self.root / name).write_bytes(data)

    def review(self, *entries):
        session = ProjectPatchSession(self.root, {"version": 1, "files": list(entries)})
        return session, session.review()

    def test_every_file_error_is_reported_with_its_path(self):
        session, outcomes = self.review(entry("a.py", hunk("missing", "x")),
                                        entry("b.py", hunk("absent", "y")))
        self.assertEqual([o["status"] for o in outcomes], ["error", "error"])
        for outcome, path in zip(outcomes, ("a.py", "b.py")):
            self.assertEqual(outcome["relative_path"], path)
            self.assertIn(path, outcome["error"])
            self.assertIn("Hunk 1", outcome["error"])
        self.assertEqual(session.results, [])

    def test_validate_all_raises_one_error_naming_every_failing_file(self):
        session = ProjectPatchSession(self.root, {"files": [entry("a.py", hunk("missing", "x")),
                                                            entry("b.py", hunk("absent", "y"))]})
        with self.assertRaises(PatchError) as raised:
            session.validate_all()
        self.assertIn("a.py", str(raised.exception))
        self.assertIn("b.py", str(raised.exception))

    def test_valid_files_are_reviewed_alongside_errors(self):
        session, outcomes = self.review(entry("a.py", hunk("alpha", "ALPHA")),
                                        entry("b.py", hunk("absent", "y")))
        changed, failed = outcomes
        self.assertEqual((changed["status"], changed["additions"], changed["deletions"]), ("changed", 1, 1))
        self.assertEqual(changed["patched"], "ALPHA\n")
        self.assertEqual(failed["status"], "error")
        self.assertEqual(session.results, [], "no plan results while any file is invalid")

    def test_no_change_status_and_counts(self):
        session, (outcome,) = self.review(entry("a.py", hunk("alpha", "alpha")))
        self.assertEqual(outcome["status"], "no_change")
        self.assertEqual((outcome["additions"], outcome["deletions"], outcome["diff_hunks"]), (0, 0, []))
        self.assertEqual(outcome["hunk_count"], 1)
        self.assertEqual(len(session.results), 1)

    def test_empty_result_and_final_newline_flags(self):
        self.write("c.py", b"a\nb")
        _, (emptied, newline) = self.review(entry("a.py", hunk("alpha", "")),
                                            entry("c.py", hunk("b", "")))
        self.assertTrue(emptied["empty_result"])
        self.assertFalse(emptied["final_newline_changed"])
        self.assertEqual(newline["patched"], "a\n")
        self.assertTrue(newline["final_newline_changed"])
        self.assertFalse(newline["empty_result"])

    def test_source_hash_encoding_and_binary_problems_are_per_file(self):
        self.write("latin.txt", b"caf\xe9\n")
        self.write("bin.txt", b"a\x00b\n")
        _, outcomes = self.review(entry("a.py", hunk("alpha", "x"), sha256="0" * 64),
                                  entry("latin.txt", hunk("caf", "x")),
                                  entry("bin.txt", hunk("a", "x")),
                                  entry("b.py", hunk("bravo", "BRAVO")))
        self.assertEqual([o["status"] for o in outcomes], ["error", "error", "error", "changed"])
        self.assertIn("Source changed", outcomes[0]["error"])
        self.assertIn("UTF-8", outcomes[1]["error"])
        self.assertIn("binary", outcomes[2]["error"])

    def test_manifest_level_errors_stay_fatal(self):
        for manifest in ({"files": [entry("a.py", hunk("alpha", "x")), entry("a.py", hunk("alpha", "y"))]},
                         {"files": [entry("../a.py", hunk("alpha", "x"))]},
                         "{not json"):
            with self.subTest(manifest=manifest), self.assertRaises(PatchError):
                ProjectPatchSession(self.root, manifest)


class DiffHunkTests(unittest.TestCase):
    def test_separated_changes_form_separate_hunks(self):
        original = "".join(f"line {i}\n" for i in range(30))
        patched = original.replace("line 2\n", "LINE 2\n").replace("line 25\n", "LINE 25\n")
        hunks = DiffFile("x", original, patched).hunks
        self.assertEqual(len(hunks), 2)
        self.assertEqual((hunks[0]["original_start"], hunks[0]["original_end"]), (0, 6))
        self.assertEqual((hunks[1]["patched_start"], hunks[1]["patched_end"]), (22, 29))

    def test_nearby_changes_share_a_hunk_and_no_change_has_none(self):
        original = "".join(f"line {i}\n" for i in range(10))
        patched = original.replace("line 3\n", "X\n").replace("line 5\n", "Y\n")
        self.assertEqual(len(DiffFile("x", original, patched).hunks), 1)
        self.assertEqual(DiffFile("x", original, original).hunks, [])


class ReviewActionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        (self.root / "a.py").write_bytes(b"alpha\n")
        (self.root / "b.py").write_bytes(b"bravo\n")
        self.app, _ = create_application(self.root)
        self.addCleanup(self.app.close)

    def validate(self, *entries):
        return self.app.execute("project_patch.validate", {
            "root": str(self.root), "manifest": json.dumps({"version": 1, "files": list(entries)})})

    def test_invalid_manifest_returns_review_without_plan(self):
        result = self.validate(entry("a.py", hunk("alpha", "ALPHA")), entry("b.py", hunk("absent", "y")))
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertFalse(result.data["valid"])
        self.assertIsNone(result.data["plan_id"])
        self.assertEqual([f["status"] for f in result.data["files"]], ["changed", "error"])
        self.assertIn("b.py", result.data["errors"][0])
        json.dumps(result.data)  # transport-ready: no bytes or paths

    def test_valid_manifest_returns_plan_and_file_statistics(self):
        result = self.validate(entry("a.py", hunk("alpha", "ALPHA")), entry("b.py", hunk("bravo", "bravo")))
        self.assertTrue(result.data["valid"])
        self.assertIsNotNone(result.data["plan_id"])
        self.assertEqual(result.data["errors"], [])
        changed, unchanged = result.data["files"]
        self.assertEqual((changed["status"], changed["additions"], len(changed["diff_hunks"])), ("changed", 1, 1))
        self.assertEqual(unchanged["status"], "no_change")
        self.assertNotIn("original_bytes", changed)
        json.dumps(result.data)

    def test_manifest_level_error_fails_the_action(self):
        result = self.validate(entry("../a.py", hunk("alpha", "x")))
        self.assertEqual(result.status, "failed")


class ReviewWindowTests(unittest.TestCase):
    def test_window_reports_every_failing_file_and_keeps_apply_disabled(self):
        from tests.support import tk_root
        from projectmapper.app import ProjectMapperApp
        folder = Path(temporary_directory(self).name).resolve()
        (folder / "a.py").write_bytes(b"alpha\n")
        (folder / "b.py").write_bytes(b"bravo\n")
        root = tk_root(self)
        root.withdraw()
        app = ProjectMapperApp(root, folder)
        for timer in root.tk.call("after", "info"):
            root.after_cancel(timer)
        window = app.open_project_patcher(folder)
        self.addCleanup(window.top.destroy)
        window.manifest_box.delete("1.0", "end")
        window.manifest_box.insert("1.0", json.dumps({"files": [entry("a.py", hunk("missing", "x")),
                                                                entry("b.py", hunk("absent", "y"))]}))
        self.assertFalse(window.validate())
        self.assertIn("a.py", window.status.get())
        self.assertIn("b.py", window.status.get())
        self.assertIsNone(window.session)
        self.assertEqual(str(window.apply_button["state"]), "disabled")


if __name__ == "__main__":
    unittest.main()
