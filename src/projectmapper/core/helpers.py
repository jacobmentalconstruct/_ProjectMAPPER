"""Filesystem and formatting helpers independent of Tk."""
import os
import hashlib
import gc
import time
from datetime import datetime
from pathlib import Path
from .config import *

def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_display_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size_kb = size_bytes / 1024
    if size_kb < 1024:
        return f"{size_kb:.1f} KB"
    size_mb = size_kb / 1024
    if size_mb < 1024:
        return f"{size_mb:.1f} MB"
    size_gb = size_mb / 1024
    return f"{size_gb:.2f} GB"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def rel_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except Exception:
        return path.name


def is_path_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def is_binary(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as handle:
            return b"\0" in handle.read(1024)
    except Exception:
        return True


def safe_stat_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def safe_stat_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def max_tree_mtime(rows: list[dict]) -> float:
    values = [row.get("mtime") for row in rows if row.get("mtime") is not None]
    return max(values) if values else 0.0


def remove_file_with_retry(path: Path, attempts: int = 6, delay: float = 0.25) -> None:
    """Delete a file, tolerating Windows locks from handles awaiting garbage collection."""
    last_error = None
    for _ in range(attempts):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            gc.collect()
            time.sleep(delay)
    raise RuntimeError(
        f"Could not delete locked file '{path}'. Close any SQLite browser or other "
        f"program holding it open and try again. Last error: {last_error}"
    )


def get_folder_size_bytes(folder_path: Path, stop_event=None) -> int:
    total_size = 0
    try:
        for entry in os.scandir(folder_path):
            if stop_event is not None and stop_event.is_set():
                break
            try:
                if entry.is_file(follow_symlinks=False):
                    total_size += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total_size += get_folder_size_bytes(Path(entry.path), stop_event=stop_event)
            except OSError:
                continue
    except OSError:
        pass
    return total_size


def safe_read_text(path: Path, max_bytes: int = MAX_TEXT_FILE_SIZE_BYTES) -> tuple[str | None, str | None]:
    size = safe_stat_size(path)
    if size is None:
        return None, "stat_failed"
    if size > max_bytes:
        return None, "over_size_limit"
    if "".join(path.suffixes).lower() in FORCE_BINARY_EXTENSIONS_FOR_DUMP:
        return None, "forced_binary_extension"
    if is_binary(path):
        return None, "binary_detected"
    try:
        return path.read_text(encoding=TEXT_ENCODING, errors="ignore"), None
    except PermissionError:
        return None, "permission_denied"
    except Exception as exc:
        return None, f"read_failed: {exc}"


def safe_read_blob(path: Path) -> tuple[bytes | None, str | None]:
    try:
        return path.read_bytes(), None
    except PermissionError:
        return None, "permission_denied"
    except Exception as exc:
        return None, f"blob_read_failed: {exc}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
