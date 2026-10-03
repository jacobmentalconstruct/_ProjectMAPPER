"""Validated operation shapes for ordered project changesets."""

from dataclasses import dataclass
import copy
import json
import re

from .paths import PathSafetyError


_ALIASES = {"rename": "move", "rename_dir": "move_dir"}
_FIELDS = {
    "patch": {"path", "sha256", "hunks"},
    "create": {"path", "content"},
    "delete": {"path", "sha256"},
    "move": {"from", "to", "sha256"},
    "mkdir": {"path"},
    "move_dir": {"from", "to"},
    "delete_dir": {"path", "recursive"},
}
_COMMON_FIELDS = {"description", "derived_from"}
_HEX_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


@dataclass(frozen=True)
class Operation:
    """One normalized v2 operation; paths remain relative until validation."""

    kind: str
    path: str = None
    source: str = None
    destination: str = None
    content: str = None
    sha256: str = None
    hunks: tuple = ()
    recursive: bool = False
    description: str = None
    derived_from: int = None

    def as_dict(self):
        """Return the canonical manifest shape without changing hunk text."""
        result = {"op": self.kind}
        if self.path is not None:
            result["path"] = self.path
        if self.source is not None:
            result["from"] = self.source
        if self.destination is not None:
            result["to"] = self.destination
        if self.content is not None:
            result["content"] = self.content
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        if self.hunks:
            result["hunks"] = copy.deepcopy(list(self.hunks))
        if self.recursive:
            result["recursive"] = True
        if self.description is not None:
            result["description"] = self.description
        if self.derived_from is not None:
            result["derived_from"] = self.derived_from
        return result


@dataclass(frozen=True)
class ChangeSet:
    """A manifest normalized to the v2 operation-list representation."""

    description: str = None
    ops: tuple = ()

    def as_dict(self):
        result = {"version": 2, "ops": [op.as_dict() for op in self.ops]}
        if self.description is not None:
            result["description"] = self.description
        return result


@dataclass(frozen=True)
class InverseOperation:
    """Internal inverse description; captured bytes are supplied by simulation."""

    kind: str
    path: str = None
    source: str = None
    destination: str = None
    original_bytes: bytes = None
    original_mode: int = None


def _manifest_object(manifest):
    if isinstance(manifest, str):
        try:
            manifest = json.loads(manifest)
        except json.JSONDecodeError as exc:
            raise PathSafetyError(f"Invalid project patch JSON: {exc.msg}.") from exc
    if not isinstance(manifest, dict):
        raise PathSafetyError("Project patch must be an object.")
    version = manifest.get("version", 1)
    if type(version) is not int or version not in (1, 2):
        raise PathSafetyError("Unsupported project patch version.")
    if version == 1:
        unknown = set(manifest) - {"version", "description", "files"}
        if unknown:
            raise PathSafetyError(f"Unexpected version 1 project patch field: {sorted(unknown)[0]}.")
        if "ops" in manifest or not isinstance(manifest.get("files"), list):
            raise PathSafetyError("Version 1 project patch must have a 'files' list.")
        entries = manifest["files"]
        is_v1 = True
    else:
        unknown = set(manifest) - {"version", "description", "ops"}
        if unknown:
            raise PathSafetyError(f"Unexpected version 2 project patch field: {sorted(unknown)[0]}.")
        if "files" in manifest or not isinstance(manifest.get("ops"), list):
            raise PathSafetyError("Version 2 project patch must have an 'ops' list.")
        entries = manifest["ops"]
        is_v1 = False
    if not entries:
        raise PathSafetyError("Add at least one file entry." if is_v1 else "Add at least one operation.")
    description = manifest.get("description")
    if description is not None and not isinstance(description, str):
        raise PathSafetyError("Project patch description must be text.")
    return entries, is_v1, description


def _nonempty_path(entry, field):
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PathSafetyError(f"Operation needs a non-empty '{field}' path.")
    return value


def _parse_operation(entry, *, is_v1):
    if not isinstance(entry, dict):
        raise PathSafetyError("Each project patch operation must be an object.")
    if is_v1:
        kind = "patch"
    else:
        supplied_kind = entry.get("op")
        if not isinstance(supplied_kind, str):
            raise PathSafetyError("Each operation needs an 'op' name.")
        kind = _ALIASES.get(supplied_kind, supplied_kind)
    if kind not in _FIELDS:
        raise PathSafetyError(f"Unsupported project patch operation: {kind}.")

    allowed = _FIELDS[kind] | _COMMON_FIELDS | ({"path"} if is_v1 else {"op"})
    unknown = set(entry) - allowed
    if unknown:
        raise PathSafetyError(f"Unexpected field for {kind} operation: {sorted(unknown)[0]}.")
    description = entry.get("description")
    if description is not None and not isinstance(description, str):
        raise PathSafetyError("Operation description must be text.")
    derived_from = entry.get("derived_from")
    if derived_from is not None and (type(derived_from) is not int or derived_from < 0):
        raise PathSafetyError("'derived_from' must be a non-negative operation index.")

    path = _nonempty_path(entry, "path") if kind in {"patch", "create", "delete", "mkdir", "delete_dir"} else None
    source = destination = None
    if kind in {"move", "move_dir"}:
        source = _nonempty_path(entry, "from")
        destination = _nonempty_path(entry, "to")

    content = entry.get("content")
    if kind == "create" and not isinstance(content, str):
        raise PathSafetyError("Create operation needs text 'content'.")
    hunks = entry.get("hunks", ())
    if kind == "patch":
        if not isinstance(hunks, list) or not hunks:
            raise PathSafetyError("Patch operation needs a non-empty 'hunks' list.")
        if any(not isinstance(hunk, dict) for hunk in hunks):
            raise PathSafetyError("Each patch hunk must be an object.")
        for hunk in hunks:
            if not all(isinstance(hunk.get(field), str) for field in ("search_block", "replace_block")):
                raise PathSafetyError("Each patch hunk needs text search and replacement blocks.")
            if "use_patch_indent" in hunk and type(hunk["use_patch_indent"]) is not bool:
                raise PathSafetyError("Hunk 'use_patch_indent' must be true or false.")
        hunks = tuple(copy.deepcopy(hunks))
    else:
        hunks = ()

    sha256 = entry.get("sha256")
    if sha256 is not None:
        if kind not in {"patch", "delete", "move"}:
            raise PathSafetyError(f"A sha256 is not valid for {kind} operations.")
        # V1 historically checked length only. Keep that input compatibility while
        # requiring well-formed hexadecimal digests for new v2 manifests.
        if not isinstance(sha256, str) or len(sha256) != 64 or (not is_v1 and not _HEX_SHA256.fullmatch(sha256)):
            raise PathSafetyError(f"Invalid sha256 for {path or source}.")

    recursive = entry.get("recursive", False)
    if kind == "delete_dir":
        if type(recursive) is not bool:
            raise PathSafetyError("'recursive' must be true or false.")
    else:
        recursive = False
    return Operation(kind, path, source, destination, content, sha256, hunks,
                     recursive, description, derived_from)


def parse_changeset(manifest):
    """Parse v1 or v2 input and return its canonical v2 operation model."""
    entries, is_v1, description = _manifest_object(manifest)
    ops = tuple(_parse_operation(entry, is_v1=is_v1) for entry in entries)
    return ChangeSet(description=description, ops=ops)


def inverse_operation(operation, *, original_bytes=None, original_mode=None):
    """Describe one inverse op, attaching captured data when it is required."""
    kind = operation.kind
    if kind == "patch":
        if original_bytes is None:
            raise ValueError("Inverting a patch requires the original file bytes.")
        return InverseOperation("restore", path=operation.path,
                                original_bytes=original_bytes, original_mode=original_mode)
    if kind == "create":
        return InverseOperation("delete", path=operation.path)
    if kind == "delete":
        if original_bytes is None:
            raise ValueError("Inverting a delete requires the original file bytes.")
        return InverseOperation("create", path=operation.path,
                                original_bytes=original_bytes, original_mode=original_mode)
    if kind == "move":
        return InverseOperation("move", source=operation.destination,
                                destination=operation.source)
    if kind == "mkdir":
        return InverseOperation("delete_dir", path=operation.path)
    if kind == "move_dir":
        return InverseOperation("move_dir", source=operation.destination,
                                destination=operation.source)
    if kind == "delete_dir":
        if operation.recursive:
            raise ValueError("Recursive directory deletes must be expanded before inversion.")
        return InverseOperation("mkdir", path=operation.path)
    raise ValueError(f"No inverse is defined for {kind}.")
