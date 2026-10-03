"""Single-file hunk transformations. No GUI or reference-folder dependencies."""

import os
import re
import stat

try:
    from ..core.hunks import Line, apply_patch_text, lines
    from ..core.writes import discard_scratch, stage_bytes
    from ..core.paths import PathSafetyError as PatchError, validate_target
except ImportError:
    from core.hunks import Line, apply_patch_text, lines
    from core.writes import discard_scratch, stage_bytes
    from core.paths import PathSafetyError as PatchError, validate_target


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

    def save(self, result, suffix=None, backup=None):
        """Guarded save. ``backup``, when given, is called as ``backup(path, original_bytes, mode)``
        after staging and before replacement; if it raises, the target is left unchanged."""
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
                if backup is not None:
                    backup(destination, self.original_bytes, stat.S_IMODE(self.path.stat().st_mode))
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
            if scratch is not None:
                discard_scratch(scratch)
