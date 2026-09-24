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
