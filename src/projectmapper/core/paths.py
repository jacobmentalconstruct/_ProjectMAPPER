"""Shared filesystem safety independent of transformation tools."""
from pathlib import Path, PureWindowsPath


class PathSafetyError(ValueError):
    """A refusal from the file engines (also exported as PatchError); reported as invalid_input."""


class UnsafePathError(PathSafetyError):
    """The location itself is not allowed; the dispatcher reports it as unsafe_path."""
    code = "unsafe_path"


class SourceChangedError(PathSafetyError):
    """The file no longer matches what was validated; the dispatcher reports it as source_changed."""
    code = "source_changed"


_VERSION_CONTROL_DIRS = frozenset({".git", ".hg", ".svn"})


def validate_target(path):
    path = Path(path).absolute()
    if any(part.casefold() == ".parts" for part in (*path.parts, *path.resolve().parts)):
        raise UnsafePathError("The .parts reference folder is read-only.")
    if path.is_symlink() or path.resolve() != path:
        raise UnsafePathError("Choose a direct file path rather than a linked path.")
    return path


def resolve_in_root(root, relative, *, allow_root=False):
    """Resolve a user path beneath ``root`` and refuse app/reference metadata.

    Both slash conventions are accepted on every OS. Absolute paths, drive-qualified
    paths, parent traversal, symlink traversal and version-control directories are
    rejected before a caller can read or mutate the result.
    """
    if not isinstance(relative, str) or not relative.strip():
        raise PathSafetyError("A relative path is required.")
    windows_path = PureWindowsPath(relative)
    normalized = relative.replace("\\", "/")
    relative_path = Path(normalized)
    if (relative_path.is_absolute() or windows_path.is_absolute() or windows_path.drive
            or ".." in relative_path.parts or ".." in windows_path.parts):
        raise UnsafePathError("Choose a relative path inside the project root.")

    root_path = validate_target(Path(root).absolute())
    candidate = validate_target((root_path / relative_path).absolute())
    try:
        relative_parts = candidate.relative_to(root_path).parts
    except ValueError as exc:
        raise UnsafePathError("The path escapes the project root.") from exc
    if not allow_root and not relative_parts:
        raise UnsafePathError("The project root itself is not a file target.")
    if any(part.casefold() in _VERSION_CONTROL_DIRS for part in relative_parts):
        raise UnsafePathError("Version-control folders are read-only.")
    return candidate
