"""Validated, all-or-nothing multi-file patches for one project root."""

import json
import copy

from .patcher import PatchError, validate_target
try:
    from ..core.diff import DiffFile, unified_diff_text
    from ..core.config import OUTPUT_ROOT_NAME
    from ..core.paths import resolve_in_root
    from ..core.changeset import ChangeSet, Operation, parse_changeset
    from ..core.transaction import apply_operations
    from ..core.vtree import Simulation, VirtualTree
except ImportError:
    from core.diff import DiffFile, unified_diff_text
    from core.config import OUTPUT_ROOT_NAME
    from core.paths import resolve_in_root
    from core.changeset import ChangeSet, Operation, parse_changeset
    from core.transaction import apply_operations
    from core.vtree import Simulation, VirtualTree


EXAMPLE_ENTRY = {"path": "src/example.py", "sha256": "optional-original-file-hash", "hunks": [
    {"description": "Describe the change", "search_block": "old", "replace_block": "new", "use_patch_indent": False}]}
EXAMPLE_MANIFEST = {"version": 1, "description": "Project patch", "files": [EXAMPLE_ENTRY]}
SKELETON_MANIFEST = {"version": 1, "files": []}
EXAMPLE_CHANGESET = {"version": 2, "description": "Project transform", "ops": [
    {"op": "patch", "path": "src/example.py", "hunks": [
        {"description": "Describe the change", "search_block": "old", "replace_block": "new",
         "use_patch_indent": False}]},
    {"op": "create", "path": "src/new_module.py", "content": "# New file\n"},
    {"op": "move", "from": "src/old_name.py", "to": "src/new_name.py"}]}


def _ends_with_newline(text):
    return text.endswith(("\n", "\r"))


class ProjectPatchSession:
    def __init__(self, root, manifest):
        self.root = validate_target(root)
        if not self.root.is_dir():
            raise PatchError("Project patch root must be a folder.")
        self.manifest = copy.deepcopy(self._parse(manifest))
        self.results = []
        self.outcomes = []
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
        if not isinstance(manifest, dict):
            raise PatchError("Project patch must be an object.")
        version = manifest.get("version", 1)
        if version == 2:
            parse_changeset(manifest)
            return manifest
        if version != 1:
            raise PatchError("Unsupported project patch version.")
        if not isinstance(manifest.get("files"), list):
            raise PatchError("Version 1 project patch must have a 'files' list.")
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
        if self.manifest.get("version", 1) == 2:
            return
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
        # apply_all normalizes through this same strict parser to record undo data, so
        # unknown fields and malformed hunks must be refused at review, not after approval.
        parse_changeset(self.manifest)

    def review(self, force_indent=False):
        """Validate every file independently; plan results exist only when all are valid."""
        self._force_indent = force_indent
        self.results = []
        self.outcomes = []
        self._reviewed_operations = []
        if self.manifest.get("version", 1) == 2:
            simulation = VirtualTree(self.root).simulate(
                parse_changeset(self.manifest), force_indent=force_indent)
            errors = {item["index"]: item for item in simulation.errors}
            warnings = {}
            for item in simulation.warnings:
                warnings.setdefault(item["index"], []).append(item["message"])
            outcomes = []
            for index, detail in enumerate(simulation.operations):
                kind = detail["op"]
                relative = detail.get("path") or f"{detail.get('from')} → {detail.get('to')}"
                error = errors.get(index)
                item = {"index": index, "op": kind, "relative_path": relative,
                        "status": "error" if error else "ready",
                        "error": error["error"] if error else None,
                        "path": detail.get("resolved_paths", [self.root])[0],
                        "paths": detail.get("resolved_paths", []),
                        "source": detail.get("from"), "destination": detail.get("to"),
                        "warnings": warnings.get(index, [])}
                if "original" in detail:
                    item.update(original=detail["original"], patched=detail["patched"],
                                additions=DiffFile(relative, detail["original"], detail["patched"]).additions,
                                deletions=DiffFile(relative, detail["original"], detail["patched"]).deletions)
                elif kind == "create":
                    item.update(original="", patched=detail["content"].decode("utf-8"))
                elif kind == "delete":
                    item.update(original=detail.get("content", b"").decode("utf-8", "replace"), patched="")
                outcomes.append(item)
            self.outcomes = outcomes
            if not simulation.errors:
                self._reviewed_operations = copy.deepcopy(simulation.operations)
                self.results = outcomes
            return outcomes
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
        self.outcomes = outcomes
        return outcomes

    def validate_all(self, force_indent=False):
        outcomes = self.review(force_indent)
        errors = [outcome["error"] for outcome in outcomes if outcome["status"] == "error"]
        if errors:
            raise PatchError("; ".join(errors))
        return self.results

    def apply_all(self, backup=None, record=None, recover=None):
        """Apply the reviewed changeset as one rollback-capable transaction.

        ``backup`` and ``recover`` are optional callables taking ``[(path, original_bytes, mode)]``
        and returning a description of where the bytes were stored. Backups are captured
        before mutation; deletes stay quarantined until the entire changeset commits.
        """
        if not self._reviewed_operations:
            self.validate_all(self._force_indent)
        simulation = Simulation(operations=copy.deepcopy(self._reviewed_operations))
        result = apply_operations(self.root, simulation, backup=backup, record=record,
                                  forward=parse_changeset(self.manifest).as_dict(), recover=recover)
        self.results = []
        self._reviewed_operations = []
        return result["paths"]


def project_patch_diff(results):
    diffs = [DiffFile(result["relative_path"], result["original"], result["patched"])
             for result in results if "original" in result and "patched" in result]
    text = unified_diff_text(diffs)
    structural = [f"{result.get('op', 'operation').upper()} {result['relative_path']}"
                  for result in results if "original" not in result]
    return "\n".join(part for part in (text, "\n".join(structural)) if part)
