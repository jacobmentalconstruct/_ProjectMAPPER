"""Validated, all-or-nothing multi-file patches for one project root."""

import json
import copy

from .patcher import PatchError, validate_target
try:
    from ..core.diff import DiffFile, unified_diff_text
    from ..core.config import OUTPUT_ROOT_NAME
    from ..core.paths import resolve_in_root
    from ..core.changeset import ChangeSet, Operation
    from ..core.transaction import apply_operations
    from ..core.vtree import Simulation, VirtualTree
except ImportError:
    from core.diff import DiffFile, unified_diff_text
    from core.config import OUTPUT_ROOT_NAME
    from core.paths import resolve_in_root
    from core.changeset import ChangeSet, Operation
    from core.transaction import apply_operations
    from core.vtree import Simulation, VirtualTree


EXAMPLE_ENTRY = {"path": "src/example.py", "sha256": "optional-original-file-hash", "hunks": [
    {"description": "Describe the change", "search_block": "old", "replace_block": "new", "use_patch_indent": False}]}
EXAMPLE_MANIFEST = {"version": 1, "description": "Project patch", "files": [EXAMPLE_ENTRY]}
SKELETON_MANIFEST = {"version": 1, "files": []}


def _ends_with_newline(text):
    return text.endswith(("\n", "\r"))


class ProjectPatchSession:
    def __init__(self, root, manifest):
        self.root = validate_target(root)
        if not self.root.is_dir():
            raise PatchError("Project patch root must be a folder.")
        self.manifest = copy.deepcopy(self._parse(manifest))
        self.results = []
        self._force_indent = False
        self._reviewed_operations = []
        self._validate_manifest()

    @staticmethod
    def _parse(manifest):
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except json.JSONDecodeError as exc:
                raise PatchError(f"Invalid project patch JSON: {exc.msg}.") from exc
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
            raise PatchError("Project patch must be an object with a 'files' list.")
        if manifest.get("version", 1) != 1:
            raise PatchError("Unsupported project patch version.")
        if not manifest["files"]:
            raise PatchError("Add at least one file entry.")
        return manifest

    def _resolve(self, relative):
        candidate = resolve_in_root(self.root, relative)
        # Refuse the project's own output folder and roots directly inside one. Ancestor
        # names alone are ambiguous: hosted runners and workspace folders may share them.
        parts = candidate.relative_to(self.root).parts
        if (self.root.parent.name.casefold() == OUTPUT_ROOT_NAME.casefold()
                or any(part.casefold() == OUTPUT_ROOT_NAME.casefold() for part in parts)):
            raise PatchError(f"The {OUTPUT_ROOT_NAME} output folder cannot be patched: {relative}")
        return candidate

    def _validate_manifest(self):
        seen = set()
        for index, entry in enumerate(self.manifest["files"], 1):
            if not isinstance(entry, dict):
                raise PatchError(f"File entry {index} must be an object.")
            path = self._resolve(entry.get("path"))
            key = str(path).casefold()
            if key in seen:
                raise PatchError(f"Duplicate file entry: {entry.get('path')}")
            seen.add(key)
            if not path.is_file():
                raise PatchError(f"Target file does not exist: {entry.get('path')}")
            if not isinstance(entry.get("hunks"), list) or not entry["hunks"]:
                raise PatchError(f"File entry {entry.get('path')} needs a non-empty 'hunks' list.")
            expected = entry.get("sha256")
            if expected is not None and (not isinstance(expected, str) or len(expected) != 64):
                raise PatchError(f"Invalid sha256 for {entry.get('path')}.")

    def review(self, force_indent=False):
        """Validate every file independently; plan results exist only when all are valid."""
        self._force_indent = force_indent
        self.results = []
        self._reviewed_operations = []
        outcomes, results = [], []
        tree = VirtualTree(self.root)
        for entry in self.manifest["files"]:
            operation = Operation("patch", path=entry["path"], sha256=entry.get("sha256"),
                                  hunks=tuple(copy.deepcopy(entry["hunks"])))
            simulation = tree.simulate(ChangeSet(ops=(operation,)), force_indent=force_indent)
            if not simulation.valid:
                exc = simulation.errors[0]["error"]
                outcomes.append({"relative_path": entry["path"], "status": "error",
                                 "error": f"{entry['path']}: {exc}",
                                 "hunk_count": len(entry["hunks"])})
                continue
            detail = simulation.operations[0]
            result = {"path": self._resolve(entry["path"]), "relative_path": entry["path"],
                      "original_bytes": detail["original_bytes"], "original": detail["original"],
                      "patched": detail["patched"], "sha256": detail["sha256"],
                      "identity": detail["before"][detail["path"]]["identity"]}
            operation_detail = copy.deepcopy(detail)
            operation_detail["index"] = len(self._reviewed_operations)
            self._reviewed_operations.append(operation_detail)
            results.append(result)
            diff = DiffFile(entry["path"], result["original"], result["patched"])
            visible = {key: value for key, value in result.items() if key != "identity"}
            outcomes.append({**visible, "status": "changed" if diff.changed else "no_change", "error": None,
                             "hunk_count": len(entry["hunks"]), "additions": diff.additions,
                             "deletions": diff.deletions, "diff_hunks": diff.hunks,
                             "empty_result": result["patched"] == "" and result["original"] != "",
                             "final_newline_changed": bool(result["original"]) and bool(result["patched"])
                             and _ends_with_newline(result["original"]) != _ends_with_newline(result["patched"])})
        if len(results) == len(outcomes):
            self.results = results
        else:
            self._reviewed_operations = []
        return outcomes

    def validate_all(self, force_indent=False):
        outcomes = self.review(force_indent)
        errors = [outcome["error"] for outcome in outcomes if outcome["status"] == "error"]
        if errors:
            raise PatchError("; ".join(errors))
        return self.results

    def apply_all(self, backup=None, recover=None):
        """Apply the reviewed changeset as one rollback-capable transaction.

        ``backup`` and ``recover`` are optional callables taking ``[(path, original_bytes, mode)]``
        and returning a description of where the bytes were stored. Backups are captured
        before mutation; deletes stay quarantined until the entire changeset commits.
        """
        if not self.results:
            self.validate_all(self._force_indent)
        simulation = Simulation(operations=copy.deepcopy(self._reviewed_operations))
        result = apply_operations(self.root, simulation, backup=backup, recover=recover)
        self.results = []
        self._reviewed_operations = []
        return result["paths"]


def project_patch_diff(results):
    return unified_diff_text(DiffFile(result["relative_path"], result["original"], result["patched"])
                             for result in results)
