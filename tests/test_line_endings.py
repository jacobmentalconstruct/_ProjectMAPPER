"""Repository hygiene: text files use LF only; Windows batch files use CRLF only.

Backs up .gitattributes and .editorconfig, which an editor or a local git setting can
bypass. Checks the working tree, so drift fails the suite before it is committed.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
# Tracked text the project owns. .dev-log/ is private and checked by the same rule
# when present; vendor_exports/, archives and caches are generated or historical.
SCANNED_DIRS = ("src", "tests", "docs", "tools", ".dev-log")
SKIPPED_PARTS = {"__pycache__", "archive", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".ini", ".txt", ".json", ".cfg", ".yaml", ".yml"}
ROOT_FILES = (".gitattributes", ".gitignore", ".editorconfig", "pyproject.toml", "pytest.ini",
              "requirements.txt", "README.md", "CHANGELOG.md", "LICENSE.md")


def text_files():
    for name in ROOT_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for folder in SCANNED_DIRS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in TEXT_SUFFIXES and not SKIPPED_PARTS & set(path.parts):
                yield path


class LineEndingTests(unittest.TestCase):
    def test_text_files_have_no_carriage_returns(self):
        offenders = []
        for path in text_files():
            data = path.read_bytes()
            if b"\r" in data:
                count = data.count(b"\r")
                offenders.append(f"{path.relative_to(ROOT).as_posix()} ({count} CR)")
        self.assertEqual(offenders, [], "Convert these files to LF line endings: " + ", ".join(offenders))

    def test_batch_files_are_crlf_only(self):
        for path in ROOT.glob("*.bat"):
            data = path.read_bytes()
            with self.subTest(path=path.name):
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""), "Bare LF in a batch file")
                self.assertNotIn(b"\r", data.replace(b"\r\n", b""), "Bare CR in a batch file")


if __name__ == "__main__":
    unittest.main()
