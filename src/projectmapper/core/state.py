"""Explicit freshness state shared by the mapper and transformation tools."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectState:
    root: Path | None = None
    generation: int = 0
    capture_revision: int = 0
    scan_revision: int = 0
    applied_scan_revision: int = -1
    latest_source_mtime: float = 0.0
    snapshot_path: Path | None = None
    dirty_reasons: set[str] = field(default_factory=set)
    transformed_paths: set[Path] = field(default_factory=set)
    active_operations: set[str] = field(default_factory=set)

    def set_root(self, root):
        self.root = Path(root).resolve() if root else None
        self.generation += 1
        self.capture_revision += 1
        self.scan_revision += 1
        self.applied_scan_revision = -1
        self.snapshot_path = None
        self.latest_source_mtime = 0.0
        self.dirty_reasons.clear()
        self.transformed_paths.clear()

    def mark_scan_requested(self):
        self.scan_revision += 1
        self.dirty_reasons.add("tree_scan_pending")
        return self.scan_revision

    def mark_scan_applied(self, revision, source_mtime):
        if revision != self.scan_revision:
            return False
        self.applied_scan_revision = revision
        self.latest_source_mtime = float(source_mtime or 0.0)
        self.dirty_reasons.discard("tree_scan_pending")
        return True

    def mark_dirty(self, reason, paths=()):
        self.capture_revision += 1
        self.dirty_reasons.add(reason)
        self.snapshot_path = None
        self.transformed_paths.update(Path(path).resolve() for path in paths)

    def mark_snapshot(self, path, revision=None, capture_revision=None):
        if revision is not None and revision != self.scan_revision:
            return False
        if capture_revision is not None and capture_revision != self.capture_revision:
            return False
        self.snapshot_path = Path(path) if path else None
        self.dirty_reasons.clear()
        self.transformed_paths.clear()
        return True

    def operation_started(self, name):
        self.active_operations.add(name)

    def operation_finished(self, name):
        self.active_operations.discard(name)

    def can_export(self):
        return self.snapshot_path is not None and not self.dirty_reasons and not self.transformed_paths

    def explain_export_block(self):
        if self.transformed_paths:
            return "Files have been transformed. Compile a new snapshot before exporting."
        if self.dirty_reasons:
            return "Project state changed. Compile a new snapshot before exporting."
        if self.snapshot_path is None:
            return "No snapshot DB found yet. Compile Snapshot DB first."
        return None
