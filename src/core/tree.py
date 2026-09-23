"""Metadata-only, cancellable filesystem inventory; never follow linked entries."""
import os
import stat
from pathlib import Path


def scan_project_tree(root: Path, policy, stop_event=None):
    root = Path(root).resolve()
    rows, skipped = [], []

    def cancelled():
        return stop_event is not None and stop_event.is_set()

    def skip(path, reason, detail):
        skipped.append(dict(relative_path=path.relative_to(root).as_posix(),
                            skip_reason=reason, detail=detail))

    # Enter/leave frames aggregate sizes without recursion or extra walks.
    if cancelled():
        return rows, skipped
    pending = [(root, None, 0, root.stat(), False)]
    while pending and not cancelled():
        path, parent, depth, metadata, leaving = pending.pop()
        if leaving:
            if parent is not None:
                parent["size_bytes"] += metadata["size_bytes"]
            continue
        directory = stat.S_ISDIR(metadata.st_mode)
        row = dict(path=path, parent=parent["path"] if parent else None,
                   relative_path=path.relative_to(root).as_posix(),
                   parent_relative_path=parent["relative_path"] if parent else None,
                   name=path.name, entry_type="dir" if directory else "file",
                   depth=depth, size_bytes=0 if directory else metadata.st_size,
                   mtime=metadata.st_mtime)
        rows.append(row)
        if not directory:
            if parent is not None:
                parent["size_bytes"] += row["size_bytes"]
            continue
        pending.append((path, parent, depth, row, True))
        entries = []
        try:
            with os.scandir(path) as iterator:
                for entry in iterator:
                    if cancelled():
                        break
                    child = path / entry.name
                    try:
                        info = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode):
                            skip(child, "symlink", "Linked entries are not followed")
                            continue
                        if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                            skip(child, "reparse_point", "Junctions and other reparse points are not followed")
                            continue
                        is_dir = stat.S_ISDIR(info.st_mode)
                        if not is_dir and not stat.S_ISREG(info.st_mode):
                            skip(child, "unsupported_type", "Not a regular file or directory")
                            continue
                        excluded, reason = policy.should_exclude_entry(child, root, is_dir)
                        if excluded:
                            skip(child, "excluded_by_rule", reason or "excluded")
                        else:
                            entries.append((child, info, is_dir))
                    except OSError as exc:
                        skip(child, "stat_failed", str(exc))
        except OSError as exc:
            skip(path, "permission_denied" if isinstance(exc, PermissionError) else "list_failed", str(exc))
        entries.sort(key=lambda item: (not item[2], item[0].name.lower(), item[0].name))
        pending.extend((child, row, depth + 1, info, False)
                       for child, info, _ in reversed(entries))
    return rows, skipped
