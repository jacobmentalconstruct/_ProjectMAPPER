"""Small shared building blocks for ProjectMapper's core state and tools."""

from .diff import DiffFile, diff_summary, unified_diff_text
from .diagnostics import collect_diagnostics, format_diagnostics
from .state import ProjectState
from .tree import scan_project_tree
from .writes import atomic_write_bytes, backup_path, create_backup, stage_bytes

__all__ = [
    "DiffFile", "ProjectState", "atomic_write_bytes", "diff_summary",
    "stage_bytes", "unified_diff_text", "collect_diagnostics", "format_diagnostics",
    "backup_path", "create_backup", "scan_project_tree",
]
