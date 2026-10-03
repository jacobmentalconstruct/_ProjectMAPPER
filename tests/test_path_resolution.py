from pathlib import Path
import unittest

from projectmapper.core.paths import PathSafetyError, UnsafePathError, resolve_in_root


class RootResolutionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd() / "_path-resolution-fixture"

    def test_accepts_relative_paths_with_either_separator_style(self):
        self.assertEqual(resolve_in_root(self.root, "src/example.py"),
                         self.root / "src" / "example.py")
        self.assertEqual(resolve_in_root(self.root, r"src\example.py"),
                         self.root / "src" / "example.py")

    def test_rejects_absolute_drive_and_traversal_paths(self):
        invalid = ("/outside.py", r"C:\outside.py", "../outside.py", r"src\..\outside.py")
        for relative in invalid:
            with self.subTest(relative=relative), self.assertRaises(UnsafePathError):
                resolve_in_root(self.root, relative)

    def test_refuses_project_root_and_version_control_directories_case_insensitively(self):
        for relative in (".", ".git/HEAD", "src/.HG/config", ".svn/entries"):
            with self.subTest(relative=relative), self.assertRaises(UnsafePathError):
                resolve_in_root(self.root, relative)

    def test_can_explicitly_resolve_root_for_callers_that_need_it(self):
        self.assertEqual(resolve_in_root(self.root, ".", allow_root=True), self.root)

    def test_empty_path_is_invalid(self):
        with self.assertRaises(PathSafetyError):
            resolve_in_root(self.root, " ")


if __name__ == "__main__":
    unittest.main()
