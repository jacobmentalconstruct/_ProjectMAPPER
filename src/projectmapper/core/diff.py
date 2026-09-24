"""Shared diff data and presentation helpers."""

from dataclasses import dataclass
import difflib
import re


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

    @property
    def hunks(self):
        """Changed regions as unified-diff groups (3 context lines), as 0-based line ranges."""
        matcher = difflib.SequenceMatcher(None, self.original.splitlines(), self.patched.splitlines())
        return [{"original_start": group[0][1], "original_end": group[-1][2],
                 "patched_start": group[0][3], "patched_end": group[-1][4]}
                for group in matcher.get_grouped_opcodes(3)] if self.changed else []


_HUNK_HEADER = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def diff_line_kinds(text):
    """Classify unified-diff lines as header, hunk, add, remove or None (context).

    Lines inside a hunk are classified by the hunk's line counts, so content such as
    a removed "-- comment" (shown as "--- comment") is never mistaken for a file header.
    """
    kinds, old, new = [], 0, 0
    for line in text.split("\n"):
        if old > 0 or new > 0:
            if line.startswith("-"):
                kinds.append("remove")
                old -= 1
            elif line.startswith("+"):
                kinds.append("add")
                new -= 1
            else:
                kinds.append(None)
                old, new = old - 1, new - 1
            continue
        match = _HUNK_HEADER.match(line)
        if match:
            old = 1 if match[1] is None else int(match[1])
            new = 1 if match[2] is None else int(match[2])
            kinds.append("hunk")
        else:
            kinds.append("header" if line.startswith(("--- ", "+++ ")) else None)
    return kinds


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
