"""Transactional writes for reviewed project changes."""

import copy
import os
import stat

from .paths import PathSafetyError, SourceChangedError, validate_target
from .writes import atomic_write_bytes, stage_bytes


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
        raise SourceChangedError(f"Source changed {when}: {result['relative_path']}") from exc
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
