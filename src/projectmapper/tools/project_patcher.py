"""Validated, all-or-nothing multi-file patches for one project root."""

import hashlib
import json
import os
from pathlib import Path
import stat
import copy

from .patcher import PatchError, apply_patch_text, validate_target
try:
    from ..core.diff import DiffFile, unified_diff_text
    from ..core.writes import atomic_write_bytes, create_backup, stage_bytes
except ImportError:
    from core.diff import DiffFile, unified_diff_text
    from core.writes import atomic_write_bytes, create_backup, stage_bytes


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


class ProjectPatchSession:
    def __init__(self, root, manifest):
        self.root = validate_target(root)
        if not self.root.is_dir():
            raise PatchError("Project patch root must be a folder.")
        self.manifest = copy.deepcopy(self._parse(manifest))
        self.results = []
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
        if not isinstance(relative, str) or not relative.strip():
            raise PatchError("Each file entry needs a relative path.")
        rel = relative.replace("\\", "/")
        candidate = (self.root / Path(rel)).absolute()
        if Path(rel).is_absolute() or any(part == ".." for part in Path(rel).parts):
            raise PatchError(f"Unsafe project patch path: {relative}")
        candidate = validate_target(candidate)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise PatchError(f"Project patch path escapes the project root: {relative}") from exc
        if any(part.casefold() == ".parts" for part in candidate.relative_to(self.root).parts):
            raise PatchError("The .parts reference folder is read-only.")
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

    def validate_all(self, force_indent=False):
        self.results = []
        results = []
        for entry in self.manifest["files"]:
            path = self._resolve(entry["path"])
            original_bytes = path.read_bytes()
            actual_hash = _sha256(original_bytes)
            expected = entry.get("sha256")
            if expected and expected.casefold() != actual_hash:
                raise PatchError(f"Source changed for {entry['path']}; expected sha256 {expected}, found {actual_hash}.")
            try:
                original = original_bytes.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise PatchError(f"{entry['path']} is not valid UTF-8 text.") from exc
            if "\x00" in original:
                raise PatchError(f"{entry['path']} appears to be binary.")
            patched = apply_patch_text(original, {"hunks": entry["hunks"]}, force_indent)
            results.append({"path": path, "relative_path": entry["path"], "original_bytes": original_bytes,
                            "original": original, "patched": patched, "sha256": actual_hash})
        self.results = results
        return results

    def apply_all(self, backup=False):
        if not self.results:
            self.validate_all()
        results = copy.deepcopy(self.results)
        scratch = []
        committed = []
        recovery_errors = []
        cleanup_errors = []
        failure = None
        try:
            for result in results:
                destination = validate_target(result["path"])
                if destination.read_bytes() != result["original_bytes"]:
                    raise PatchError(f"Source changed after validation: {result['relative_path']}")
                result["mode"] = stat.S_IMODE(destination.stat().st_mode)
                result["output_bytes"] = (b"\xef\xbb\xbf" if result["original_bytes"].startswith(b"\xef\xbb\xbf") else b"") + result["patched"].encode("utf-8")
                staged = stage_bytes(destination, result["output_bytes"], mode=result["mode"], prefix=".project-patch-")
                scratch.append((staged, result))
            for _, result in scratch:
                if validate_target(result["path"]).read_bytes() != result["original_bytes"]:
                    raise PatchError(f"Source changed during staging: {result['relative_path']}")
            if backup:
                for result in results:
                    create_backup(result["path"], result["original_bytes"])
            for staged, result in scratch:
                if validate_target(result["path"]).read_bytes() != result["original_bytes"]:
                    raise PatchError(f"Source changed before replacement: {result['relative_path']}")
                os.replace(staged, result["path"])
                committed.append(result)
        except Exception as exc:
            failure = exc
            for result in reversed(committed):
                try:
                    destination = validate_target(result["path"])
                    if destination.read_bytes() != result["output_bytes"]:
                        raise PatchError("External change preserved; original retained in this session")
                    atomic_write_bytes(destination, result["original_bytes"], mode=result["mode"])
                except (OSError, PatchError) as rollback_exc:
                    recovery_errors.append(f"{result['relative_path']}: {rollback_exc}")
        finally:
            for staged, _ in scratch:
                try:
                    staged.unlink(missing_ok=True)
                except OSError as exc:
                    cleanup_errors.append(f"{staged}: {exc}")
        if failure is not None or cleanup_errors:
            prefix = "Recovery required" if recovery_errors else ("Project patch rolled back" if committed and failure else "Project patch stopped")
            detail = f"{prefix}: {failure or 'temporary file cleanup failed'}"
            if recovery_errors:
                detail += "; " + "; ".join(recovery_errors)
            if cleanup_errors:
                detail += "; cleanup: " + "; ".join(cleanup_errors)
            raise PatchError(detail) from failure
        self.results = []
        return [result["path"] for result in results]


def project_patch_diff(results):
    return unified_diff_text(DiffFile(result["relative_path"], result["original"], result["patched"])
                             for result in results)
