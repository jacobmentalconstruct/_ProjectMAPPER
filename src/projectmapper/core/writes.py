"""Atomic, permission-preserving file write helpers."""

import os
from pathlib import Path
import stat
import tempfile


def stage_bytes(destination, data, mode=None, prefix=".projectmapper-"):
    destination = Path(destination)
    scratch = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=prefix, delete=False) as stream:
            scratch = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is None and destination.exists():
            mode = stat.S_IMODE(destination.stat().st_mode)
        if mode is not None:
            os.chmod(scratch, mode)
        return scratch
    except Exception:
        if scratch is not None and scratch.exists():
            scratch.unlink()
        raise


def atomic_write_bytes(destination, data, mode=None, prefix=".projectmapper-"):
    destination = Path(destination)
    scratch = stage_bytes(destination, data, mode=mode, prefix=prefix)
    try:
        os.replace(scratch, destination)
        return destination
    finally:
        if scratch.exists():
            scratch.unlink()


def backup_path(destination):
    destination = Path(destination)
    return destination.with_name(destination.name + ".bak")


def create_backup(destination, data=None):
    """Write a recoverable sibling backup using the same atomic primitive."""
    destination = Path(destination)
    if data is None:
        data = destination.read_bytes()
    mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else None
    target = backup_path(destination)
    scratch = stage_bytes(target, data, mode=mode, prefix=".projectmapper-backup-")
    try:
        os.link(scratch, target)
        return target
    finally:
        scratch.unlink(missing_ok=True)
