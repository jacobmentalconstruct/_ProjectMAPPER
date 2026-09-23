import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests.support import temporary_directory, tk_root
from projectmapper import app as app_module
from projectmapper.core import config, exports


REPO = Path(__file__).resolve().parents[1]


class EntryPointTests(unittest.TestCase):
    def test_version_flag(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
            app_module.main(["--version"])
        self.assertEqual(exit_.exception.code, 0)
        self.assertIn(config.APP_VERSION, out.getvalue())

    def test_missing_folder_is_rejected_before_gui(self):
        with patch.object(app_module, "run_gui") as run_gui, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_:
            app_module.main([str(REPO / "no-such-folder")])
        self.assertEqual(exit_.exception.code, 2)
        run_gui.assert_not_called()

    def test_folder_argument_and_default(self):
        temp = temporary_directory(self)
        with patch.object(app_module, "run_gui") as run_gui:
            app_module.main([temp.name])
            app_module.main([])
        self.assertEqual(run_gui.call_args_list[0].args, (Path(temp.name),))
        self.assertEqual(run_gui.call_args_list[1].args, (None,))

    def test_module_entry_runs_from_src_layout(self):
        run = subprocess.run([sys.executable, "-B", "-m", "projectmapper", "--version"],
                             capture_output=True, text=True, timeout=20,
                             env={**os.environ, "PYTHONPATH": str(REPO / "src")})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(config.APP_VERSION, run.stdout)


class StartupRootTests(unittest.TestCase):
    def setUp(self):
        self.root = tk_root(self)
        self.root.withdraw()

    def make_app(self, initial_root):
        app = app_module.ProjectMapperApp(self.root, initial_root)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.addCleanup(app.controller.close)
        return app

    def test_explicit_root(self):
        folder = Path(temporary_directory(self).name).resolve()
        app = self.make_app(folder)
        self.assertEqual(app.controller.state.root, folder)
        self.assertEqual(app.widgets["selected_root_var"].get(), str(folder))

    def test_default_root_is_working_directory_not_package(self):
        app = self.make_app(None)
        self.assertEqual(app.controller.state.root, Path.cwd().resolve())
        self.assertNotEqual(app.controller.state.root, config.APP_DIR)


class SourceCheckoutTests(unittest.TestCase):
    def test_checkout_root_detected(self):
        self.assertEqual(config.SOURCE_ROOT, REPO)

    def test_installed_layout_has_no_source_root(self):
        installed = REPO / "no-such-env" / "Lib" / "site-packages" / "projectmapper"
        with patch.object(config, "APP_DIR", installed):
            self.assertIsNone(config._source_checkout_root())

    def test_build_metadata_never_vendored(self):
        self.assertTrue(exports.is_vendor_export_excluded(Path("projectmapper.egg-info"))[0])

    def test_vendored_batch_files_use_crlf(self):
        folder = Path(temporary_directory(self).name)
        source, target = folder / "lf.bat", folder / "out" / "lf.bat"
        source.write_bytes(b"@echo off\necho one\r\necho two\n")
        exports.copy_vendor_tree(source, target, [], [])
        self.assertEqual(target.read_bytes(), b"@echo off\r\necho one\r\necho two\r\n")

    def test_vendor_export_refused_without_checkout(self):
        with patch.object(exports, "SOURCE_ROOT", None), self.assertRaisesRegex(RuntimeError, "source checkout"):
            exports.create_vendor_export(export_root=Path(temporary_directory(self).name))


if __name__ == "__main__":
    unittest.main()
