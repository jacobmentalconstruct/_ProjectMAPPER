"""Transactional writes for reviewed project changes."""

import copy
import hashlib
import os
from pathlib import Path
import shutil
import stat
from uuid import uuid4

from .config import OUTPUT_ROOT_NAME
from .paths import PathSafetyError, SourceChangedError, resolve_in_root, validate_target
from .writes import atomic_write_bytes, discard_scratch, stage_bytes


class RecoveryRequiredError(PathSafetyError):
    """A transaction could not roll back without preserving external changes."""

    code = "recovery_required"


def _identity(info):
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns


def _recheck(result, when):
    destination = validate_target(result["path"])
    try:
        before = destination.stat()
        data = destination.read_bytes()
        after = destination.stat()
    except OSError as exc:
        raise SourceChangedError(
            f"Source changed {when}: {result['relative_path']} ({exc})") from exc
    if (_identity(before) != _identity(after)
            or _identity(after) != result["identity"]
            or data != result["original_bytes"]):
        raise SourceChangedError(f"Source changed {when}: {result['relative_path']}")
    return destination


def apply_patches(validated, *, backup=None, recover=None):
    """Atomically apply a validated set of text patches or restore every committed file.

    The callbacks accept ``[(path, original_bytes, mode)]``. Backups are written before
    the first replacement; recovery storage is used only if rollback cannot finish safely.
    """
    results = copy.deepcopy(validated)
    staged = []
    committed = []
    recovery = []
    cleanup = []
    failure = None
    try:
        for result in results:
            destination = _recheck(result, "after validation")
            result["mode"] = stat.S_IMODE(destination.stat().st_mode)
            result["output_bytes"] = (
                b"\xef\xbb\xbf" if result["original_bytes"].startswith(b"\xef\xbb\xbf") else b""
            ) + result["patched"].encode("utf-8")
            scratch = stage_bytes(destination, result["output_bytes"], mode=result["mode"],
                                  prefix=".project-patch-")
            staged.append((scratch, result))
        for _, result in staged:
            _recheck(result, "during staging")
        if backup is not None:
            backup([(item["path"], item["original_bytes"], item["mode"]) for item in results])
        for scratch, result in staged:
            destination = _recheck(result, "before replacement")
            os.replace(scratch, destination)
            committed.append(result)
    except Exception as exc:
        failure = exc
        unrestored = []
        for result in reversed(committed):
            try:
                destination = validate_target(result["path"])
                if destination.read_bytes() != result["output_bytes"]:
                    raise PathSafetyError("External change preserved")
                atomic_write_bytes(destination, result["original_bytes"], mode=result["mode"])
            except (OSError, PathSafetyError) as rollback_error:
                recovery.append(f"{result['relative_path']}: {rollback_error}")
                unrestored.append(result)
        if unrestored:
            if recover is None:
                recovery.append("original bytes were not saved (no recovery store configured)")
            else:
                try:
                    location = recover([(item["path"], item["original_bytes"], item["mode"])
                                        for item in unrestored])
                    recovery.append(f"originals saved in recovery backup {location}")
                except Exception as store_error:
                    recovery.append(f"originals could not be saved: {store_error}")
    finally:
        for scratch, _ in staged:
            try:
                scratch.unlink(missing_ok=True)
            except OSError as exc:
                cleanup.append(f"{scratch}: {exc}")

    if failure is not None or cleanup:
        prefix = ("Recovery required" if recovery else
                  "Project patch rolled back" if committed and failure else "Project patch stopped")
        detail = f"{prefix}: {failure or 'temporary file cleanup failed'}"
        if recovery:
            detail += "; " + "; ".join(recovery)
        if cleanup:
            detail += "; cleanup: " + "; ".join(cleanup)
        if recovery:
            raise RecoveryRequiredError(detail) from failure
        if isinstance(failure, PathSafetyError) and getattr(failure, "code", None):
            raise type(failure)(detail) from failure
        raise PathSafetyError(detail) from failure
    return [item["path"] for item in results]


def _inspect(root, relative):
    path = resolve_in_root(root, relative)
    if path.is_symlink():
        raise PathSafetyError(f"Linked paths cannot be changed: {relative}.")
    try:
        before = path.stat()
    except FileNotFoundError:
        return {"path": path, "kind": "missing", "mode": None, "identity": None,
                "sha256": None, "data": None}
    mode = stat.S_IMODE(before.st_mode)
    identity = _identity(before)
    if stat.S_ISDIR(before.st_mode):
        return {"path": path, "kind": "dir", "mode": mode, "identity": identity,
                "sha256": None, "data": None}
    if not stat.S_ISREG(before.st_mode):
        raise PathSafetyError(f"Target is not a regular file or folder: {relative}.")
    try:
        data = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise SourceChangedError(f"Could not recheck {relative}: {exc}") from exc
    if identity != _identity(after):
        raise SourceChangedError(f"Source changed while being checked: {relative}.")
    return {"path": path, "kind": "file", "mode": mode, "identity": identity,
            "sha256": hashlib.sha256(data).hexdigest(), "data": data}


def _matches_state(actual, expected, *, identity=False):
    if actual["kind"] != expected.get("kind"):
        return False
    if actual["kind"] == "missing":
        return True
    if expected.get("mode") is not None and actual["mode"] != expected["mode"]:
        return False
    if expected.get("sha256") is not None and actual["sha256"] != expected["sha256"]:
        return False
    return not identity or expected.get("identity") is None or actual["identity"] == expected["identity"]


def _case_only_pair(source, destination):
    return (source.parent == destination.parent
            and source.name.casefold() == destination.name.casefold()
            and source.name != destination.name)


def _same_file(source, destination):
    try:
        return os.path.samefile(source, destination)
    except OSError:
        return False


def _rename_no_replace(source, destination):
    """Move one path without replacing an existing destination."""
    source, destination = Path(source), Path(destination)
    if source == destination:
        return
    if _case_only_pair(source, destination):
        temporary = source.with_name(f".{source.name}.projectmapper-{uuid4().hex}.tmp")
        os.rename(source, temporary)
        try:
            os.rename(temporary, destination)
        except OSError as exc:
            try:
                os.rename(temporary, source)
            except OSError as rollback_error:
                raise RecoveryRequiredError(
                    f"Case-only rename failed; original remains at {temporary}: {rollback_error}") from exc
            raise
        return
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Destination already exists: {destination}.")
    if source.is_file() and os.name != "nt":
        os.link(source, destination)
        try:
            source.unlink()
        except OSError:
            if _same_file(source, destination):
                destination.unlink(missing_ok=True)
            raise
        return
    # Windows rename refuses replacement; POSIX gets an explicit destination check above.
    os.rename(source, destination)


def _ensure_state(root, states, *, aliases=()):
    alias_paths = [resolve_in_root(root, path) for path in aliases]
    for relative, expected in states.items():
        actual = _inspect(root, relative)
        if expected.get("kind") == "missing" and actual["kind"] != "missing":
            if any(_same_file(actual["path"], alias) for alias in alias_paths):
                continue
        if not _matches_state(actual, expected):
            raise SourceChangedError(f"Source changed before operation: {relative}.")


def _quarantine_root(root, operation_id):
    root = Path(root)
    store = root / OUTPUT_ROOT_NAME
    pending = store / ".pending"
    destination = pending / operation_id
    for path in (store, pending, destination):
        validate_target(path)
        if path.is_symlink():
            raise PathSafetyError(f"Linked quarantine path is not allowed: {path}.")
    destination.mkdir(parents=True, exist_ok=False)
    return destination


def _undo(entry):
    kind = entry["kind"]
    if kind == "patch":
        path = validate_target(entry["path"])
        if path.read_bytes() != entry["output"]:
            raise PathSafetyError("External change preserved")
        atomic_write_bytes(path, entry["original"], mode=entry["mode"])
    elif kind == "create":
        path = validate_target(entry["path"])
        if path.read_bytes() != entry["content"]:
            raise PathSafetyError("External change preserved")
        path.unlink()
    elif kind == "mkdir":
        validate_target(entry["path"]).rmdir()
    elif kind in {"move", "move_dir"}:
        _rename_no_replace(entry["destination"], entry["source"])
    elif kind in {"delete", "delete_dir"}:
        _rename_no_replace(entry["quarantined"], entry["path"])


def apply_operations(root, simulation, *, backup=None, recover=None, operation_id=None):
    """Apply a valid virtual-tree plan as one rollback-capable filesystem transaction.

    ``backup`` and ``recover`` use the same file tuple contract as ``apply_patches``.
    Deletes remain in a same-volume quarantine until every operation has committed.
    """
    if not simulation.valid:
        raise PathSafetyError("Cannot execute a changeset with validation conflicts.")
    root = validate_target(Path(root).absolute())
    operations = copy.deepcopy(simulation.operations)
    baseline = {}
    for operation in operations:
        for relative, expected in operation.get("before", {}).items():
            # Only source objects with a disk identity belong to the reviewed
            # starting tree. Missing destinations and objects created earlier in
            # the virtual plan are checked immediately before their own operation.
            if expected.get("identity") is None:
                continue
            baseline.setdefault(relative.casefold(), (relative, expected))

    initial = {}
    for relative, expected in baseline.values():
        actual = _inspect(root, relative)
        if not _matches_state(actual, expected, identity=True):
            raise SourceChangedError(f"Source changed after review: {relative}.")
        if actual["kind"] != "missing":
            initial[relative] = actual

    by_identity = {item["identity"]: item for item in initial.values()
                   if item["identity"] is not None}
    backup_files = {}
    for operation in operations:
        if operation["op"] not in {"patch", "delete", "delete_dir"}:
            continue
        for relative, expected in operation.get("before", {}).items():
            if expected.get("kind") != "file" or expected.get("identity") is None:
                continue
            original = by_identity.get(expected["identity"])
            if original is not None:
                backup_files[expected["identity"]] = original
    backup_items = [(item["path"], item["data"], item["mode"])
                    for item in backup_files.values()]
    if backup is not None and backup_items:
        try:
            backup(backup_items)
        except Exception as exc:
            raise PathSafetyError(f"Backup failed: {exc}") from exc

    quarantine = None
    if any(item["op"] in {"delete", "delete_dir"} for item in operations):
        quarantine = _quarantine_root(root, operation_id or uuid4().hex)

    journal = []
    scratch = []
    touched = []
    failure = None
    recovery = []
    cleanup = []
    try:
        for operation in operations:
            index, kind = operation["index"], operation["op"]
            states = operation.get("before", {})
            aliases = ([operation["from"]]
                       if kind in {"move", "move_dir"} else ())
            _ensure_state(root, states, aliases=aliases)
            if kind == "patch":
                path = resolve_in_root(root, operation["path"])
                original = path.read_bytes()
                mode = stat.S_IMODE(path.stat().st_mode)
                output = operation["content"]
                staged = stage_bytes(path, output, mode=mode, prefix=".project-patch-")
                scratch.append(staged)
                _ensure_state(root, states)
                os.replace(staged, path)
                scratch.remove(staged)
                journal.append({"index": index, "kind": kind, "path": path,
                                "original": original, "output": output, "mode": mode})
                touched.append(path)
            elif kind == "create":
                path = resolve_in_root(root, operation["path"])
                staged = stage_bytes(path, operation["content"], prefix=".projectmapper-create-")
                scratch.append(staged)
                os.link(staged, path)
                journal.append({"index": index, "kind": kind, "path": path,
                                "content": operation["content"]})
                staged.unlink()
                scratch.remove(staged)
                touched.append(path)
            elif kind == "mkdir":
                path = resolve_in_root(root, operation["path"])
                path.mkdir()
                journal.append({"index": index, "kind": kind, "path": path})
                touched.append(path)
            elif kind in {"move", "move_dir"}:
                source = resolve_in_root(root, operation["from"])
                destination = resolve_in_root(root, operation["to"])
                if source != destination:
                    _rename_no_replace(source, destination)
                    journal.append({"index": index, "kind": kind, "source": source,
                                    "destination": destination})
                    touched.extend((source, destination))
            elif kind in {"delete", "delete_dir"}:
                source = resolve_in_root(root, operation["path"])
                slot = quarantine / str(index)
                slot.mkdir()
                destination = slot / source.name
                _rename_no_replace(source, destination)
                journal.append({"index": index, "kind": kind, "path": source,
                                "quarantined": destination})
                touched.append(source)
            else:
                raise PathSafetyError(f"Unsupported operation at index {index}: {kind}.")
    except Exception as exc:
        failure = exc
        for entry in reversed(journal):
            try:
                _undo(entry)
            except (OSError, PathSafetyError) as rollback_error:
                recovery.append(f"operation {entry['index']}: {rollback_error}")
                if entry.get("quarantined") and entry["quarantined"].exists():
                    recovery.append(f"deleted data remains at {entry['quarantined']}")
    finally:
        for path in scratch:
            if not discard_scratch(path):
                cleanup.append(str(path))

    if failure is not None and quarantine is not None and not recovery:
        try:
            shutil.rmtree(quarantine)
            parent = quarantine.parent
            if not any(parent.iterdir()):
                parent.rmdir()
        except OSError as exc:
            cleanup.append(f"empty quarantine cleanup failed at {quarantine}: {exc}")

    if failure is not None or recovery or cleanup:
        if isinstance(failure, RecoveryRequiredError):
            recovery.append(str(failure))
        if recovery:
            if recover is None:
                recovery.append("original bytes were not saved (no recovery store configured)"
                                if backup_items else "recovery store is not configured")
            elif backup_items:
                try:
                    location = recover(backup_items)
                    recovery.append(f"originals saved in recovery backup {location}")
                except Exception as exc:
                    recovery.append(f"originals could not be saved: {exc}")
        prefix = "Recovery required" if recovery else "Changeset stopped"
        detail = f"{prefix}: {failure or 'temporary file cleanup failed'}"
        if recovery:
            detail += "; " + "; ".join(recovery)
        if cleanup:
            detail += "; scratch cleanup failed: " + ", ".join(cleanup)
        if recovery:
            raise RecoveryRequiredError(detail) from failure
        if isinstance(failure, PathSafetyError) and getattr(failure, "code", None):
            raise type(failure)(detail) from failure
        raise PathSafetyError(detail) from failure

    if quarantine is not None:
        try:
            shutil.rmtree(quarantine)
            parent = quarantine.parent
            if not any(parent.iterdir()):
                parent.rmdir()
        except OSError as exc:
            raise RecoveryRequiredError(
                f"Changes committed, but delete quarantine cleanup failed at {quarantine}: {exc}") from exc
    return {"paths": list(dict.fromkeys(touched)), "operations": operations}
