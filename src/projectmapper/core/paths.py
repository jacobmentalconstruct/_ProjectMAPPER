"""Shared filesystem safety independent of transformation tools."""
from pathlib import Path


class PathSafetyError(ValueError):
    """A refusal from the file engines (also exported as PatchError); reported as invalid_input."""


class UnsafePathError(PathSafetyError):
    """The location itself is not allowed; the dispatcher reports it as unsafe_path."""
    code = "unsafe_path"


class SourceChangedError(PathSafetyError):
    """The file no longer matches what was validated; the dispatcher reports it as source_changed."""
    code = "source_changed"


def validate_target(path):
    path = Path(path).absolute()
    if any(part.casefold() == ".parts" for part in (*path.parts, *path.resolve().parts)):
        raise UnsafePathError("The .parts reference folder is read-only.")
    if path.is_symlink() or path.resolve() != path:
        raise UnsafePathError("Choose a direct file path rather than a linked path.")
    return path
