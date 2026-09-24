"""Managed backup generations: a scoped store of verified, app-owned file copies.

A generation is one directory holding numbered blobs and a ``manifest.json``. The
manifest is written last and atomically; it is the commit marker. Ownership means:
inside the managed directory, a valid manifest, and blobs matching their recorded
sha256. Anything else in the store is ignored and never modified.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
from uuid import uuid4

from .config import OUTPUT_ROOT_NAME
from .writes import discard_scratch, stage_bytes

FORMAT = "projectmapper-backup"
VERSION = 1
KINDS = ("backup", "pre-restore", "recovery")
MANIFEST = "manifest.json"
_NAME = re.compile(r"^\d{8}T\d{12}Z-[0-9a-z]{1,16}$")
_STORED = re.compile(r"^\d{4}\.bin$")


class BackupError(RuntimeError):
    """A backup could not be written or is not a verified, app-owned generation."""


@dataclass
class Generation:
    id: str
    path: Path
    status: str                      # ok | incomplete | corrupt
    scope: str = ""
    kind: str = ""
    action: str = ""
    operation_id: str = ""
    created_at: str = ""
    files: list = field(default_factory=list)
    size: int = 0
    problem: str = ""

    def to_dict(self):
        return {"id": self.id, "status": self.status, "scope": self.scope, "kind": self.kind,
                "action": self.action, "operation_id": self.operation_id, "created_at": self.created_at,
                "files": [dict(item) for item in self.files], "size": self.size, "problem": self.problem}


def user_backup_dir():
    """Per-user store for targets outside the mapper root."""
    override = os.environ.get("PROJECTMAPPER_USER_BACKUPS")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ProjectMapper" / "backups"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ProjectMapper" / "backups"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "projectmapper" / "backups"


def _suffix():
    return uuid4().hex[:8]


def _is_link(path):
    """Symlinks, junctions and other reparse points are never treated as generations."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _write_blob(path, data, mode):
    scratch = stage_bytes(path, data, mode=mode, prefix=".projectmapper-backup-")
    try:
        os.link(scratch, path)  # exclusive: never replaces an existing name
    finally:
        discard_scratch(scratch)


class BackupStore:
    def __init__(self, directory, scope, root=None):
        self.directory = Path(directory)
        self.scope = scope
        self.root = Path(root).resolve() if root is not None else None

    @classmethod
    def for_project(cls, root):
        root = Path(root).resolve()
        return cls(root / OUTPUT_ROOT_NAME / "backups", "project", root)

    @classmethod
    def for_user(cls):
        return cls(user_backup_dir(), "user")

    @classmethod
    def for_target(cls, target, root):
        """Project scope for targets inside the mapper root; the per-user store otherwise."""
        target, root = Path(target).resolve(), Path(root).resolve()
        return cls.for_project(root) if target.is_relative_to(root) else cls.for_user()

    # --- target naming -------------------------------------------------

    def target_key(self, path):
        path = Path(path).resolve()
        if self.scope == "user":
            return str(path)
        if not path.is_relative_to(self.root):
            raise BackupError(f"{path} is outside the project backup scope.")
        return path.relative_to(self.root).as_posix()

    def target_path(self, key):
        return Path(key) if self.scope == "user" else self.root / PurePosixPath(key)

    def _valid_key(self, key):
        if not isinstance(key, str) or not key:
            return False
        if self.scope == "user":
            return Path(key).is_absolute()
        pure = PurePosixPath(key)
        return not pure.is_absolute() and ".." not in pure.parts and not Path(key).is_absolute()

    # --- writing -------------------------------------------------------

    def create(self, kind, action, operation_id, files):
        """Write one generation for ``files`` = [(target_path, bytes, mode)]."""
        if kind not in KINDS:
            raise BackupError(f"Unknown backup kind: {kind}")
        entries = [(self.target_key(path), data, mode) for path, data, mode in files]
        if not entries:
            raise BackupError("A backup generation needs at least one file.")
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc)
        for _ in range(8):
            name = f"{stamp:%Y%m%dT%H%M%S%f}Z-{_suffix()}"
            path = self.directory / name
            try:
                path.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise BackupError("Could not allocate a unique backup generation name.")
        try:
            records = []
            for number, (key, data, mode) in enumerate(entries, 1):
                stored = f"{number:04d}.bin"
                _write_blob(path / stored, data, mode)
                records.append({"target": key, "stored": stored, "sha256": _sha256(data),
                                "size": len(data), "mode": mode})
            manifest = {"format": FORMAT, "version": VERSION, "scope": self.scope, "kind": kind,
                        "action": action, "operation_id": operation_id,
                        "created_at": stamp.isoformat(), "files": records}
            _write_blob(path / MANIFEST, json.dumps(manifest, indent=2).encode("utf-8"), None)
        except Exception as exc:
            # Only this call created ``path``; nothing else can live in it yet.
            shutil.rmtree(path, ignore_errors=True)
            raise BackupError(f"Backup was not written: {exc}") from exc
        return self.get(name)

    # --- reading -------------------------------------------------------

    def list(self):
        """Generations newest first. Entries not named like generations are ignored."""
        if not self.directory.is_dir():
            return []
        names = [entry.name for entry in os.scandir(self.directory)
                 if entry.is_dir(follow_symlinks=False) and _NAME.match(entry.name) and not _is_link(entry.path)]
        return [self.get(name) for name in sorted(names, reverse=True)]

    def get(self, generation_id):
        if not isinstance(generation_id, str) or not _NAME.match(generation_id):
            raise BackupError(f"Not a backup generation id: {generation_id}")
        path = self.directory / generation_id
        if _is_link(path) or not path.is_dir():
            raise BackupError(f"Backup generation not found: {generation_id}")
        generation = Generation(generation_id, path, "incomplete", scope=self.scope)
        manifest_path = path / MANIFEST
        if not manifest_path.is_file():
            generation.problem = "no manifest (interrupted or not written by ProjectMapper)"
            return generation
        generation.status = "corrupt"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self._validate(manifest)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            generation.problem = f"invalid manifest: {exc}"
            return generation
        generation.kind, generation.action = manifest["kind"], manifest["action"]
        generation.operation_id, generation.created_at = manifest["operation_id"], manifest["created_at"]
        generation.files = manifest["files"]
        generation.size = sum(item["size"] for item in manifest["files"])
        for item in manifest["files"]:
            blob = path / item["stored"]
            try:
                data = blob.read_bytes()
            except OSError as exc:
                generation.problem = f"{item['target']}: blob unreadable: {exc}"
                return generation
            if len(data) != item["size"] or _sha256(data) != item["sha256"]:
                generation.problem = f"{item['target']}: sha256 or size mismatch"
                return generation
        generation.status = "ok"
        return generation

    def _validate(self, manifest):
        if manifest.get("format") != FORMAT:
            raise ValueError("not a ProjectMapper backup manifest")
        if manifest.get("version") != VERSION:
            raise ValueError(f"unsupported version {manifest.get('version')!r}")
        if manifest.get("scope") != self.scope:
            raise ValueError("scope does not match this store")
        if manifest.get("kind") not in KINDS:
            raise ValueError(f"unknown kind {manifest.get('kind')!r}")
        for key in ("action", "operation_id", "created_at"):
            if not isinstance(manifest.get(key), str):
                raise ValueError(f"{key} must be text")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError("files must be a non-empty list")
        seen = set()
        for item in files:
            if not isinstance(item, dict) or not _STORED.match(str(item.get("stored", ""))):
                raise ValueError("invalid stored blob name")
            if not self._valid_key(item.get("target")):
                raise ValueError(f"unsafe target {item.get('target')!r}")
            if item["stored"] in seen:
                raise ValueError("duplicate stored blob name")
            seen.add(item["stored"])
            if not isinstance(item.get("size"), int) or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256"))):
                raise ValueError("invalid size or sha256")
            if item.get("mode") is not None and not isinstance(item["mode"], int):
                raise ValueError("invalid mode")

    def fingerprint(self, generation_id):
        """sha256 of the manifest bytes, used to bind a clean-up plan to what was reviewed."""
        return _sha256((self.get(generation_id).path / MANIFEST).read_bytes())

    def remove(self, generation_id, expected_fingerprint):
        """Delete one verified generation that still matches its reviewed manifest.

        Only the manifest and its recorded blobs are unlinked, then the empty directory is
        removed. Links, unexpected entries or any mismatch leave the directory in place.
        """
        generation = self.get(generation_id)
        if generation.status != "ok":
            raise BackupError(f"{generation_id} is {generation.status}; only verified generations are removed.")
        if self.fingerprint(generation_id) != expected_fingerprint:
            raise BackupError(f"{generation_id} changed after it was reviewed.")
        expected = {MANIFEST, *(item["stored"] for item in generation.files)}
        entries = list(os.scandir(generation.path))
        unexpected = sorted(entry.name for entry in entries
                            if entry.name not in expected or _is_link(entry.path) or not entry.is_file(follow_symlinks=False))
        if unexpected:
            raise BackupError(f"{generation_id} contains unexpected entries ({', '.join(unexpected)}); left in place.")
        # Manifest first: an interrupted removal leaves an "incomplete" generation, never a usable one.
        for name in [MANIFEST] + sorted(expected - {MANIFEST}):
            (generation.path / name).unlink()
        generation.path.rmdir()

    def read(self, generation_id, target):
        """Return the verified bytes of ``target`` from an ``ok`` generation."""
        generation = self.get(generation_id)
        if generation.status != "ok":
            raise BackupError(f"Backup {generation_id} is {generation.status}: {generation.problem}")
        for item in generation.files:
            if item["target"] == target:
                data = (generation.path / item["stored"]).read_bytes()
                if _sha256(data) != item["sha256"]:
                    raise BackupError(f"Backup {generation_id} changed while reading {target}.")
                return data
        raise BackupError(f"{target} is not in backup {generation_id}.")
