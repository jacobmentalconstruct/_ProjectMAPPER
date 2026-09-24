"""Every error code in the source has human wording; the desktop shows "Label: detail"."""

import ast
import hashlib
from pathlib import Path
import unittest

from tests.support import temporary_directory, tk_root
from projectmapper.application import errors
from projectmapper.app import ProjectMapperApp
from projectmapper.tools.patcher import PatchError

SRC = Path(__file__).resolve().parents[1] / "src"


def _literals(node):
    """String constants a code expression can evaluate to: literals and both arms of `a if c else b`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.IfExp):
        return _literals(node.body) + _literals(node.orelse)
    return []  # calls, names, lookups read codes; they do not define them


def codes_in(source):
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and node.args and \
                getattr(node.func, "id", getattr(node.func, "attr", None)) == "ActionError":
            found.update(_literals(node.args[0]))
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "code" and value is not None:
                    found.update(_literals(value))
    return found


def all_source_codes():
    found = set()
    for path in SRC.rglob("*.py"):
        found |= codes_in(path.read_text(encoding="utf-8"))
    return found


class CatalogueTests(unittest.TestCase):
    def test_every_code_in_the_source_has_a_label(self):
        codes = all_source_codes()
        self.assertGreaterEqual(len(codes), 18, sorted(codes))
        self.assertEqual(sorted(codes - set(errors.LABELS)), [])

    def test_scanner_catches_new_and_conditional_codes(self):
        sample = ('raise ActionError("brand_new", "x")\n'
                  'raise ActionError("a_code" if ok else "b_code", "y")\n'
                  'err = {"code": "dict_code", "message": "m"}\n'
                  'read = {"code": str(e.get("code", ""))}\n')
        self.assertEqual(codes_in(sample), {"brand_new", "a_code", "b_code", "dict_code"})

    def test_no_stale_labels(self):
        self.assertEqual(sorted(set(errors.LABELS) - all_source_codes()), [])

    def test_describe(self):
        self.assertEqual(errors.describe({"code": "source_changed", "message": "a.txt changed."}),
                         "The file changed on disk: a.txt changed.")
        self.assertEqual(errors.describe({"code": "mystery", "message": "x"}), "Operation failed: x")
        self.assertEqual(errors.describe({"code": "cancelled"}), "Cancelled")
        self.assertEqual(errors.describe(None), "Operation failed")


class DesktopWordingTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(temporary_directory(self).name).resolve()
        self.path = self.folder / "a.txt"
        self.path.write_bytes(b"v1\n")
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root, self.folder)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)

    def test_action_failures_read_label_then_detail(self):
        with self.assertRaises(PatchError) as raised:
            self.app.action("text.save", {"path": str(self.path), "text": "v2\n", "sha256": "0" * 64})
        self.assertTrue(str(raised.exception).startswith("The file changed on disk: "), str(raised.exception))

    def test_rejected_requests_read_label_then_detail(self):
        with self.assertRaises(PatchError) as raised:
            self.app.action("no.such_action")
        self.assertTrue(str(raised.exception).startswith("Invalid request: "), str(raised.exception))

    def test_engine_rejections_are_invalid_input_not_generic_failures(self):
        import json
        for manifest in ("{not json", json.dumps({"files": [{"path": "../x", "hunks": [
                {"search_block": "a", "replace_block": "b"}]}]})):
            with self.subTest(manifest=manifest[:12]):
                result = self.app.controller.execute("project_patch.validate",
                                                     {"root": str(self.folder), "manifest": manifest})
                self.assertEqual(result.error["code"], "invalid_input")
                self.assertTrue(errors.describe(result.error).startswith("Invalid request: "))

    def test_unexpected_exceptions_stay_generic(self):
        from unittest.mock import patch
        with patch.object(self.app.controller, "state_view", side_effect=RuntimeError("boom")):
            result = self.app.controller.execute("state.get")
        self.assertEqual((result.error["code"], errors.describe(result.error)), ("action_failed", "Operation failed: boom"))

    def test_failed_operations_are_logged_with_their_label(self):
        digest = hashlib.sha256(b"other").hexdigest()
        self.app.controller.execute("text.save", {"path": str(self.path), "text": "v2\n", "sha256": digest})
        while not self.app.gui_queue.empty():
            self.app.gui_queue.get_nowait()()
        log = self.app.widgets["log_box"].get("1.0", "end-1c")
        self.assertIn("[ERROR] The file changed on disk: ", log)


if __name__ == "__main__":
    unittest.main()
