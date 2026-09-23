"""Complete logical tree and inherited selection, independent of Tk widgets."""
from pathlib import Path


class LogicalTree:
    """A scan projection whose selection semantics do not depend on rendering."""

    def __init__(self, rows=(), selection=()):
        self.rows = []
        self.by_path = {}
        self.children = {}
        self.selection = {}
        self.replace(rows, selection)

    def replace(self, rows, previous=()):
        """Replace a parent-before-child scan; removed paths lose their overrides."""
        previous = {Path(path): state for path, state in dict(previous or {}).items()}
        self.rows = list(rows)
        self.by_path = {Path(row["path"]): row for row in self.rows}
        self.children = {path: [] for path in self.by_path}
        for row in self.rows:
            path = Path(row["path"])
            parent = Path(row["parent"]) if row.get("parent") else None
            if parent in self.children:
                self.children[parent].append(path)
        self.selection = {}
        for row in self.rows:
            path = Path(row["path"])
            if path in previous:
                self.selection[str(path)] = previous[path]
            else:
                parent = Path(row["parent"]) if row.get("parent") else None
                self.selection[str(path)] = self.selection.get(str(parent), "checked")
        return self

    def descendants(self, path, include_self=True):
        path = Path(path)
        result = []
        pending = [path] if include_self and path in self.by_path else list(self.children.get(path, ()))
        while pending:
            current = pending.pop()
            result.append(current)
            pending.extend(reversed(self.children.get(current, ())))
        return result

    def set_selection(self, path, state):
        for descendant in self.descendants(path):
            self.selection[str(descendant)] = state

    def selected(self, path):
        return self.selection.get(str(Path(path)), "unchecked") == "checked"
