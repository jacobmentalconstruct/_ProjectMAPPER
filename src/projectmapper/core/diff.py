"""Shared diff data and presentation helpers."""

from dataclasses import dataclass
import difflib


@dataclass(frozen=True)
class DiffFile:
    relative_path: str
    original: str
    patched: str

    @property
    def additions(self):
        original = self.original.splitlines()
        patched = self.patched.splitlines()
        return sum((j2 - j1) for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, original, patched).get_opcodes()
                   if tag in ("insert", "replace"))

    @property
    def deletions(self):
        original = self.original.splitlines()
        patched = self.patched.splitlines()
        return sum((i2 - i1) for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, original, patched).get_opcodes()
                   if tag in ("delete", "replace"))

    @property
    def changed(self):
        return self.original != self.patched


def unified_diff_text(files):
    chunks = []
    for item in files:
        chunks.extend(difflib.unified_diff(item.original.splitlines(), item.patched.splitlines(),
                                            fromfile=item.relative_path, tofile=item.relative_path, lineterm=""))
    return "\n".join(chunks) or "(No differences)"


def diff_summary(files):
    files = list(files)
    return {
        "files": len(files),
        "changed_files": sum(item.changed for item in files),
        "additions": sum(item.additions for item in files),
        "deletions": sum(item.deletions for item in files),
    }
