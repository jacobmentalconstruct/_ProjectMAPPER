"""Snapshot publication is bound to the bytes actually captured (ABA regressions).

Changes are injected through the compiler's database-insert helpers, which run after
the signature pass (tree rows) and after the file capture loop (outputs). This keeps
the injection independent of how files are read.
"""

import contextlib
import hashlib
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from tests.support import temporary_directory
from projectmapper.application.controller import create_application
from projectmapper.core import snapshots
from projectmapper.core.config import S_CHECKED
from projectmapper.core.exclusions import ExclusionPolicy
from projectmapper.core.tree import scan_project_tree


SNIFFED = b"ab" + bytes(1) + b"cd"
A, B = b"alpha\r\n", b"bravo\r\n"


@contextlib.contextmanager
def change_during_capture(path, captured, final=None):
    """Write `captured` once the signature pass is done, then `final` before the recheck."""
    tree_row, output = snapshots.insert_project_tree_row, snapshots.insert_snapshot_output
    state = {"tree": False, "output": False}

    def on_tree_row(*args, **kwargs):
        if not state["tree"]:
            state["tree"] = True
            path.write_bytes(captured)
        return tree_row(*args, **kwargs)

    def on_output(*args, **kwargs):
        if final is not None and not state["output"]:
            state["output"] = True
            path.write_bytes(final)
        return output(*args, **kwargs)

    with patch.object(snapshots, "insert_project_tree_row", on_tree_row), \
            patch.object(snapshots, "insert_snapshot_output", on_output):
        yield state


class SnapshotBindingTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(temporary_directory(self).name).resolve()
        self.text = self.root / "a.txt"
        self.text.write_bytes(A)
        self.output = self.root / "_projectmapper"
        self.policy = ExclusionPolicy()

    def compile(self, include_binary=False):
        rows, skipped = scan_project_tree(self.root, self.policy)
        selection = {str(r["path"]): S_CHECKED for r in rows}
        return snapshots.compile_snapshot(self.root, self.output, rows, selection, self.policy,
                                          skipped, include_binary_blobs=include_binary)

    def assert_refused_and_preserved(self, previous, include_binary=False, final=A, target=None):
        target = target or self.text
        before = previous.read_bytes()
        with change_during_capture(target, B if target is self.text else b"\0B", final) as state:
            with self.assertRaises(snapshots.SnapshotSourceChanged):
                self.compile(include_binary)
        self.assertTrue(state["tree"])
        self.assertEqual(previous.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), [previous.name])

    def test_unchanged_project_publishes_and_verifies(self):
        snapshot = self.compile()
        rows, _ = scan_project_tree(self.root, self.policy)
        selection = {str(r["path"]): S_CHECKED for r in rows}
        self.assertTrue(snapshots.snapshot_matches(snapshot, self.root, self.policy, selection))
        with contextlib.closing(sqlite3.connect(snapshot)) as conn:
            self.assertEqual(conn.execute("SELECT content FROM project_files").fetchone(), ("alpha\n",))

    def test_text_changed_and_restored_during_capture_is_refused(self):
        # A (signature) -> B (captured) -> A (recheck): previously published B as fresh.
        self.assert_refused_and_preserved(self.compile())

    def test_text_changed_and_left_during_capture_is_refused(self):
        self.assert_refused_and_preserved(self.compile(), final=None)

    def test_blob_changed_and_restored_during_capture_is_refused(self):
        blob = self.root / "data.bin"
        blob.write_bytes(b"\0A")
        previous = self.compile(include_binary=True)
        self.assert_refused_and_preserved(previous, include_binary=True, final=b"\0A", target=blob)

    def test_sniffed_binary_blob_is_stored_from_hashed_bytes(self):
        sniffed = self.root / "sniffed.txt"  # binary by content, not by extension
        sniffed.write_bytes(SNIFFED)
        snapshot = self.compile(include_binary=True)
        with contextlib.closing(sqlite3.connect(snapshot)) as conn:
            row = conn.execute("SELECT blob_content, sha256 FROM project_blobs").fetchone()
            reason = conn.execute("SELECT skip_reason FROM snapshot_skipped_paths "
                                  "WHERE relative_path = 'sniffed.txt'").fetchone()
        self.assertEqual(row, (SNIFFED, hashlib.sha256(SNIFFED).hexdigest()))
        self.assertEqual(reason, ("binary_detected",))

    def test_controller_reports_source_changed(self):
        controller, _ = create_application(self.root)
        self.addCleanup(controller.close)
        with change_during_capture(self.text, B, A):
            result = controller.execute("snapshot.compile")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "source_changed")
        self.assertIsNone(controller.state_view()["snapshot_path"])


if __name__ == "__main__":
    unittest.main()
