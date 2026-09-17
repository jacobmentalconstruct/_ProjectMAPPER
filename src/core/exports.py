"""Headless exports services."""
import os
import sys
import platform
import sqlite3
import contextlib
import gc
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from .config import *
from .helpers import *
from .exclusions import ExclusionPolicy
from .tree import scan_project_tree
from .snapshots import write_text_file

def safe_export_name(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in ("-", "_", "."):
            allowed.append(char)
        else:
            allowed.append("-")
    return "".join(allowed).strip("-") or "export"


def is_vendor_export_excluded(path: Path) -> tuple[bool, str | None]:
    name = path.name
    if name in VENDOR_EXPORT_EXCLUDED_NAMES:
        return True, f"excluded_name:{name}"
    if any(name.startswith(prefix) for prefix in VENDOR_EXPORT_EXCLUDED_PREFIXES):
        return True, f"excluded_prefix:{name}"
    if any(name.endswith(suffix) for suffix in VENDOR_EXPORT_EXCLUDED_SUFFIXES):
        return True, f"excluded_suffix:{name}"
    return False, None


def copy_vendor_tree(source: Path, destination: Path, included: list[str], skipped: list[dict], stop_event=None):
    excluded, reason = is_vendor_export_excluded(source)
    if excluded:
        skipped.append({"path": source.name, "reason": reason})
        return

    if source.is_dir():
        ensure_dir(destination)
        for child in sorted(source.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if stop_event is not None and stop_event.is_set():
                return
            copy_vendor_tree(child, destination / child.name, included, skipped, stop_event=stop_event)
        return

    ensure_dir(destination.parent)
    shutil.copy2(source, destination)
    included.append(destination.as_posix())


def build_fresh_start_install_markdown(export_name: str) -> str:
    return "\n".join([
        "# ProjectMapper Blank-Slate Vendor Export",
        "",
        f"Package: `{export_name}`",
        f"Created: `{now_iso()}`",
        "",
        "This export is intended for clean external testing. It contains the installable ProjectMapper app files only.",
        "",
        "## What Is Included",
        "",
        "- App source under `src/`",
        "- Runtime scripts: `setup_env.bat` and `run.bat`",
        "- README, license, requirements, and app assets",
        "- A vendor export manifest",
        "",
        "## What Is Not Included",
        "",
        "- Git history or repository metadata",
        "- Local virtual environments",
        "- Python caches",
        "- Previous `_projectmapper` snapshot outputs",
        "- Prior SQLite databases, logs, or generated vendor exports",
        "- Local `.env*` files",
        "",
        "## Fresh Install Test",
        "",
        "1. Copy this folder into a blank test project or any external project folder.",
        "2. Run `setup_env.bat` from this folder.",
        "3. Run `run.bat`.",
        "4. In the app, choose the project root you want to test.",
        "5. Compile a snapshot. New records will be created only under the selected project's `_projectmapper` output folder.",
        "",
        "The app does not need prior ProjectMapper records to start.",
        "",
    ])


def create_vendor_export(source_root: Path | None = None, export_root: Path | None = None, make_zip: bool = True, stop_event=None, log_callback=None) -> dict:
    source_root = (source_root or SOURCE_ROOT).resolve()
    export_root = ensure_dir((export_root or source_root / VENDOR_EXPORT_ROOT_NAME).resolve())
    export_name = safe_export_name(f"ProjectMapper-v{APP_VERSION}-blank-slate-{now_stamp()}")
    export_dir = export_root / export_name
    ensure_dir(export_dir)

    def log(message: str):
        if log_callback:
            log_callback(message)

    included: list[str] = []
    skipped: list[dict] = []

    log(f"Creating blank-slate vendor export: {export_dir}")

    for file_name in VENDOR_EXPORT_INCLUDE_FILES:
        if stop_event is not None and stop_event.is_set():
            break
        source = source_root / file_name
        if not source.exists():
            skipped.append({"path": file_name, "reason": "missing_include_file"})
            continue
        copy_vendor_tree(source, export_dir / file_name, included, skipped, stop_event=stop_event)

    for dir_name in VENDOR_EXPORT_INCLUDE_DIRS:
        if stop_event is not None and stop_event.is_set():
            break
        source = source_root / dir_name
        if not source.exists():
            skipped.append({"path": dir_name, "reason": "missing_include_dir"})
            continue
        copy_vendor_tree(source, export_dir / dir_name, included, skipped, stop_event=stop_event)

    install_path = export_dir / "INSTALL_FRESH_START.md"
    write_text_file(install_path, build_fresh_start_install_markdown(export_name))
    included.append(install_path.as_posix())

    manifest_path = export_dir / "VENDOR_EXPORT_MANIFEST.json"
    relative_included = sorted(
        [rel_posix(Path(path), export_dir) for path in included]
        + [rel_posix(manifest_path, export_dir)]
    )
    manifest = {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "export_kind": "blank_slate_vendor_app",
        "export_name": export_name,
        "exported_at": now_iso(),
        "included_paths": relative_included,
        "skipped": skipped,
        "blank_slate_guarantees": [
            "No git history or repository metadata is copied.",
            "No virtual environment is copied.",
            "No Python cache files are copied.",
            "No prior _projectmapper snapshot outputs are copied.",
            "No SQLite snapshot/history databases are copied.",
            "No local .env files are copied.",
        ],
    }
    write_text_file(manifest_path, json.dumps(manifest, indent=2))

    zip_path = None
    if make_zip and (stop_event is None or not stop_event.is_set()):
        zip_base = export_root / export_name
        zip_path = Path(shutil.make_archive(str(zip_base), "zip", root_dir=export_root, base_dir=export_name))
        log(f"Created vendor zip: {zip_path}")

    return {
        "export_dir": export_dir,
        "zip_path": zip_path,
        "included_count": len(relative_included),
        "skipped_count": len(skipped),
    }
