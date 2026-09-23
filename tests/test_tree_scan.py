import stat
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.support import temporary_directory
from src.core.exclusions import ExclusionPolicy
from src.core.tree import scan_project_tree


class TreeScanTests(unittest.TestCase):
    def setUp(self):
        self.fixture = temporary_directory(self)
        self.folder = Path(self.fixture.name).resolve()
        (self.folder / "nested").mkdir()
        (self.folder / "nested" / "a.txt").write_bytes(b"abc")
        (self.folder / "b.txt").write_bytes(b"four")

    def test_metadata_only_size_aggregation_and_external_rescan(self):
        with patch.object(Path, "open", side_effect=AssertionError("read content")):
            rows, skipped = scan_project_tree(self.folder, ExclusionPolicy())
        self.assertEqual(rows[0]["size_bytes"], 7)
        self.assertEqual(rows[1]["size_bytes"], 3)
        self.assertEqual(skipped, [])
        (self.folder / "nested" / "a.txt").unlink()
        (self.folder / "new.txt").write_bytes(b"hello")
        rows, _ = scan_project_tree(self.folder, ExclusionPolicy())
        self.assertEqual(rows[0]["size_bytes"], 9)
        self.assertNotIn("nested/a.txt", [row["relative_path"] for row in rows])

    def test_cancellation_acknowledged_during_enumeration(self):
        stop = threading.Event()
        policy = ExclusionPolicy()
        def cancel(*args):
            stop.set()
            return False, None
        with patch.object(policy, "should_exclude_entry", side_effect=cancel):
            started = time.perf_counter()
            rows, _ = scan_project_tree(self.folder, policy, stop)
        self.assertLess(time.perf_counter() - started, 1)
        self.assertEqual(len(rows), 1)

    def test_inaccessible_directory_is_recorded(self):
        with patch("src.core.tree.os.scandir", side_effect=PermissionError("denied")):
            rows, skipped = scan_project_tree(self.folder, ExclusionPolicy())
        self.assertEqual(len(rows), 1)
        self.assertEqual(skipped[0]["skip_reason"], "permission_denied")

    def test_links_and_junction_metadata_are_not_traversed(self):
        entries = [SimpleNamespace(name="link", stat=lambda **kw: SimpleNamespace(st_mode=stat.S_IFLNK)),
                   SimpleNamespace(name="junction", stat=lambda **kw: SimpleNamespace(
                       st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT))]
        with patch("src.core.tree.os.scandir") as scandir:
            scandir.return_value.__enter__.return_value = iter(entries)
            rows, skipped = scan_project_tree(self.folder, ExclusionPolicy())
        self.assertEqual(len(rows), 1)
        self.assertEqual([entry["skip_reason"] for entry in skipped], ["symlink", "reparse_point"])
        self.assertEqual(scandir.call_count, 1)
