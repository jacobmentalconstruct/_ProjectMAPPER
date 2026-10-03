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


def _changeset_record(root, operations, backup_items, forward):
    """Build portable inverse operations and final fingerprints for one committed plan."""
    backup_by_identity = {}
    backup_data_by_identity = {}
    for path, data, mode in backup_items:
        relative = Path(path).relative_to(root).as_posix()
        backup_by_identity[_identity(Path(path).stat())] = relative
        backup_data_by_identity[_identity(Path(path).stat())] = data

    original_files = {}
    states = {}

    def ensure(relative, expected):
        key = relative.casefold()
        if key not in states:
            identity = expected.get("identity")
            data = None
            if identity is not None:
                original = next((item for item in backup_items
                                 if _identity(Path(item[0]).stat()) == identity), None)
                if original is not None:
                    data = original[1]
                    original_files[identity] = Path(original[0]).relative_to(root).as_posix()
            states[key] = {"path": relative, "kind": expected.get("kind"),
                           "sha256": expected.get("sha256"), "mode": expected.get("mode"),
                           "identity": identity, "data": data}
        return states[key]

    def backup_reference(identity):
        return original_files.get(identity) or backup_by_identity.get(identity)

    def restore(path, expected, data):
        identity = expected.get("identity")
        reference = backup_reference(identity)
        item = {"op": "restore", "path": path, "mode": expected.get("mode")}
        if reference is not None and data == backup_data_by_identity.get(identity):
            item["from_backup"] = reference
        elif data is not None:
            item["content"] = data.decode("utf-8")
        else:
            raise PathSafetyError(f"Cannot record undo data for {path}.")
        return item

    inverse_groups = []
    for operation in operations:
        kind = operation["op"]
        before = operation.get("before", {})
        for relative, expected in before.items():
            state = ensure(relative, expected)
            if state["data"] is None and expected.get("identity") is not None:
                identity = expected["identity"]
                original = next((item for item in backup_items
                                 if _identity(Path(item[0]).stat()) == identity), None)
                if original is not None:
                    state["data"] = original[1]
                    original_files[identity] = Path(original[0]).relative_to(root).as_posix()

        if kind == "patch":
            path = operation["path"]
            expected = before[path]
            data = operation.get("original_bytes") or states[path.casefold()]["data"]
            group = [restore(path, expected, data)]
            output = operation["content"]
            states[path.casefold()].update(kind="file", sha256=hashlib.sha256(output).hexdigest(),
                                           data=output)
        elif kind == "create":
            path, data = operation["path"], operation["content"]
            group = [{"op": "delete", "path": path,
                      "sha256": hashlib.sha256(data).hexdigest()}]
            states[path.casefold()].update(path=path, kind="file",
                                           sha256=hashlib.sha256(data).hexdigest(),
                                           mode=None, identity=None, data=data)
        elif kind == "mkdir":
            path = operation["path"]
            group = [{"op": "delete_dir", "path": path}]
            states[path.casefold()].update(path=path, kind="dir", sha256=None, data=None)
        elif kind in {"move", "move_dir"}:
            source, destination = operation["from"], operation["to"]
            group = [{"op": kind, "from": destination, "to": source}]
            prefix = source.casefold().rstrip("/")
            moved = [(key, state) for key, state in list(states.items())
                     if key == prefix or key.startswith(prefix + "/")]
            for key, state in moved:
                suffix = state["path"][len(source):]
                target = destination + suffix
                moved_state = dict(state)
                states[key].update(kind="missing", sha256=None, mode=None, identity=None, data=None)
                states[target.casefold()] = {**moved_state, "path": target}
            if not moved:
                raise PathSafetyError(f"Cannot record moved source {source}.")
        elif kind == "delete":
            path = operation["path"]
            expected = before[path]
            state = states[path.casefold()]
            group = [restore(path, expected, state["data"])]
            state.update(kind="missing", sha256=None, mode=None, identity=None, data=None)
        elif kind == "delete_dir":
            path = operation["path"]
            expected_root = before[path]
            prefix = path.casefold().rstrip("/")
            members = [(key, state) for key, state in states.items()
                       if key == prefix or key.startswith(prefix + "/")]
            if len(members) == 1:
                group = [{"op": "mkdir", "path": path, "mode": expected_root.get("mode")}]
            else:
                dirs = sorted((state for _, state in members if state["kind"] == "dir"),
                              key=lambda state: (state["path"].count("/"), state["path"].casefold()))
                files = sorted((state for _, state in members if state["kind"] == "file"),
                               key=lambda state: state["path"].casefold())
                group = [{"op": "mkdir", "path": state["path"], "mode": state.get("mode")}
                         for state in dirs]
                group.extend(restore(state["path"], before[state["path"]], state["data"])
                             for state in files)
            for _, state in members:
                state.update(kind="missing", sha256=None, mode=None, identity=None, data=None)
        else:
            raise PathSafetyError(f"Cannot record undo for operation {kind}.")
        inverse_groups.append(group)

    inverse = [item for group in reversed(inverse_groups) for item in group]
    post_state = [{"target": state["path"], "kind": state["kind"],
                   "sha256": state["sha256"], "mode": state["mode"]}
                  for state in sorted(states.values(), key=lambda item: item["path"].casefold())]
    return {"forward": copy.deepcopy(forward),
            "inverse": {"version": 2, "ops": inverse}, "post_state": post_state}


def prepare_undo(root, changeset, read_backup):
    """Build a reviewed executor simulation from a stored inverse changeset."""
    from .vtree import Simulation

    root = Path(root).absolute()
    states = {item["target"].casefold(): dict(item) for item in changeset.get("post_state", [])}
    operations = []

    def current(relative):
        return states.get(relative.casefold(), {"target": relative, "kind": "missing",
                                                "sha256": None, "mode": None})

    def before_entry(relative):
        state = current(relative)
        return {"kind": state["kind"], "sha256": state.get("sha256"),
                "mode": state.get("mode"), "identity": None}

    def update(relative, kind, data=None, mode=None, sha256=None):
        digest = (hashlib.sha256(data).hexdigest() if data is not None else sha256) if kind == "file" else None
        states[relative.casefold()] = {"target": relative, "kind": kind,
                                       "sha256": digest, "mode": mode}

    for index, inverse in enumerate(changeset["inverse"]["ops"]):
        kind = inverse.get("op")
        if kind == "restore":
            relative = inverse["path"]
            if "from_backup" in inverse:
                content = read_backup(inverse["from_backup"])
            elif isinstance(inverse.get("content"), str):
                content = inverse["content"].encode("utf-8")
            else:
                raise PathSafetyError(f"Undo data is missing for {relative}.")
            operations.append({"index": index, "op": "restore", "path": relative,
                               "before": {relative: before_entry(relative)},
                               "content": content, "mode": inverse.get("mode")})
            update(relative, "file", content, inverse.get("mode"))
        elif kind == "delete":
            relative = inverse["path"]
            entry = {relative: before_entry(relative)}
            operations.append({"index": index, "op": "delete", "path": relative,
                               "before": entry})
            update(relative, "missing")
        elif kind == "delete_dir":
            relative = inverse["path"]
            prefix = relative.casefold().rstrip("/")
            members = {key: state for key, state in states.items()
                       if key == prefix or key.startswith(prefix + "/")}
            entry = {state["target"]: before_entry(state["target"])
                     for state in members.values()}
            operations.append({"index": index, "op": "delete_dir", "path": relative,
                               "before": entry})
            for state in members.values():
                update(state["target"], "missing")
        elif kind == "mkdir":
            relative = inverse["path"]
            operations.append({"index": index, "op": "mkdir", "path": relative,
                               "before": {relative: before_entry(relative)},
                               "mode": inverse.get("mode")})
            update(relative, "dir")
        elif kind in {"move", "move_dir"}:
            source, destination = inverse["from"], inverse["to"]
            prefix = source.casefold().rstrip("/")
            members = {key: state for key, state in states.items()
                       if key == prefix or (kind == "move_dir" and key.startswith(prefix + "/"))}
            if prefix not in members:
                raise PathSafetyError(f"Undo source does not exist in the reviewed result: {source}.")
            entry = {state["target"]: before_entry(state["target"])
                     for state in members.values()}
            same_case_key = source.casefold() == destination.casefold()
            if not same_case_key:
                entry[destination] = before_entry(destination)
            operations.append({"index": index, "op": kind, "from": source, "to": destination,
                               "before": entry})
            moved = []
            for state in members.values():
                suffix = state["target"][len(source):]
                moved.append((state, destination + suffix))
            for state, target in moved:
                update(state["target"], "missing")
            for state, target in moved:
                update(target, state["kind"], mode=state.get("mode"),
                       sha256=state.get("sha256"))
        else:
            raise PathSafetyError(f"Unsupported inverse operation: {kind}.")
    return Simulation(operations=operations)


def apply_operations(root, simulation, *, backup=None, record=None, forward=None,
                     recover=None, operation_id=None):
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
    change_record = None
    record_result = None
    if record is not None:
        if not isinstance(forward, dict):
            raise PathSafetyError("A changeset record requires its forward manifest.")
        change_record = _changeset_record(root, operations, backup_items, forward)
        try:
            record_result = record(backup_items, change_record)
        except Exception as exc:
            raise PathSafetyError(f"Changeset backup failed: {exc}") from exc

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
            elif kind == "restore":
                path = resolve_in_root(root, operation["path"])
                actual = _inspect(root, operation["path"])
                output = operation["content"]
                mode = operation.get("mode")
                if actual["kind"] == "missing":
                    staged = stage_bytes(path, output, mode=mode, prefix=".projectmapper-restore-")
                    scratch.append(staged)
                    _ensure_state(root, states)
                    os.link(staged, path)
                    journal.append({"index": index, "kind": "create", "path": path,
                                    "content": output})
                    staged.unlink()
                    scratch.remove(staged)
                elif actual["kind"] == "file":
                    original = actual["data"]
                    original_mode = actual["mode"]
                    staged = stage_bytes(path, output, mode=mode, prefix=".projectmapper-restore-")
                    scratch.append(staged)
                    _ensure_state(root, states)
                    os.replace(staged, path)
                    scratch.remove(staged)
                    journal.append({"index": index, "kind": "patch", "path": path,
                                    "original": original, "output": output, "mode": original_mode})
                else:
                    raise PathSafetyError(f"Restore target is not a file: {operation['path']}.")
                touched.append(path)
            elif kind == "mkdir":
                path = resolve_in_root(root, operation["path"])
                path.mkdir()
                journal.append({"index": index, "kind": kind, "path": path})
                if operation.get("mode") is not None:
                    path.chmod(operation["mode"])
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
    return {"paths": list(dict.fromkeys(touched)), "operations": operations,
            "changeset": record_result}
