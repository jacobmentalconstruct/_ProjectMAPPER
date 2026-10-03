"""The console adapter is exercised through its actual Python module entry point."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tests.support import temporary_directory


SRC = Path(__file__).resolve().parents[1] / "src"


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        base = Path(self.temp.name).resolve()
        self.root = base / "project"
        self.root.mkdir()
        (self.root / "app.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "skip.log").write_text("log\n", encoding="utf-8")
        self.manifest = base / "manifest.json"
        self.patch = base / "patch.json"

    def run_cli(self, *args):
        env = {**os.environ, "PYTHONPATH": str(SRC)}
        return subprocess.run([sys.executable, "-B", "-m", "projectmapper.cli", *map(str, args)],
                              cwd=self.root, env=env, capture_output=True, text=True, timeout=30)

    def json_result(self, process):
        self.assertTrue(process.stdout, process.stderr)
        return json.loads(process.stdout)

    def test_help_and_module_import_do_not_load_tk(self):
        process = subprocess.run([sys.executable, "-B", "-c",
                                  "import sys; import projectmapper.cli; assert 'tkinter' not in sys.modules"],
                                 cwd=self.root, env={**os.environ, "PYTHONPATH": str(SRC)},
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        help_result = self.run_cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("projectmapper-cli", help_result.stdout)
        self.assertNotIn("--approve", help_result.stdout)

    def test_scan_accepts_shared_options_before_and_after_command(self):
        process = self.run_cli("--root", self.root, "--exclude", "*.log", "scan", "--text")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn("Entries: 2", process.stdout)
        self.assertIn("app.py", process.stdout)
        self.assertNotIn("skip.log", process.stdout)
        structured = self.run_cli("tree", "--root", self.root, "--json")
        self.assertEqual(structured.returncode, 0, structured.stderr)
        self.assertEqual(self.json_result(structured)["exit_code"], 0)

    def test_compile_and_export_create_only_snapshot_outputs(self):
        compiled = self.run_cli("compile", "--root", self.root)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        compiled_result = self.json_result(compiled)
        snapshot = Path(compiled_result["data"]["path"])
        self.assertTrue(snapshot.is_file())
        exported = self.run_cli("export", "tree", "--root", self.root, "--text")
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        self.assertTrue((self.root / "_projectmapper" / "project_project_tree.md").is_file())
        self.assertTrue((self.root / "app.py").is_file())

    def test_validate_commands_report_proposals_without_writing_project_files(self):
        self.patch.write_text(json.dumps({"hunks": [{"search_block": "value = 1",
                                                       "replace_block": "value = 2"}]}), encoding="utf-8")
        single = self.run_cli("validate-patch", "app.py", self.patch, "--root", self.root)
        self.assertEqual(single.returncode, 0, single.stderr)
        single_result = self.json_result(single)
        self.assertEqual(single_result["status"], "succeeded")
        self.assertTrue(single_result["data"].get("plan_id"))
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "value = 1\n")

    def test_apply_commands_use_the_trusted_approver_for_single_and_multi_file_changes(self):
        from projectmapper.adapters.session import AdapterSession
        from projectmapper.cli import _run_command, build_parser
        from projectmapper.core.settings import Settings

        self.patch.write_text(json.dumps({"hunks": [{"search_block": "value = 1",
                                                        "replace_block": "value = 2"}]}), encoding="utf-8")
        decisions = []

        def approve(request):
            decisions.append(request)
            return True

        session = AdapterSession(self.root, "cli", approver=approve, settings=Settings())
        try:
            args = build_parser().parse_args(["apply-patch", "app.py", str(self.patch), "--root", str(self.root)])
            result = _run_command(session, args)
            self.assertEqual((result["status"], result["exit_code"]), ("succeeded", 0))
            self.assertIn("+value = 2", decisions[0].diff)
            self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "value = 2\n")

            (self.root / "app.py").write_text("value = 1\n", encoding="utf-8")
            self.manifest.write_text(json.dumps({"files": [{"path": "app.py", "hunks": [
                {"search_block": "value = 1", "replace_block": "value = 3"}]}]}), encoding="utf-8")
            args = build_parser().parse_args(["apply-project", str(self.manifest), "--root", str(self.root)])
            result = _run_command(session, args)
            self.assertEqual((result["status"], result["exit_code"]), ("succeeded", 0))
            self.assertEqual(decisions[1].action, "project_patch.apply")
            self.assertIn("+value = 3", decisions[1].diff)
            self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "value = 3\n")
        finally:
            session.close()

        (self.root / "app.py").write_text("value = 1\n", encoding="utf-8")
        self.manifest.write_text(json.dumps({"files": [{"path": "app.py", "hunks": [
            {"search_block": "value = 1", "replace_block": "value = 3"}]}]}), encoding="utf-8")
        project = self.run_cli("validate-project", self.manifest, "--root", self.root)
        self.assertEqual(project.returncode, 0, project.stderr)
        project_result = self.json_result(project)
        self.assertEqual(project_result["status"], "succeeded")
        self.assertTrue(project_result["data"].get("plan_id"))
        self.assertEqual((self.root / "app.py").read_text(encoding="utf-8"), "value = 1\n")

        invalid_manifest = self.root / "missing-file-manifest.json"
        invalid_manifest.write_text(json.dumps({"files": [{"path": "missing.py", "hunks": []}]}),
                                    encoding="utf-8")
        invalid = self.run_cli("validate-project", invalid_manifest, "--root", self.root)
        self.assertEqual(invalid.returncode, 2, invalid.stdout + invalid.stderr)
        invalid_result = self.json_result(invalid)
        self.assertIn("data", invalid_result, invalid.stdout)
        self.assertFalse(invalid_result["data"].get("valid", False), invalid.stdout)
        self.assertIsNone(invalid_result["data"].get("plan_id"), invalid.stdout)

    def test_stale_and_invalid_input_exit_codes_are_stable(self):
        stale_export = self.run_cli("export", "tree", "--root", self.root)
        self.assertEqual(stale_export.returncode, 3)
        self.assertEqual(self.json_result(stale_export)["error"]["code"], "stale_snapshot")

        bad_json = self.run_cli("validate-project", self.manifest, "--root", self.root)
        self.assertEqual(bad_json.returncode, 2)
        self.assertEqual(self.json_result(bad_json)["error"]["code"], "invalid_input")

        usage = self.run_cli("no-such-command")
        self.assertEqual(usage.returncode, 2)
        self.assertEqual(self.json_result(usage)["exit_code"], 2)

        outside_file = self.root.parent / "outside.py"
        outside_file.write_text("value = 1\n", encoding="utf-8")
        self.patch.write_text("{}", encoding="utf-8")
        unsafe = self.run_cli("validate-patch", outside_file, self.patch, "--root", self.root)
        self.assertEqual(unsafe.returncode, 5)
        self.assertEqual(self.json_result(unsafe)["error"]["code"], "unsafe_path")

    def test_approval_and_cancellation_exit_codes_are_reserved(self):
        from projectmapper.cli import exit_code

        self.assertEqual(exit_code({"status": "approval_required", "error": {"code": "approval_required"}}), 4)
        self.assertEqual(exit_code({"status": "cancelled", "error": {"code": "cancelled"}}), 130)

    def test_history_and_binary_option_are_supported(self):
        compiled = self.run_cli("compile", "--root", self.root, "--include-binary")
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        history = self.run_cli("history", "--root", self.root, "--limit", "10")
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertIn("operations", self.json_result(history)["data"])


if __name__ == "__main__":
    unittest.main()
