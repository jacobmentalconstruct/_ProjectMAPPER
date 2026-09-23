from tests.support import temporary_directory, tk_root
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from projectmapper.app import ProjectMapperApp
from projectmapper.core.state import ProjectState
from projectmapper.application.controller import create_application


class FileDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.folder = Path(self.temp.name).resolve()
        self.target = self.folder / "delete_me.txt"
        self.target.write_text("original")
        self.app = ProjectMapperApp.__new__(ProjectMapperApp)
        self.app.root = None
        self.app.controller, self.app.approve_action = create_application(self.folder)
        self.addCleanup(self.app.controller.close)
        self.app.project_state = self.app.controller.state
        self.app.action_operations = set()
        self.app.running_tasks = set()
        self.app.scan_pending = False
        self.app.transformed_paths = set()
        self.app.latest_snapshot_path = self.folder / "snapshot.sqlite3"
        self.app.log_message = Mock()
        self.app.request_rescan_tree_silent = Mock()
        self.confirm = patch("projectmapper.app.messagebox.askyesno").start()
        self.error = patch("projectmapper.app.messagebox.showerror").start()
        self.addCleanup(patch.stopall)

    def test_declining_or_closing_does_not_delete(self):
        for decision in (False, None):
            self.confirm.return_value = decision
            self.app.delete_file(self.target)
            self.assertEqual(self.target.read_text(), "original")
            self.assertFalse(self.app.transformed_paths)
            self.app.request_rescan_tree_silent.assert_not_called()

    def test_approval_is_required_before_deletion_and_refresh(self):
        def approve(*args, **kwargs):
            self.assertTrue(self.target.exists())
            self.assertIn(str(self.target), args[1])
            self.assertEqual(kwargs["default"], "no")
            return True
        self.confirm.side_effect = approve
        self.app.delete_file(self.target)
        self.assertFalse(self.target.exists())
        self.assertIn(self.target, self.app.transformed_paths)
        self.assertIsNone(self.app.latest_snapshot_path)
        self.app.request_rescan_tree_silent.assert_called_once()
        self.error.assert_not_called()

    def test_change_during_approval_requires_new_review(self):
        def approve(*args, **kwargs):
            self.target.write_text("changed while dialog was open")
            return True
        self.confirm.side_effect = approve
        self.app.delete_file(self.target)
        self.assertEqual(self.target.read_text(), "changed while dialog was open")
        self.error.assert_called_once()
        self.app.request_rescan_tree_silent.assert_not_called()

    def test_folders_missing_files_and_parts_never_reach_confirmation(self):
        for target in (self.folder, self.folder / "missing.txt", self.folder / ".parts" / "ref.py"):
            self.app.delete_file(target)
        self.confirm.assert_not_called()
        self.assertTrue(self.target.exists())

    def test_active_operation_blocks_deletion(self):
        self.app.running_tasks.add("compile_snapshot")
        self.app.delete_file(self.target)
        self.confirm.assert_not_called()
        self.assertTrue(self.target.exists())

    def test_operation_starting_during_confirmation_blocks_deletion(self):
        def approve(*args, **kwargs):
            self.app.scan_pending = True
            return True
        self.confirm.side_effect = approve
        self.app.delete_file(self.target)
        self.assertTrue(self.target.exists())
        self.error.assert_called_once()

    def test_failed_delete_does_not_mark_snapshot_dirty(self):
        self.confirm.return_value = True
        with patch.object(Path, "unlink", side_effect=PermissionError("File is locked")):
            self.app.delete_file(self.target)
        self.assertTrue(self.target.exists())
        self.assertFalse(self.app.transformed_paths)
        self.app.request_rescan_tree_silent.assert_not_called()
        self.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
