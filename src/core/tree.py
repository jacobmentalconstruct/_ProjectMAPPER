"""Filesystem tree walking independent of the Tk UI."""

from pathlib import Path


def _relative(path, root):
    try:
        return path.relative_to(root).as_posix()
    except Exception:
        return path.name


def _safe_size(path):
    try:
        return path.stat().st_size
    except OSError:
        return None


def _safe_mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def scan_project_tree(root: Path, policy, stop_event=None):
    root = Path(root).resolve()
    rows = []
    skipped = []

    def add_row(path, parent, depth, size_bytes=None):
        row = {
            "path": path.resolve(),
            "parent": parent.resolve() if parent else None,
            "relative_path": "." if path == root else _relative(path, root),
            "parent_relative_path": None if parent is None else ("." if parent == root else _relative(parent, root)),
            "name": path.name,
            "entry_type": "dir" if path.is_dir() else "file",
            "depth": depth,
            "size_bytes": _safe_size(path) if size_bytes is None and path.is_file() else size_bytes,
            "mtime": _safe_mtime(path),
        }
        rows.append(row)
        return row

    def recurse(current, depth):
        if stop_event is not None and stop_event.is_set():
            return 0
        try:
            items = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            skipped.append({"relative_path": _relative(current, root), "skip_reason": "permission_denied", "detail": "Cannot list directory"})
            return 0
        except Exception as exc:
            skipped.append({"relative_path": _relative(current, root), "skip_reason": "list_failed", "detail": str(exc)})
            return 0

        total_size = 0
        for item in items:
            if stop_event is not None and stop_event.is_set():
                break
            if item.is_symlink():
                skipped.append({"relative_path": _relative(item, root), "skip_reason": "symlink", "detail": "Linked files and folders are not followed"})
                continue
            excluded, reason = policy.should_exclude_path(item, root)
            if excluded:
                skipped.append({"relative_path": _relative(item, root), "skip_reason": "excluded_by_rule", "detail": reason or "excluded"})
                continue
            row = add_row(item, current, depth + 1)
            if item.is_dir():
                row["size_bytes"] = recurse(item, depth + 1)
            total_size += int(row.get("size_bytes") or 0)
        return total_size

    root_row = add_row(root, None, 0, 0)
    root_row["size_bytes"] = recurse(root, 0)
    return rows, skipped
