"""Atomic, permission-preserving file write helpers."""

import os
from pathlib import Path
import stat
import tempfile


def discard_scratch(path):
    """Remove a scratch file if present. Never raises: a cleanup failure must not mask
    the outcome it follows. Returns False when the file could not be removed."""
    try:
        Path(path).unlink(missing_ok=True)
        return True
    except OSError:
        return False


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
        if scratch is not None:
            discard_scratch(scratch)
        raise


def atomic_write_bytes(destination, data, mode=None, prefix=".projectmapper-"):
    destination = Path(destination)
    scratch = stage_bytes(destination, data, mode=mode, prefix=prefix)
    try:
        os.replace(scratch, destination)
        return destination
    finally:
        discard_scratch(scratch)
