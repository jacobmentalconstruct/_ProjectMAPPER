"""Shared filesystem safety independent of transformation tools."""
from pathlib import Path


class PathSafetyError(ValueError):
    pass


def validate_target(path):
    path = Path(path).absolute()
    if any(part.casefold() == ".parts" for part in (*path.parts, *path.resolve().parts)):
        raise PathSafetyError("The .parts reference folder is read-only.")
    if path.is_symlink() or path.resolve() != path:
        raise PathSafetyError("Choose a direct file path rather than a linked path.")
    return path
