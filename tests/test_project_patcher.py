from pathlib import Path
import json
import tkinter as tk
import unittest
from unittest.mock import patch
from tests.support import temporary_directory, tk_root

from src.tools.patcher import PatchError
from src.tools.project_patcher import ProjectPatchSession, project_patch_diff
from src.app import ProjectMapperApp


class ProjectPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.root = Path(self.temp.name).resolve()
        (self.root / "README.md").write_text("# ProjectMapper Snapshot Compiler\n", encoding="utf-8")
        (self.root / "requirements.txt").write_text("tk>=0.1.0\n", encoding="utf-8")

    def test_validates_multiple_files_against_original_source(self):
        manifest = {"version": 1, "files": [
            {"path": "README.md", "hunks": [{"search_block": "# ProjectMapper Snapshot Compiler",
                                                "replace_block": "# ProjectMapper Snapshot Compiler"}]},
            {"path": "requirements.txt", "hunks": [{"search_block": "tk>=0.1.0",
                                                       "replace_block": "tk>=0.1.0"}]},
        ]}
        session = ProjectPatchSession(self.root, manifest)
        results = session.validate_all()
        self.assertEqual([r["relative_path"] for r in results], ["README.md", "requirements.txt"])
        self.assertEqual(project_patch_diff(results), "(No differences)")

    def test_rejects_duplicates_traversal_parts_missing_and_binary(self):
        cases = [
            {"files": [{"path": "README.md", "hunks": [{"search_block": "a", "replace_block": "b"}]},
                       {"path": "README.md", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"files": [{"path": "../README.md", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"files": [{"path": ".parts/reference.py", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"files": [{"path": "missing.txt", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
        ]
        for manifest in cases:
            with self.subTest(manifest=manifest), self.assertRaises(PatchError):
                ProjectPatchSession(self.root, manifest)

    def test_hash_mismatch_stops_before_apply(self):
        manifest = {"files": [{"path": "README.md", "sha256": "0" * 64,
                                "hunks": [{"search_block": "# ProjectMapper Snapshot Compiler",
                                            "replace_block": "changed"}]}]}
        session = ProjectPatchSession(self.root, manifest)
        with self.assertRaisesRegex(PatchError, "Source changed"):
            session.validate_all()

    def test_project_window_has_preview_and_linked_actions(self):
        root = tk_root(self)
        root.withdraw()
        app = ProjectMapperApp(root)
        for timer in root.tk.call("after", "info"):
            root.after_cancel(timer)
        window = app.open_project_patcher(self.root)
        try:
            manifest = {"version": 1, "files": [{"path": "README.md", "hunks": [
                {"search_block": "# ProjectMapper Snapshot Compiler",
                 "replace_block": "# ProjectMapper Snapshot Compiler"}]}]}
            window.manifest_box.delete("1.0", "end")
            window.manifest_box.insert("1.0", json.dumps(manifest))
            window.manifest_box.edit_modified(False)
            self.assertTrue(window.validate())
            self.assertIn("No differences", window.diff_box.get("1.0", "end-1c"))
            window.link_button.invoke()
            self.assertTrue(window.actions_linked)
            self.assertEqual(str(window.apply_button["state"]), "normal")
        finally:
            window.top.destroy()


if __name__ == "__main__":
    unittest.main()
