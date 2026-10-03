"""Sequential, non-mutating simulation of project changesets."""

from dataclasses import dataclass, field
import hashlib
import os
import stat
from pathlib import Path

from .config import OUTPUT_ROOT_NAME
from .changeset import ChangeSet
from .hunks import apply_patch_text
from .paths import PathSafetyError, SourceChangedError, UnsafePathError, resolve_in_root


_PROTECTED = {".parts", "_projectmapper", ".git", ".hg", ".svn"}


def _key(relative):
    return relative.casefold()


def _parts(relative):
    return tuple(part for part in relative.replace("\\", "/").split("/") if part)


@dataclass
class _Node:
    path: str
    kind: str
    data: bytes = None
    mode: int = None
    original_bytes: bytes = None
    original_mode: int = None
    disk_backed: bool = True
    original_identity: tuple = None

@dataclass
class Simulation:
    """Results are available even when some operations conflict."""

    operations: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    final_files: dict = field(default_factory=dict)

    @property
    def valid(self):
        return not self.errors


class VirtualTree:
    """A lazy overlay over a project directory; simulation never writes to disk.

    Paths in the overlay are case-folded for collision checks while each node keeps its
    original spelling. File contents stay as bytes between operations; decoding occurs
    only for text patch hunks, so BOMs and physical newline choices remain explicit.
    """

    def __init__(self, root, *, exclusion_match=None):
        self.root = Path(root).absolute()
        self._nodes = {}
        self._tombstones = set()
        self._exclusion_match = exclusion_match

    def _resolve(self, relative, *, allow_root=False):
        path = resolve_in_root(self.root, relative, allow_root=allow_root)
        parts = path.relative_to(self.root).parts
        if (any(part.casefold() in _PROTECTED for part in parts)
                or any(part.casefold() == OUTPUT_ROOT_NAME.casefold() for part in parts)):
            raise UnsafePathError("Project metadata and output folders are read-only.")
        return path

    def _relative(self, path):
        return path.relative_to(self.root).as_posix()

    def _case_collision(self, path):
        parent = path.parent
        if not parent.is_dir():
            return None
        try:
            return next((item for item in parent.iterdir()
                         if item.name.casefold() == path.name.casefold()), None)
        except OSError:
            return None

    def _load(self, relative):
        path = self._resolve(relative)
        rel = self._relative(path)
        key = _key(rel)
        if key in self._tombstones:
            raise PathSafetyError(f"Target does not exist in the current changeset state: {relative}.")
        cached = self._nodes.get(key)
        if cached is not None:
            if cached.disk_backed and cached.path != rel and path.exists():
                try:
                    same_entry = os.path.samefile(path, self.root / cached.path)
                except OSError:
                    same_entry = False
                if not same_entry:
                    raise PathSafetyError(f"Case-insensitive path collision: {relative}.")
            return cached

        if not path.exists() and not path.is_symlink():
            collision = self._case_collision(path)
            if collision is not None:
                path = self._resolve(self._relative(collision))
                rel = self._relative(path)
                key = _key(rel)
                cached = self._nodes.get(key)
                if cached is not None:
                    return cached
        if path.is_symlink():
            raise UnsafePathError("Linked paths cannot be changed.")
        try:
            info = path.stat()
            mode = stat.S_IMODE(info.st_mode)
            if path.is_dir():
                node = _Node(rel, "dir", mode=mode, original_mode=mode,
                             original_identity=(info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns))
            elif path.is_file():
                data = path.read_bytes()
                node = _Node(rel, "file", data, mode, data, mode,
                             original_identity=(info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns))
            else:
                raise PathSafetyError(f"Target is not a regular file or folder: {relative}.")
        except FileNotFoundError as exc:
            raise PathSafetyError(f"Target does not exist: {relative}.") from exc
        self._nodes[key] = node
        return node

    def _load_parent(self, relative):
        parts = _parts(relative)
        if len(parts) <= 1:
            return None
        parent = self._load("/".join(parts[:-1]))
        if parent.kind != "dir":
            raise PathSafetyError(f"Parent folder does not exist: {'/'.join(parts[:-1])}.")
        return parent

    def _children(self, directory):
        """Load a complete subtree before structural operations rewrite its keys."""
        path = self._resolve(directory.path)
        disk_paths = []
        if directory.disk_backed:
            def raise_walk_error(error):
                raise error

            for current, dirs, files in os.walk(path, onerror=raise_walk_error, followlinks=False):
                current_path = Path(current)
                for name in (*dirs, *files):
                    child = current_path / name
                    rel = self._relative(child)
                    self._resolve(rel)
                    if child.is_symlink():
                        raise UnsafePathError("Folders containing linked paths cannot be moved or deleted.")
                    disk_paths.append(rel)
        for key, node in tuple(self._nodes.items()):
            if node.path.casefold().startswith(directory.path.casefold().rstrip("/") + "/"):
                if key not in self._tombstones:
                    disk_paths.append(node.path)
        nodes = []
        for relative in sorted(set(disk_paths), key=lambda item: (item.count("/"), item.casefold())):
            if _key(relative) in self._tombstones:
                continue
            nodes.append(self._load(relative))
        return nodes

    def _existing_destination(self, relative):
        path = self._resolve(relative)
        key = _key(self._relative(path))
        if key in self._tombstones:
            return None
        try:
            return self._load(relative)
        except PathSafetyError as exc:
            if str(exc).startswith("Target does not exist:"):
                return None
            raise

    def _record_before(self, *nodes):
        before = {}
        for node in nodes:
            if node is None:
                continue
            digest = hashlib.sha256(node.data).hexdigest() if node.kind == "file" else None
            before[node.path] = {"kind": node.kind, "sha256": digest,
                                 "mode": node.mode, "identity": node.original_identity}
        return before

    @staticmethod
    def _missing_before(relative):
        return {relative: {"kind": "missing", "sha256": None, "mode": None}}

    def _patch(self, operation, force_indent=False):
        node = self._load(operation.path)
        if node.kind != "file":
            raise PathSafetyError(f"Patch target is not a file: {operation.path}.")
        digest = hashlib.sha256(node.data).hexdigest()
        if operation.sha256 and digest.casefold() != operation.sha256.casefold():
            raise SourceChangedError(f"Source changed; expected sha256 {operation.sha256}, found {digest}.")
        input_bytes = node.data
        try:
            original = input_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise PathSafetyError("Not valid UTF-8 text.") from exc
        if "\x00" in original:
            raise PathSafetyError("Appears to be binary.")
        before = self._record_before(node)
        patched = apply_patch_text(original, {"hunks": list(operation.hunks)}, force_indent)
        bom = input_bytes.startswith(b"\xef\xbb\xbf")
        node.data = (b"\xef\xbb\xbf" if bom else b"") + patched.encode("utf-8")
        return {"path": node.path, "before": before, "content": node.data,
                "original_bytes": input_bytes, "original": original, "patched": patched,
                "sha256": digest}

    def _apply(self, operation, force_indent=False):
        kind = operation.kind
        if kind == "patch":
            return self._patch(operation, force_indent)
        if kind in {"create", "mkdir"}:
            path = self._resolve(operation.path)
            relative = self._relative(path)
            self._load_parent(relative)
            if self._existing_destination(relative) is not None:
                raise PathSafetyError(f"Destination already exists: {relative}.")
            if kind == "create":
                data = operation.content.encode("utf-8")
                node = _Node(relative, "file", data, disk_backed=False)
            else:
                node = _Node(relative, "dir", disk_backed=False)
            self._nodes[_key(relative)] = node
            self._tombstones.discard(_key(relative))
            warnings = []
            if self._exclusion_match is not None and self._exclusion_match(relative):
                warnings.append(f"Destination is excluded from the project tree: {relative}.")
            return {"path": relative, "before": self._missing_before(relative),
                    "content": node.data, "warnings": warnings}

        if kind in {"delete", "delete_dir"}:
            node = self._load(operation.path)
            if kind == "delete" and node.kind != "file":
                raise PathSafetyError(f"Delete target is not a file: {operation.path}.")
            if kind == "delete_dir" and node.kind != "dir":
                raise PathSafetyError(f"Delete target is not a folder: {operation.path}.")
            descendants = self._children(node) if kind == "delete_dir" else []
            if kind == "delete_dir" and descendants and not operation.recursive:
                raise PathSafetyError(f"Folder is not empty: {operation.path}.")
            targets = [node, *descendants]
            before = self._record_before(*targets)
            for target in targets:
                self._tombstones.add(_key(target.path))
            warnings = []
            if kind == "delete" and node.data != node.original_bytes:
                warnings.append(f"Deleting a file changed by an earlier operation: {node.path}.")
            return {"path": node.path, "before": before, "content": None,
                    "warnings": warnings}

        if kind in {"move", "move_dir"}:
            source = self._load(operation.source)
            required_kind = "file" if kind == "move" else "dir"
            if source.kind != required_kind:
                raise PathSafetyError(f"{kind} source is not a {required_kind}: {operation.source}.")
            destination_path = self._resolve(operation.destination)
            destination = self._relative(destination_path)
            if kind == "move_dir" and (destination.casefold() == source.path.casefold()
                    or destination.casefold().startswith(source.path.casefold().rstrip("/") + "/")):
                raise PathSafetyError("A folder cannot be moved into itself or its descendant.")
            self._load_parent(destination)
            existing = self._existing_destination(destination)
            same_node = existing is source
            if existing is not None and not same_node:
                raise PathSafetyError(f"Destination already exists: {destination}.")
            moved = [source, *(self._children(source) if kind == "move_dir" else [])]
            before = self._record_before(*moved)
            old_prefix = source.path
            if not same_node:
                before.update(self._missing_before(destination))
            for node in moved:
                suffix = node.path[len(old_prefix):]
                updated = destination + suffix
                old_key = _key(node.path)
                self._nodes.pop(old_key, None)
                new_key = _key(updated)
                if old_key != new_key:
                    self._tombstones.add(old_key)
                self._tombstones.discard(new_key)
                node.path = updated
                self._nodes[new_key] = node
            warning = []
            if self._exclusion_match is not None and self._exclusion_match(destination):
                warning.append(f"Destination is excluded from the project tree: {destination}.")
            if kind == "move" and Path(old_prefix).suffix.casefold() != Path(destination).suffix.casefold():
                warning.append(f"File extension changes: {old_prefix} → {destination}.")
            return {"from": old_prefix, "to": destination, "before": before,
                    "content": source.data if source.kind == "file" else None, "warnings": warning}

        raise PathSafetyError(f"Unsupported operation: {kind}.")

    def simulate(self, changeset: ChangeSet, *, force_indent=False):
        """Apply operations to the overlay in order and collect every operation error."""
        result = Simulation()
        for index, operation in enumerate(changeset.ops):
            try:
                detail = self._apply(operation, force_indent)
                detail.update({"index": index, "op": operation.kind, "error": None})
                paths = ([operation.path] if operation.path is not None else
                         [operation.source, operation.destination])
                detail["resolved_paths"] = [self._resolve(path) for path in paths]
                warnings = detail.pop("warnings", [])
                for warning in warnings:
                    result.warnings.append({"index": index, "message": warning})
                result.operations.append(detail)
            except (PathSafetyError, OSError) as exc:
                result.errors.append({"index": index, "op": operation.kind,
                                      "path": operation.path or operation.source,
                                      "error": str(exc)})
                result.operations.append({"index": index, "op": operation.kind,
                                          "path": operation.path or operation.source,
                                          "error": str(exc)})
        result.final_files = {node.path: node.data for key, node in self._nodes.items()
                              if key not in self._tombstones and node.kind == "file"}
        return result
