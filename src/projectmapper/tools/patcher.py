"""Single-file hunk transformations. No GUI or reference-folder dependencies."""

from dataclasses import dataclass
from pathlib import Path
import os
import re
import stat

try:
    from ..core.writes import create_backup, stage_bytes
    from ..core.paths import PathSafetyError as PatchError, validate_target
except ImportError:
    from core.writes import create_backup, stage_bytes
    from core.paths import PathSafetyError as PatchError, validate_target


@dataclass(frozen=True)
class Line:
    body: str
    ending: str

    @property
    def indent(self):
        return re.match(r"[ \t]*", self.body).group()

    @property
    def content(self):
        return self.body.strip(" \t")


def lines(text):
    # Only physical newline characters split lines; preserve every original ending.
    return [Line(m[1], m[2]) for m in re.finditer(r"([^\r\n]*)(\r\n|\r|\n|$)", text)
            if m[0]]


def apply_patch_text(original_text, patch_obj, global_force_indent=False):
    """Resolve all hunks against the original, then apply them from bottom to top."""
    if not isinstance(patch_obj, dict) or not isinstance(patch_obj.get("hunks"), list):
        raise PatchError("Patch must be an object with a 'hunks' list.")
    if not patch_obj["hunks"]:
        raise PatchError("Add at least one hunk.")
    source = lines(original_text)
    default_ending = next((line.ending for line in source if line.ending), "\n")
    applications = []
    for number, hunk in enumerate(patch_obj["hunks"], 1):
        if not isinstance(hunk, dict):
            raise PatchError(f"Hunk {number}: Expected an object.")
        if not all(isinstance(hunk.get(key), str) for key in ("search_block", "replace_block")):
            raise PatchError(f"Hunk {number}: Search and replacement blocks must be strings.")
        if "use_patch_indent" in hunk and type(hunk["use_patch_indent"]) is not bool:
            raise PatchError(f"Hunk {number}: 'use_patch_indent' must be true or false.")
        search = lines(hunk["search_block"])
        replacement = lines(hunk["replace_block"])
        if not search:
            raise PatchError(f"Hunk {number}: Search block cannot be empty.")
        matches = []
        for floating in (False, True):
            matches = [start for start in range(len(source) - len(search) + 1)
                       if all((source[start + i].content == line.content if floating
                               else source[start + i].body == line.body)
                              for i, line in enumerate(search))]
            if matches:
                break
        if not matches:
            raise PatchError(f"Hunk {number}: Search block not found.")
        if len(matches) != 1:
            raise PatchError(f"Hunk {number}: Ambiguous match ({len(matches)} found).")
        start = matches[0]
        end = start + len(search)
        force = global_force_indent or hunk.get("use_patch_indent", False)
        base = source[start].indent
        patch_base = next((line.indent for line in replacement if line.content), "")
        ending = next((line.ending for line in source[start:end] if line.ending), default_ending)
        output = []
        for i, line in enumerate(replacement):
            body = line.body
            if not force and line.content:
                relative = line.indent[len(patch_base):] if line.indent.startswith(patch_base) else line.indent
                body = base + relative + line.body[len(line.indent):]
            # The target controls the block boundary, including final-newline state.
            output.append(Line(body, ending if i < len(replacement) - 1 else source[end - 1].ending))
        applications.append((start, end, output, number))
    applications.sort(key=lambda item: item[0])
    for left, right in zip(applications, applications[1:]):
        if left[1] > right[0]:
            raise PatchError(f"Hunks {left[3]} and {right[3]} overlap in the target file.")
    for start, end, output, _ in reversed(applications):
        source[start:end] = output
    return "".join(line.body + line.ending for line in source)


class PatchSession:
    """Byte-preserving UTF-8 load and guarded writes for one target file."""

    def __init__(self, path):
        self.path = validate_target(path)
        self.original_bytes = self.path.read_bytes()
        self.bom = self.original_bytes.startswith(b"\xef\xbb\xbf")
        try:
            self.source = self.original_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise PatchError("The patcher currently supports UTF-8 text files only.") from exc
        if "\x00" in self.source:
            raise PatchError("Binary files cannot be patched as text.")

    def save(self, result, suffix=None, backup=False):
        validate_target(self.path)
        if self.path.read_bytes() != self.original_bytes:
            raise PatchError("The target changed on disk. Reload it and validate the patch again.")
        destination = self.path
        if suffix is not None:
            if not suffix or not re.fullmatch(r"[A-Za-z0-9_.-]+", suffix):
                raise PatchError("Version suffix must contain only letters, numbers, _, - or .")
            suffix = suffix if suffix.startswith("_") else "_" + suffix
            destination = self.path.with_name(self.path.stem + suffix + self.path.suffix)
            if destination.exists():
                raise PatchError("That version already exists. Choose a different suffix.")
        validate_target(destination)
        data = (b"\xef\xbb\xbf" if self.bom else b"") + result.encode("utf-8")
        scratch = None
        try:
            scratch = stage_bytes(destination, data, mode=stat.S_IMODE(self.path.stat().st_mode), prefix=".patch-")
            if self.path.read_bytes() != self.original_bytes:
                raise PatchError("The target changed during save. Reload before trying again.")
            if suffix is None:
                if backup:
                    create_backup(destination, self.original_bytes)
                if validate_target(self.path).read_bytes() != self.original_bytes:
                    raise PatchError("The target changed during save. Reload before trying again.")
                os.replace(scratch, destination)
            else:
                # Exclusive creation avoids overwriting an existing version.
                os.link(scratch, destination)
            self.path = destination
            self.original_bytes = data
            self.source = result
            return destination
        finally:
            if scratch is not None and scratch.exists():
                scratch.unlink()
