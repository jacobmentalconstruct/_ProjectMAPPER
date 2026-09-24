"""Phase 8 acceptance-evidence gaps G1-G6 (plan section 14 rows without direct tests)."""

import contextlib
import sys
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from tests.support import temporary_directory
from projectmapper.application.controller import create_application
from projectmapper.core import config
from projectmapper.core.diagnostics import collect_diagnostics
from projectmapper.tools.patcher import PatchSession


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.user = Path(temporary_directory(self).name).resolve() / "user-store"
        env = patch.dict(os.environ, {"PROJECTMAPPER_USER_BACKUPS": str(self.user)})
        env.start()
        self.addCleanup(env.stop)
        (self.root / "src").mkdir()
        self.a = self.root / "src" / "a.py"
        self.a.write_bytes(b"alpha = 1\n")
        (self.root / "README.md").write_bytes(b"# Demo\n")
        self.open_app()

    def open_app(self):
        self.app, self.approve = create_application(self.root)
        self.addCleanup(self.app.close)

    def compile(self):
        self.assertEqual(self.app.execute("project.scan").status, "succeeded")
        result = self.app.execute("snapshot.compile")
        self.assertEqual(result.status, "succeeded", result.error)
        return Path(result.data["path"])

    def export(self, output="project_tree_markdown", suffix=config.TREE_MD_SUFFIX, **extra):
        return self.app.execute("snapshot.export", {"output": output, "suffix": suffix, **extra})


class G1HeadlessExportTests(ProjectCase):
    def test_every_projection_exports(self):
        self.compile()
        for output, suffix, expected in (
                ("project_tree_markdown", config.TREE_MD_SUFFIX, "a.py"),
                ("project_filedump_markdown", config.FILEDUMP_MD_SUFFIX, "alpha = 1"),
                ("project_tree_and_filedump_markdown", config.COMBINED_MD_SUFFIX, "alpha = 1"),
                ("snapshot_manifest_markdown", config.MANIFEST_MD_SUFFIX, "Snapshot Manifest")):
            with self.subTest(output=output):
                result = self.export(output, suffix)
                self.assertEqual(result.status, "succeeded", result.error)
                written = Path(result.data["path"])
                self.assertEqual(written.parent, self.root / config.OUTPUT_ROOT_NAME)
                self.assertIn(expected, written.read_text(encoding="utf-8"))

    def test_scan_compile_export_in_a_process_that_never_imports_tkinter(self):
        import subprocess
        script = (
            "import sys; from pathlib import Path\n"
            "from projectmapper.application.controller import create_application\n"
            f"c, _ = create_application(Path({str(self.root)!r}))\n"
            "assert c.execute('project.scan').status == 'succeeded'\n"
            "assert c.execute('snapshot.compile').status == 'succeeded'\n"
            "r = c.execute('snapshot.export', {'output': 'project_tree_markdown', 'suffix': '"
            f"{config.TREE_MD_SUFFIX}'" "})\n"
            "assert r.status == 'succeeded', r.error\n"
            "c.close()\n"
            "assert 'tkinter' not in sys.modules, 'tkinter was imported'\n"
            "print('OK', r.data['path'])\n")
        run = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=60,
                             env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.startswith("OK"), run.stdout)

    def test_filedump_with_tree_option_and_unknown_projection(self):
        self.compile()
        result = self.export("project_filedump_markdown", config.FILEDUMP_MD_SUFFIX, include_tree=True)
        text = Path(result.data["path"]).read_text(encoding="utf-8")
        self.assertIn("README.md", text)
        self.assertIn("alpha = 1", text)
        bad = self.export("project_tree_markdown", config.FILEDUMP_MD_SUFFIX)
        self.assertEqual((bad.status, bad.error["code"]), ("failed", "invalid_input"))


class G2FreshnessTests(ProjectCase):
    def assert_stale(self, change):
        self.compile()
        self.assertEqual(self.export().status, "succeeded")
        change()
        result = self.export()
        self.assertEqual((result.status, result.error["code"]), ("failed", "stale_snapshot"))
        self.assertEqual(self.app.execute("snapshot.require").error["code"], "stale_snapshot")

    def test_external_edit_requires_recapture(self):
        self.assert_stale(lambda: self.a.write_bytes(b"alpha = 2\n"))

    def test_external_addition_requires_recapture(self):
        self.assert_stale(lambda: (self.root / "src" / "new.py").write_bytes(b"x\n"))

    def test_external_deletion_requires_recapture(self):
        self.assert_stale(lambda: (self.root / "README.md").unlink())

    def test_recompile_makes_export_current_again(self):
        self.assert_stale(lambda: self.a.write_bytes(b"alpha = 2\n"))
        self.compile()
        self.assertEqual(self.export().status, "succeeded")


class G3ExistingSnapshotTests(ProjectCase):
    def rewrite_metadata(self, path, key, value):
        with contextlib.closing(sqlite3.connect(path)) as db:
            db.execute("UPDATE snapshot_metadata SET value = ? WHERE key = ?", (value, key))
            db.commit()

    def reopen_and_require(self):
        self.app.close()
        self.open_app()
        self.app.execute("project.scan")
        return self.app.execute("snapshot.require")

    def test_valid_snapshot_is_discovered_by_a_new_session(self):
        path = self.compile()
        result = self.reopen_and_require()
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertEqual(Path(result.data["path"]), path)

    def test_stale_snapshot_from_a_previous_session_is_refused(self):
        self.compile()
        self.a.write_bytes(b"changed while closed\n")
        self.assertEqual(self.reopen_and_require().error["code"], "stale_snapshot")

    def test_incompatible_schema_version_is_refused(self):
        path = self.compile()
        self.rewrite_metadata(path, "snapshot_schema_version", "99.0")  # stored as plain text
        result = self.reopen_and_require()
        self.assertEqual((result.status, result.error["code"]), ("failed", "stale_snapshot"))
        self.assertIn("format 99.0 is not supported", result.error["message"])

    def test_missing_signature_and_other_project_are_refused(self):
        path = self.compile()
        self.rewrite_metadata(path, "capture_signature", "")
        self.assertEqual(self.reopen_and_require().error["code"], "stale_snapshot")
        path = self.compile()
        self.rewrite_metadata(path, "source_root_absolute_path", str(self.root.parent))
        self.assertEqual(self.reopen_and_require().error["code"], "stale_snapshot")

    def test_corrupt_snapshot_file_is_refused_as_stale(self):
        path = self.compile()
        path.write_bytes(b"not a sqlite database at all")
        result = self.reopen_and_require()
        self.assertEqual((result.status, result.error["code"]), ("failed", "stale_snapshot"))
        self.assertIn("No readable snapshot", result.error["message"])


class G4FailureInjectionTests(ProjectCase):
    def manifest(self, *pairs):
        return json.dumps({"files": [{"path": p, "hunks": [{"search_block": o, "replace_block": n}]}
                                     for p, o, n in pairs]})

    def test_unreadable_target_at_validation_is_a_per_file_error(self):
        real = Path.read_bytes

        def guarded(path):
            if path.name == "a.py":
                raise PermissionError("injected: locked by another process")
            return real(path)
        with patch.object(Path, "read_bytes", guarded):
            result = self.app.execute("project_patch.validate", {"root": str(self.root), "manifest": self.manifest(
                ("src/a.py", "alpha = 1", "alpha = 2"), ("README.md", "# Demo", "# Demo!"))})
        self.assertEqual(result.status, "succeeded", result.error)
        self.assertFalse(result.data["valid"])
        statuses = {f["relative_path"]: f["status"] for f in result.data["files"]}
        self.assertEqual(statuses, {"src/a.py": "error", "README.md": "changed"})
        self.assertIn("locked", result.data["errors"][0])

    def test_unreadable_target_at_apply_stops_before_any_write(self):
        preview = self.app.execute("project_patch.validate", {"root": str(self.root), "manifest": self.manifest(
            ("README.md", "# Demo", "# Demo!"), ("src/a.py", "alpha = 1", "alpha = 2"))})
        real = Path.read_bytes

        def guarded(path):
            if path.name == "a.py":
                raise PermissionError("injected: locked")
            return real(path)
        pending = self.app.execute("project_patch.apply", {"plan_id": preview.data["plan_id"]})
        with patch.object(Path, "read_bytes", guarded):
            self.approve(pending.operation_id, True)
            result = self.app.dispatcher.wait(pending.operation_id)
        self.assertEqual(result.status, "failed")
        self.assertIn("locked", result.error["message"])
        self.assertEqual((self.root / "README.md").read_bytes(), b"# Demo\n")
        self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")
        self.assertEqual(list(self.root.rglob(".project-patch-*")), [])

    def test_chmod_failure_while_staging_leaves_target_and_no_scratch(self):
        with patch("projectmapper.core.writes.os.chmod", side_effect=PermissionError("injected chmod")):
            result = self.app.execute("text.save", {"path": str(self.a), "text": "alpha = 3\n", "sha256": sha(self.a)})
        self.assertEqual(result.status, "failed")
        self.assertIn("chmod", result.error["message"])
        self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")
        self.assertEqual([p.name for p in self.a.parent.iterdir()], ["a.py"])

    def test_scratch_cleanup_failure_is_reported_not_hidden(self):
        preview = self.app.execute("project_patch.validate", {"root": str(self.root), "manifest": self.manifest(
            ("README.md", "# Demo", "# Demo!"), ("src/a.py", "alpha = 1", "alpha = 2"))})
        real_replace, real_unlink = os.replace, Path.unlink

        def failing_replace(src, dst):
            if Path(dst).name == "a.py":
                raise PermissionError("injected replace failure")
            return real_replace(src, dst)

        def failing_unlink(path, missing_ok=False):
            if path.name.startswith(".project-patch-"):
                raise PermissionError("injected cleanup failure")
            return real_unlink(path, missing_ok=missing_ok)
        pending = self.app.execute("project_patch.apply", {"plan_id": preview.data["plan_id"]})
        with patch("projectmapper.tools.project_patcher.os.replace", side_effect=failing_replace), \
                patch.object(Path, "unlink", failing_unlink):
            self.approve(pending.operation_id, True)
            result = self.app.dispatcher.wait(pending.operation_id)
        self.assertEqual(result.status, "failed")
        message = result.error["message"]
        self.assertIn("injected replace failure", message, "the original failure is not hidden")
        self.assertIn("cleanup", message)
        self.assertEqual((self.root / "README.md").read_bytes(), b"# Demo\n", "rolled back")

    def test_single_file_scratch_cleanup_failure_does_not_mask_the_saved_result(self):
        session = PatchSession(self.a)
        real_unlink = Path.unlink

        def failing_unlink(path, missing_ok=False):
            if path.name.startswith(".patch-"):
                raise PermissionError("injected cleanup failure")
            return real_unlink(path, missing_ok=missing_ok)
        with patch("projectmapper.tools.patcher.os.replace", side_effect=PermissionError("injected replace")), \
                patch.object(Path, "unlink", failing_unlink):
            with self.assertRaises(PermissionError) as raised:
                session.save("alpha = 4\n")
        self.assertIn("injected replace", str(raised.exception), "the primary failure is what is reported")
        self.assertEqual(self.a.read_bytes(), b"alpha = 1\n")


class G5CancellationDuringApplyTests(ProjectCase):
    def test_cancel_request_during_apply_reaches_a_consistent_truthful_end(self):
        preview = self.app.execute("project_patch.validate", {"root": str(self.root), "manifest": json.dumps(
            {"files": [{"path": p, "hunks": [{"search_block": o, "replace_block": n}]}
                       for p, o, n in (("README.md", "# Demo", "# Demo!"), ("src/a.py", "alpha = 1", "alpha = 2"))]})})
        pending = self.app.execute("project_patch.apply", {"plan_id": preview.data["plan_id"]})
        real = os.replace
        cancelled = []

        def replace_then_cancel(src, dst):
            if not cancelled:
                cancelled.append(self.app.dispatcher.cancel(pending.operation_id).status)
            return real(src, dst)
        with patch("projectmapper.tools.project_patcher.os.replace", side_effect=replace_then_cancel):
            self.approve(pending.operation_id, True)
            result = self.app.dispatcher.wait(pending.operation_id)
        both = ((self.root / "README.md").read_bytes(), self.a.read_bytes())
        # Once replacement starts the batch must finish or recover; never stop half-applied.
        self.assertIn(both, {(b"# Demo!\n", b"alpha = 2\n"), (b"# Demo\n", b"alpha = 1\n")})
        if both[0] == b"# Demo!\n":
            self.assertEqual(result.status, "succeeded", "writes happened, so success is the truthful outcome")
        else:
            self.assertIn(result.status, ("cancelled", "failed"))
        history = self.app.execute("history.query", {"text": "project_patch.apply"}).data["operations"]
        self.assertEqual(history[0]["status"], result.status)


class G6DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()

    def check(self, report, name):
        (item,) = [c for c in report["checks"] if c["name"] == name]
        return item

    def test_healthy_report(self):
        from types import SimpleNamespace
        report = collect_diagnostics(SimpleNamespace(selected_root=self.root,
                                                     get_output_dir=lambda: self.root / "_projectmapper"))
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["failed"], 0)

    def test_unwritable_output_and_missing_root_are_reported(self):
        from types import SimpleNamespace
        blocker = self.root / "output-is-a-file"
        blocker.write_bytes(b"x")
        report = collect_diagnostics(SimpleNamespace(selected_root=self.root / "missing",
                                                     get_output_dir=lambda: blocker))
        self.assertFalse(report["ok"])
        self.assertFalse(self.check(report, "Project root")["ok"])
        self.assertFalse(self.check(report, "Output directory writable")["ok"])
        self.assertEqual(report["failed"], 2)
        self.assertEqual(blocker.read_bytes(), b"x", "diagnostics never overwrites what it probes")

    def test_sqlite_failure_is_reported(self):
        from types import SimpleNamespace
        with patch("projectmapper.core.diagnostics.sqlite3.connect", side_effect=RuntimeError("no sqlite")):
            report = collect_diagnostics(SimpleNamespace(selected_root=self.root,
                                                         get_output_dir=lambda: self.root / "_projectmapper"))
        self.assertFalse(self.check(report, "SQLite runtime")["ok"])
        self.assertIn("no sqlite", self.check(report, "SQLite runtime")["detail"])


if __name__ == "__main__":
    unittest.main()
