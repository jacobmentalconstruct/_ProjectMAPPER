from pathlib import Path
import json
import unittest
from tests.support import temporary_directory, tk_root

from projectmapper.application.controller import create_application
from projectmapper.tools.patcher import PatchError
from projectmapper.tools.project_patcher import ProjectPatchSession, project_patch_diff
from projectmapper.app import ProjectMapperApp


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

    def test_v2_manifest_reviews_and_applies_mixed_project_operations(self):
        manifest = {"version": 2, "description": "mixed transform", "ops": [
            {"op": "patch", "path": "README.md", "hunks": [
                {"search_block": "# ProjectMapper Snapshot Compiler",
                 "replace_block": "# ProjectMapper Project Mapper"}]},
            {"op": "mkdir", "path": "src"},
            {"op": "create", "path": "src/new.py", "content": "value = 1\n"},
            {"op": "move", "from": "requirements.txt", "to": "src/requirements.txt"},
        ]}
        session = ProjectPatchSession(self.root, manifest)
        outcomes = session.review()
        self.assertTrue(all(item["status"] == "ready" for item in outcomes), outcomes)
        self.assertIn("MKDIR src", project_patch_diff(outcomes))
        records = []

        session.apply_all(record=lambda items, changeset: records.append(changeset),
                          recover=lambda _items: "recovery")

        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"),
                         "# ProjectMapper Project Mapper\n")
        self.assertEqual((self.root / "src/new.py").read_bytes(), b"value = 1\n")
        self.assertEqual((self.root / "src/requirements.txt").read_text(encoding="utf-8"),
                         "tk>=0.1.0\n")
        self.assertFalse((self.root / "requirements.txt").exists())
        self.assertEqual(records[0]["forward"]["version"], 2)

    def test_v1_review_refuses_what_apply_would_refuse(self):
        hunk = {"search_block": "tk>=0.1.0", "replace_block": "tk>=0.2.0"}
        cases = {
            "unknown entry field": {"files": [{"path": "requirements.txt", "oops": True, "hunks": [hunk]}]},
            "unknown top-level field": {"files": [{"path": "requirements.txt", "hunks": [hunk]}], "oops": 1},
            "hunk without replacement": {"files": [{"path": "requirements.txt",
                                                    "hunks": [{"search_block": "tk>=0.1.0"}]}]},
            "non-bool indent flag": {"files": [{"path": "requirements.txt",
                                                "hunks": [dict(hunk, use_patch_indent="no")]}]},
        }
        for label, manifest in cases.items():
            with self.subTest(label), self.assertRaises(PatchError):
                ProjectPatchSession(self.root, {"version": 1, **manifest})
        self.assertEqual((self.root / "requirements.txt").read_text(encoding="utf-8"), "tk>=0.1.0\n")

    def test_v1_with_description_and_optional_sha_still_validates_and_applies(self):
        import hashlib
        digest = hashlib.sha256((self.root / "requirements.txt").read_bytes()).hexdigest()
        session = ProjectPatchSession(self.root, {"version": 1, "description": "bump", "files": [
            {"path": "requirements.txt", "sha256": digest,
             "hunks": [{"description": "x", "search_block": "tk>=0.1.0", "replace_block": "tk>=0.2.0"}]}]})
        self.assertEqual(session.review()[0]["status"], "changed")
        session.apply_all()
        self.assertEqual((self.root / "requirements.txt").read_text(encoding="utf-8"), "tk>=0.2.0\n")

    def test_project_schema_returns_version_2_changeset_example(self):
        app, _ = create_application(self.root)
        self.addCleanup(app.close)
        result = app.execute("patch.schema", {"project": True})
        self.assertEqual(json.loads(result.data["text"])["version"], 2)

    def test_rejects_duplicates_traversal_parts_missing_and_binary(self):
        cases = [
            {"files": [{"path": "README.md", "hunks": [{"search_block": "a", "replace_block": "b"}]},
                       {"path": "README.md", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"files": [{"path": "../README.md", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"files": [{"path": ".parts/reference.py", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"files": [{"path": ".git/config", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"files": [{"path": "src/.HG/config", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
            {"files": [{"path": ".SVN/entries", "hunks": [{"search_block": "a", "replace_block": "b"}]}]},
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

    def test_repository_ancestor_named_like_output_folder_does_not_block_target(self):
        nested = self.root / "nested-project"
        nested.mkdir()
        (nested / "file.txt").write_bytes(b"old\n")
        session = ProjectPatchSession(nested, {"files": [{"path": "file.txt", "hunks": [
            {"search_block": "old", "replace_block": "new"},
        ]}]})

        self.assertEqual(session.validate_all()[0]["patched"], "new\n")

    def test_apply_preserves_bom_mixed_line_endings_and_relative_indentation(self):
        original = b"\xef\xbb\xbfhead\r\n\told\rchild\nlast"
        target = self.root / "mixed.py"
        target.write_bytes(original)
        session = ProjectPatchSession(self.root, {"files": [{"path": "mixed.py", "hunks": [
            {"search_block": "old", "replace_block": "    new\n        nested"}
        ]}]})

        (result,) = session.validate_all()
        self.assertEqual(result["patched"], "head\r\n\tnew\r\t    nested\rchild\nlast")
        session.apply_all()

        self.assertEqual(target.read_bytes(),
                         b"\xef\xbb\xbfhead\r\n\tnew\r\t    nested\rchild\nlast")

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
