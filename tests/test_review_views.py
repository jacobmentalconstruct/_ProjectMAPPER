"""Shared review views: unified-diff line classification and themed highlighting."""

import difflib
import json
from pathlib import Path
import unittest

from tests.support import temporary_directory, tk_root
from projectmapper.core.diff import DiffFile, diff_line_kinds, unified_diff_text


def udiff(original, patched, name="f.sql"):
    return "\n".join(difflib.unified_diff(original.splitlines(), patched.splitlines(),
                                          fromfile=name, tofile=name, lineterm=""))


class DiffLineKindTests(unittest.TestCase):
    def test_headers_hunks_additions_removals_and_context(self):
        text = udiff("keep\nold\n", "keep\nnew\n")
        self.assertEqual(text.split("\n"), ["--- f.sql", "+++ f.sql", "@@ -1,2 +1,2 @@",
                                            " keep", "-old", "+new"])
        self.assertEqual(diff_line_kinds(text), ["header", "header", "hunk", None, "remove", "add"])

    def test_content_that_looks_like_headers_is_classified_by_hunk_counts(self):
        # Removing "-- comment" renders as "--- comment"; adding "++ x" renders as "+++ x".
        text = udiff("-- comment\nselect 1;\n", "++ x\nselect 1;\n")
        lines = text.split("\n")
        self.assertIn("--- comment", lines)
        self.assertIn("+++ x", lines)
        kinds = dict(zip(lines, diff_line_kinds(text)))
        self.assertEqual(kinds["--- comment"], "remove")
        self.assertEqual(kinds["+++ x"], "add")
        self.assertEqual(diff_line_kinds(text)[:2], ["header", "header"])

    def test_omitted_and_zero_counts(self):
        self.assertEqual(diff_line_kinds("@@ -1 +1 @@\n-a\n+b"), ["hunk", "remove", "add"])
        self.assertEqual(diff_line_kinds("@@ -0,0 +1,2 @@\n+a\n+b\n--- next"),
                         ["hunk", "add", "add", "header"])

    def test_multi_file_diff_and_no_differences(self):
        text = unified_diff_text([DiffFile("a.py", "x\n", "y\n"), DiffFile("b.py", "p\n", "q\n")])
        kinds = diff_line_kinds(text)
        self.assertEqual(kinds.count("header"), 4)
        self.assertEqual(kinds.count("hunk"), 2)
        self.assertEqual(diff_line_kinds("(No differences)"), [None])


class HighlightedPatcherTests(unittest.TestCase):
    def test_single_file_diff_is_highlighted_with_theme_tokens(self):
        from projectmapper.app import ProjectMapperApp
        folder = Path(temporary_directory(self).name).resolve()
        target = folder / "t.py"
        target.write_bytes(b"keep\nold\n")
        root = tk_root(self)
        root.withdraw()
        app = ProjectMapperApp(root, folder)
        for timer in root.tk.call("after", "info"):
            root.after_cancel(timer)
        window = app.open_tokenizing_patcher(target)
        self.addCleanup(window.top.destroy)
        window.patch_box.delete("1.0", "end")
        window.patch_box.insert("1.0", json.dumps({"hunks": [{"search_block": "old", "replace_block": "new"}]}))
        self.assertTrue(window.validate())
        box = window.diff_box
        for tag, line in (("diff_header", 1), ("diff_header", 2), ("diff_hunk", 3),
                          ("diff_remove", 5), ("diff_add", 6)):
            ranges = [str(index) for index in box.tag_ranges(tag)]
            self.assertIn(f"{line}.0", ranges, tag)
            self.assertEqual(box.tag_cget(tag, "foreground"), app.theme[tag])
        self.assertNotIn("4.0", [str(i) for tag in ("diff_add", "diff_remove") for i in box.tag_ranges(tag)])
        self.assertEqual(str(box["state"]), "disabled")


if __name__ == "__main__":
    unittest.main()
