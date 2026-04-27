# ==============================================================================
# ProjectMapper Snapshot Compiler
# Single-file tagged monolith scaffold
# ==============================================================================

# === [SECTION: IMPORTS] BEGIN ===
import sys
import os
import platform
import subprocess
import threading
import queue
import traceback
import fnmatch
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import tkinter.font as tkFont
# === [SECTION: IMPORTS] END ===


# === [SECTION: APP_METADATA] BEGIN ===
APP_NAME = "ProjectMapper Snapshot Compiler"
APP_VERSION = "0.3.0-snapshot-compiler"
SNAPSHOT_SCHEMA_VERSION = "0.1"
SNAPSHOT_COMPILER_ID = "projectmapper.snapshot_compiler"
# === [SECTION: APP_METADATA] END ===


# === [SECTION: CONSTANTS] BEGIN ===
APP_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT_DIR = APP_DIR
OUTPUT_ROOT_NAME = "_projectmapper"
MAX_TEXT_FILE_SIZE_BYTES = 1_000_000
TEXT_ENCODING = "utf-8"

S_CHECKED = "checked"
S_UNCHECKED = "unchecked"

SNAPSHOT_DB_SUFFIX = "snapshot.sqlite3"
TREE_MD_SUFFIX = "project_tree.md"
FILEDUMP_MD_SUFFIX = "project_filedump.md"
MANIFEST_MD_SUFFIX = "snapshot_manifest.md"
COMBINED_MD_SUFFIX = "project_tree_and_filedump.md"

EXCLUDED_FOLDERS = {
    "node_modules", ".git", "__pycache__", ".venv", ".mypy_cache",
    "_logs", "_projectmapper", "dist", "build", ".vscode", ".idea",
    "target", "out", "bin", "obj", "Debug", "Release", "logs", "venv"
}

PREDEFINED_EXCLUDED_FILENAMES = {
    "package-lock.json", "yarn.lock", ".DS_Store", "Thumbs.db",
    "*.pyc", "*.pyo", "*.swp", "*.swo"
}

FORCE_BINARY_EXTENSIONS_FOR_DUMP = {
    ".tar.gz", ".gz", ".zip", ".rar", ".7z", ".bz2", ".xz", ".tgz",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff",
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a",
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods",
    ".exe", ".dll", ".so", ".o", ".a", ".lib", ".app", ".dmg", ".deb", ".rpm",
    ".db", ".sqlite", ".sqlite3", ".db3", ".mdb", ".accdb", ".dat", ".idx", ".pickle", ".joblib",
    ".pyc", ".pyo", ".class", ".jar", ".wasm",
    ".ttf", ".otf", ".woff", ".woff2",
    ".iso", ".img", ".bin", ".bak", ".data", ".asset", ".pak"
}
# === [SECTION: CONSTANTS] END ===


# === [SECTION: THEME] BEGIN ===
THEME = {
    "app_bg": "#161A1F",
    "panel_bg": "#1E252D",
    "panel_alt_bg": "#273241",
    "field_bg": "#263140",
    "field_bg_alt": "#2D3948",
    "tree_bg": "#1A212B",
    "log_bg": "#10161E",
    "status_bg": "#0D1117",
    "status_text": "#89D6A0",
    "text": "#E7EDF4",
    "muted_text": "#97A4B3",
    "field_text": "#D6E2EE",
    "heading_bg": "#2A3441",
    "heading_text": "#F3F6F9",
    "selection": "#3B7E8D",
    "accent": "#C56F3D",
    "accent_hover": "#D78251",
    "secondary": "#2E7081",
    "secondary_hover": "#3A8EA2",
    "success": "#2F8E6A",
    "success_hover": "#3AA27C",
    "danger": "#B75A4D",
    "danger_hover": "#CB6B5E",
    "checkbox_checked": "#C56F3D",
    "checkbox_border": "#728195",
    "log_text": "#E1E7EE",
    "log_accent": "#89D6A0",
}
# === [SECTION: THEME] END ===


# === [SECTION: PYTHONW_SAFETY] BEGIN ===
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
# === [SECTION: PYTHONW_SAFETY] END ===


# === [SECTION: PURE_HELPERS] BEGIN ===
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
# === [SECTION: PURE_HELPERS] END ===


# === [SECTION: SNAPSHOT_DATA_HELPERS] BEGIN ===
def snapshot_output_filename(root: Path, suffix: str) -> str:
    return f"{root.name}_{suffix}"


def load_snapshot_output(snapshot_path: Path, output_name: str) -> str:
    if not snapshot_path or not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot DB not found: {snapshot_path}")
    with sqlite3.connect(snapshot_path) as conn:
        row = conn.execute(
            "SELECT content FROM snapshot_outputs WHERE name = ?",
            (output_name,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Snapshot output not found: {output_name}")
    return row[0]


def write_text_file(path: Path, content: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(content, encoding=TEXT_ENCODING, errors="ignore")
    return path


def combine_tree_and_filedump_markdown(tree_markdown: str, filedump_markdown: str) -> str:
    return "\n".join([
        "# Project Tree + Filedump",
        "",
        "This combined export includes the project tree first, followed by the captured file dump.",
        "",
        "---",
        "",
        tree_markdown.rstrip(),
        "",
        "---",
        "",
        filedump_markdown.rstrip(),
        "",
    ])
# === [SECTION: SNAPSHOT_DATA_HELPERS] END ===


# === [SECTION: EXCLUSION_POLICY] BEGIN ===
class ExclusionPolicy:
    def __init__(self):
        self.respect_exclusions = True
        self.dynamic_patterns = set()
        self.gitignore_dirnames = set()
        self.gitignore_file_patterns = set()
        self.gitignore_path_patterns = set()

    def load_gitignore(self, root: Path):
        self.gitignore_dirnames.clear()
        self.gitignore_file_patterns.clear()
        self.gitignore_path_patterns.clear()

        gi = root / ".gitignore"
        if not gi.exists():
            return

        try:
            lines = gi.read_text(encoding=TEXT_ENCODING, errors="ignore").splitlines()
        except Exception:
            return

        for raw in lines:
            pattern = raw.strip()
            if not pattern or pattern.startswith("#") or pattern.startswith("!"):
                continue
            pattern = pattern.replace("\\", "/")
            if pattern.endswith("/"):
                value = pattern[:-1].strip("/")
                if value:
                    self.gitignore_dirnames.add(value)
            elif "/" in pattern:
                self.gitignore_path_patterns.add(pattern.strip("/"))
            else:
                self.gitignore_file_patterns.add(pattern)

    def collect_rules(self) -> list[dict]:
        rules = []
        rules.append({"rule_type": "toggle", "pattern": "respect_exclusions", "source": "ui", "active": int(self.respect_exclusions)})
        for pattern in sorted(EXCLUDED_FOLDERS):
            rules.append({"rule_type": "directory", "pattern": pattern, "source": "hardcoded_folder", "active": 1})
        for pattern in sorted(PREDEFINED_EXCLUDED_FILENAMES):
            rules.append({"rule_type": "filename", "pattern": pattern, "source": "predefined_filename", "active": 1})
        for pattern in sorted(self.dynamic_patterns):
            rules.append({"rule_type": "filename", "pattern": pattern, "source": "dynamic_user_pattern", "active": 1})
        for pattern in sorted(self.gitignore_dirnames):
            rules.append({"rule_type": "directory", "pattern": pattern, "source": "gitignore_dirname", "active": 1})
        for pattern in sorted(self.gitignore_file_patterns):
            rules.append({"rule_type": "filename", "pattern": pattern, "source": "gitignore_file_pattern", "active": 1})
        for pattern in sorted(self.gitignore_path_patterns):
            rules.append({"rule_type": "path", "pattern": pattern, "source": "gitignore_path_pattern", "active": 1})
        return rules

    def should_exclude_path(self, path: Path, root: Path) -> tuple[bool, str | None]:
        if not self.respect_exclusions:
            return False, None

        try:
            p = path.resolve()
            r = root.resolve()
        except Exception:
            return False, None

        if p != r and not is_path_inside(p, r):
            return False, None

        name = p.name
        rel = rel_posix(p, r)

        if p.is_dir():
            if name in EXCLUDED_FOLDERS:
                return True, "hardcoded_folder"
            if name in self.gitignore_dirnames:
                return True, "gitignore_dirname"
            for pattern in self.gitignore_path_patterns:
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel + "/", pattern) or fnmatch.fnmatch(rel + "/", pattern + "/"):
                    return True, "gitignore_path_pattern"
            return False, None

        patterns = set(PREDEFINED_EXCLUDED_FILENAMES).union(self.dynamic_patterns)
        for pattern in patterns:
            if fnmatch.fnmatch(name, pattern):
                return True, "filename_pattern"
        for pattern in self.gitignore_file_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True, "gitignore_file_pattern"
        for pattern in self.gitignore_path_patterns:
            if fnmatch.fnmatch(rel, pattern):
                return True, "gitignore_path_pattern"
        return False, None
# === [SECTION: EXCLUSION_POLICY] END ===


# === [SECTION: FILESYSTEM_SCANNER] BEGIN ===
def scan_project_tree(root: Path, policy: ExclusionPolicy, stop_event=None) -> tuple[list[dict], list[dict]]:
    root = root.resolve()
    rows = []
    skipped = []

    def add_row(path: Path, parent: Path | None, depth: int):
        size_bytes = get_folder_size_bytes(path, stop_event=stop_event) if path.is_dir() else safe_stat_size(path)
        rows.append({
            "path": path.resolve(),
            "parent": parent.resolve() if parent else None,
            "relative_path": "." if path == root else rel_posix(path, root),
            "parent_relative_path": None if parent is None else ("." if parent == root else rel_posix(parent, root)),
            "name": path.name,
            "entry_type": "dir" if path.is_dir() else "file",
            "depth": depth,
            "size_bytes": size_bytes,
        })

    def recurse(current: Path, depth: int):
        if stop_event is not None and stop_event.is_set():
            return
        try:
            items = sorted(list(current.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            skipped.append({"relative_path": rel_posix(current, root), "skip_reason": "permission_denied", "detail": "Cannot list directory"})
            return
        except Exception as exc:
            skipped.append({"relative_path": rel_posix(current, root), "skip_reason": "list_failed", "detail": str(exc)})
            return

        for item in items:
            if stop_event is not None and stop_event.is_set():
                return
            excluded, reason = policy.should_exclude_path(item, root)
            if excluded:
                skipped.append({"relative_path": rel_posix(item, root), "skip_reason": "excluded_by_rule", "detail": reason or "excluded"})
                continue
            add_row(item, current, depth + 1)
            if item.is_dir():
                recurse(item, depth + 1)

    add_row(root, None, 0)
    recurse(root, 0)
    return rows, skipped
# === [SECTION: FILESYSTEM_SCANNER] END ===


# === [SECTION: SNAPSHOT_SCHEMA] BEGIN ===
def create_snapshot_schema(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_manifest (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            manifest_version TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            contents_markdown TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_tree (
            tree_order INTEGER NOT NULL,
            relative_path TEXT PRIMARY KEY,
            parent_relative_path TEXT,
            name TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            depth INTEGER NOT NULL,
            size_bytes INTEGER,
            is_selected INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_files (
            dump_order INTEGER NOT NULL,
            relative_path TEXT PRIMARY KEY,
            parent_relative_path TEXT,
            size_bytes INTEGER NOT NULL,
            content TEXT NOT NULL,
            captured_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_blobs (
            blob_order INTEGER NOT NULL,
            relative_path TEXT PRIMARY KEY,
            parent_relative_path TEXT,
            size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            blob_content BLOB NOT NULL,
            captured_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_exclusion_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL,
            pattern TEXT NOT NULL,
            source TEXT NOT NULL,
            active INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_skipped_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            relative_path TEXT NOT NULL,
            skip_reason TEXT NOT NULL,
            detail TEXT,
            size_bytes INTEGER,
            entry_type TEXT,
            source TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_mapper_state (
            relative_path TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            entry_type TEXT,
            is_visible INTEGER NOT NULL,
            source TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_environment (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_outputs (
            name TEXT PRIMARY KEY,
            output_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            external_path TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            relative_path TEXT,
            error TEXT NOT NULL,
            context TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_tree_order ON project_tree(tree_order)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_tree_parent ON project_tree(parent_relative_path)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_files_order ON project_files(dump_order)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_blobs_order ON project_blobs(blob_order)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skipped_reason ON snapshot_skipped_paths(skip_reason)")
# === [SECTION: SNAPSHOT_SCHEMA] END ===


# === [SECTION: SNAPSHOT_WRITERS] BEGIN ===
def upsert_snapshot_metadata(conn: sqlite3.Connection, key: str, value):
    conn.execute(
        "INSERT OR REPLACE INTO snapshot_metadata (key, value) VALUES (?, ?)",
        (key, "" if value is None else str(value)),
    )


def insert_project_tree_row(conn: sqlite3.Connection, tree_order: int, row: dict, is_selected: bool):
    conn.execute(
        """
        INSERT OR REPLACE INTO project_tree (
            tree_order, relative_path, parent_relative_path, name,
            entry_type, depth, size_bytes, is_selected
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tree_order,
            row["relative_path"],
            row.get("parent_relative_path"),
            row["name"],
            row["entry_type"],
            row["depth"],
            row.get("size_bytes"),
            int(is_selected),
        ),
    )


def insert_project_file(conn: sqlite3.Connection, dump_order: int, relative_path: str, parent_relative_path: str | None, size_bytes: int, content: str):
    conn.execute(
        """
        INSERT OR REPLACE INTO project_files (
            dump_order, relative_path, parent_relative_path, size_bytes, content, captured_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (dump_order, relative_path, parent_relative_path, size_bytes, content, now_iso()),
    )


def insert_project_blob(conn: sqlite3.Connection, blob_order: int, relative_path: str, parent_relative_path: str | None, size_bytes: int, sha256: str, blob_content: bytes):
    conn.execute(
        """
        INSERT OR REPLACE INTO project_blobs (
            blob_order, relative_path, parent_relative_path, size_bytes, sha256, blob_content, captured_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (blob_order, relative_path, parent_relative_path, size_bytes, sha256, sqlite3.Binary(blob_content), now_iso()),
    )


def insert_exclusion_rules(conn: sqlite3.Connection, rules: list[dict]):
    conn.executemany(
        """
        INSERT INTO snapshot_exclusion_rules (rule_type, pattern, source, active)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                rule.get("rule_type", "unknown"),
                rule.get("pattern", ""),
                rule.get("source", "unknown"),
                int(rule.get("active", 1)),
            )
            for rule in rules
        ],
    )


def insert_skipped_path(conn: sqlite3.Connection, relative_path: str, skip_reason: str, detail: str | None = None, size_bytes: int | None = None, entry_type: str | None = None, source: str = "snapshot_compiler"):
    conn.execute(
        """
        INSERT INTO snapshot_skipped_paths (
            relative_path, skip_reason, detail, size_bytes, entry_type, source
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (relative_path, skip_reason, detail, size_bytes, entry_type, source),
    )


def insert_mapper_state(conn: sqlite3.Connection, relative_path: str, state: str, entry_type: str | None, is_visible: bool, source: str = "tree_checkbox"):
    conn.execute(
        """
        INSERT OR REPLACE INTO snapshot_mapper_state (
            relative_path, state, entry_type, is_visible, source
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (relative_path, state, entry_type, int(is_visible), source),
    )


def insert_environment_hints(conn: sqlite3.Connection, hints: dict):
    conn.executemany(
        "INSERT OR REPLACE INTO snapshot_environment (key, value) VALUES (?, ?)",
        [(key, "" if value is None else str(value)) for key, value in sorted(hints.items())],
    )


def insert_snapshot_output(conn: sqlite3.Connection, name: str, output_type: str, content: str, external_path: str | None = None):
    conn.execute(
        """
        INSERT OR REPLACE INTO snapshot_outputs (
            name, output_type, content, created_at, external_path
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (name, output_type, content, now_iso(), external_path),
    )


def insert_snapshot_error(conn: sqlite3.Connection, error: str, relative_path: str | None = None, context: str | None = None):
    conn.execute(
        """
        INSERT INTO snapshot_errors (relative_path, error, context, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (relative_path, error, context, now_iso()),
    )
# === [SECTION: SNAPSHOT_WRITERS] END ===


# === [SECTION: ENVIRONMENT_HINTS] BEGIN ===
def detect_environment_hints(root: Path) -> dict:
    root = root.resolve()
    hints = {
        "platform": platform.platform(),
        "python_version": sys.version.replace("\n", " "),
        "snapshot_compiler_id": SNAPSHOT_COMPILER_ID,
        "app_version": APP_VERSION,
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source_root_name": root.name,
        "source_root_absolute_path": str(root),
        "has_requirements_txt": int((root / "requirements.txt").exists()),
        "has_pyproject_toml": int((root / "pyproject.toml").exists()),
        "has_package_json": int((root / "package.json").exists()),
        "has_environment_yml": int((root / "environment.yml").exists()),
        "has_poetry_lock": int((root / "poetry.lock").exists()),
        "has_uv_lock": int((root / "uv.lock").exists()),
        "has_pipfile": int((root / "Pipfile").exists()),
        "has_dot_venv": int((root / ".venv").is_dir()),
        "has_venv": int((root / "venv").is_dir()),
    }

    pyvenv_cfg = root / ".venv" / "pyvenv.cfg"
    if pyvenv_cfg.exists() and pyvenv_cfg.is_file():
        content, error = safe_read_text(pyvenv_cfg, max_bytes=20_000)
        if content is not None:
            for line in content.splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip().lower().replace(" ", "_")
                value = value.strip()
                if key in {"home", "implementation", "version", "include-system-site-packages"}:
                    hints[f"dot_venv_{key}"] = value
        elif error:
            hints["dot_venv_pyvenv_cfg_error"] = error

    return hints
# === [SECTION: ENVIRONMENT_HINTS] END ===


# === [SECTION: MARKDOWN_PROJECTIONS] BEGIN ===
def markdown_language_for_path(path_text: str) -> str:
    suffix = Path(path_text).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".json": "json",
        ".md": "markdown",
        ".txt": "text",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".xml": "xml",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
        ".ini": "ini",
        ".bat": "bat",
        ".ps1": "powershell",
        ".sh": "bash",
        ".sql": "sql",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".java": "java",
        ".rs": "rust",
        ".go": "go",
        ".rb": "ruby",
        ".php": "php",
    }.get(suffix, "text")


def build_project_tree_markdown(root: Path, snapshot_name: str, created_at: str, tree_rows: list[dict], folder_item_states: dict) -> str:
    lines = [
        "# Project Tree",
        "",
        "This standalone tree is intended as a lightweight project surface map. It can be shared without the full filedump so an agent can see the project shape, identify missing/unincluded files, and request specific follow-up uploads when needed.",
        "",
        "The SQLite snapshot remains the authoritative truth source for the manifest, selected file contents, skipped paths, exclusion rules, mapper state, and environment hints.",
        "",
        f"- Source root: `{root}`",
        f"- Snapshot: `{snapshot_name}`",
        f"- Generated: `{created_at}`",
        "",
        "```text",
    ]

    for row in tree_rows:
        depth = int(row.get("depth", 0))
        indent = "    " * depth
        icon = "📁" if row.get("entry_type") == "dir" else "📄"
        state = folder_item_states.get(str(row.get("path")), S_UNCHECKED)
        checkbox = "[x]" if state == S_CHECKED else "[ ]"
        suffix = "/" if row.get("entry_type") == "dir" else ""
        name = row.get("name", "")
        if row.get("relative_path") == ".":
            name = f"{name}/"
            suffix = ""
        lines.append(f"{indent}{checkbox} {icon} {name}{suffix}")

    lines.extend(["```", ""])
    return "\n".join(lines)


def build_filedump_markdown(root: Path, snapshot_name: str, created_at: str, captured_files: list[dict]) -> str:
    lines = [
        "# Project Filedump",
        "",
        f"- Source root: `{root}`",
        f"- Snapshot: `{snapshot_name}`",
        f"- Generated: `{created_at}`",
        f"- Captured files: `{len(captured_files)}`",
        "",
    ]

    for item in captured_files:
        rel = item.get("relative_path", "")
        content = item.get("content", "")
        language = markdown_language_for_path(rel)
        lines.extend([
            "---",
            "",
            f"## FILE: `{rel}`",
            "",
            f"```{language}",
            content.rstrip(),
            "```",
            "",
        ])

    return "\n".join(lines)
# === [SECTION: MARKDOWN_PROJECTIONS] END ===


# === [SECTION: SNAPSHOT_COMPILER] BEGIN ===
def compile_snapshot(
    root: Path,
    output_dir: Path,
    tree_rows: list[dict],
    folder_item_states: dict,
    policy: ExclusionPolicy,
    scan_skipped_paths: list[dict],
    include_binary_blobs: bool = False,
    stop_event=None,
    log_callback=None,
) -> Path:
    root = root.resolve()
    output_dir = ensure_dir(output_dir)
    snapshot_path = output_dir / f"{root.name}_{SNAPSHOT_DB_SUFFIX}"

    if snapshot_path.exists():
        snapshot_path.unlink()

    created_at = now_iso()
    visible_rows = list(tree_rows)
    skipped_paths = list(scan_skipped_paths)

    if not visible_rows:
        if log_callback:
            log_callback("No cached tree rows found; scanning before snapshot compile.")
        policy.load_gitignore(root)
        visible_rows, skipped_paths = scan_project_tree(root, policy, stop_event=stop_event)

    tree_entry_count = 0
    mapper_state_count = 0
    captured_file_count = 0
    captured_blob_count = 0
    skipped_path_count = 0
    error_count = 0
    cancelled = False
    captured_files_for_projection = []

    def emit(message: str, level: str = "INFO"):
        if log_callback:
            log_callback(message, level)

    with sqlite3.connect(snapshot_path) as conn:
        create_snapshot_schema(conn)

        base_metadata = {
            "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_compiler_id": SNAPSHOT_COMPILER_ID,
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "source_root_name": root.name,
            "source_root_absolute_path": str(root),
            "compiled_at": created_at,
            "respect_exclusions": int(policy.respect_exclusions),
            "include_binary_blobs": int(include_binary_blobs),
            "max_text_file_size_bytes": MAX_TEXT_FILE_SIZE_BYTES,
            "text_encoding": TEXT_ENCODING,
            "snapshot_filename": snapshot_path.name,
        }
        for key, value in base_metadata.items():
            upsert_snapshot_metadata(conn, key, value)

        insert_environment_hints(conn, detect_environment_hints(root))
        insert_exclusion_rules(conn, policy.collect_rules())

        for tree_order, row in enumerate(visible_rows):
            if stop_event is not None and stop_event.is_set():
                cancelled = True
                break
            abs_key = str(row["path"])
            state = folder_item_states.get(abs_key, S_UNCHECKED)
            is_selected = state == S_CHECKED
            insert_project_tree_row(conn, tree_order, row, is_selected)
            insert_mapper_state(conn, row["relative_path"], state, row["entry_type"], True)
            tree_entry_count += 1
            mapper_state_count += 1

        for skipped in skipped_paths:
            insert_skipped_path(
                conn,
                skipped.get("relative_path", ""),
                skipped.get("skip_reason", "unknown"),
                skipped.get("detail"),
                skipped.get("size_bytes"),
                skipped.get("entry_type"),
                source="scanner",
            )
            skipped_path_count += 1

        for row in visible_rows:
            if stop_event is not None and stop_event.is_set():
                cancelled = True
                break

            if row["entry_type"] != "file":
                continue

            abs_key = str(row["path"])
            state = folder_item_states.get(abs_key, S_UNCHECKED)
            if state != S_CHECKED:
                insert_skipped_path(
                    conn,
                    row["relative_path"],
                    "unchecked_by_user",
                    "Visible file was not selected in mapper tree.",
                    row.get("size_bytes"),
                    row.get("entry_type"),
                    source="mapper_state",
                )
                skipped_path_count += 1
                continue

            content, read_error = safe_read_text(row["path"], max_bytes=MAX_TEXT_FILE_SIZE_BYTES)
            if read_error:
                skip_reason = read_error.split(":", 1)[0]
                blob_preserved = False
                if include_binary_blobs and skip_reason in {"forced_binary_extension", "binary_detected"}:
                    blob_content, blob_error = safe_read_blob(row["path"])
                    if blob_content is not None:
                        insert_project_blob(
                            conn,
                            captured_blob_count,
                            row["relative_path"],
                            row.get("parent_relative_path"),
                            int(row.get("size_bytes") or len(blob_content)),
                            sha256_bytes(blob_content),
                            blob_content,
                        )
                        captured_blob_count += 1
                        blob_preserved = True
                    elif blob_error:
                        insert_snapshot_error(conn, blob_error, row["relative_path"], "insert_project_blob")
                        error_count += 1

                detail = read_error
                if blob_preserved:
                    detail = f"{read_error}; binary bytes preserved in project_blobs"

                insert_skipped_path(
                    conn,
                    row["relative_path"],
                    skip_reason,
                    detail,
                    row.get("size_bytes"),
                    row.get("entry_type"),
                    source="file_capture",
                )
                skipped_path_count += 1
                continue

            try:
                insert_project_file(
                    conn,
                    captured_file_count,
                    row["relative_path"],
                    row.get("parent_relative_path"),
                    int(row.get("size_bytes") or 0),
                    content or "",
                )
                captured_files_for_projection.append({
                    "relative_path": row["relative_path"],
                    "content": content or "",
                    "size_bytes": int(row.get("size_bytes") or 0),
                })
                captured_file_count += 1
                if captured_file_count % 10 == 0:
                    emit(f"Captured {captured_file_count} text files...")
            except Exception as exc:
                insert_snapshot_error(conn, str(exc), row["relative_path"], "insert_project_file")
                error_count += 1

        upsert_snapshot_metadata(conn, "tree_entry_count", tree_entry_count)
        upsert_snapshot_metadata(conn, "mapper_state_count", mapper_state_count)
        upsert_snapshot_metadata(conn, "captured_file_count", captured_file_count)
        upsert_snapshot_metadata(conn, "captured_blob_count", captured_blob_count)
        upsert_snapshot_metadata(conn, "skipped_path_count", skipped_path_count)
        upsert_snapshot_metadata(conn, "error_count", error_count)
        upsert_snapshot_metadata(conn, "was_cancelled", int(cancelled))
        upsert_snapshot_metadata(conn, "snapshot_completion_state", "partial" if cancelled else "complete")

        project_tree_markdown = build_project_tree_markdown(
            root=root,
            snapshot_name=snapshot_path.name,
            created_at=created_at,
            tree_rows=visible_rows,
            folder_item_states=folder_item_states,
        )
        project_filedump_markdown = build_filedump_markdown(
            root=root,
            snapshot_name=snapshot_path.name,
            created_at=created_at,
            captured_files=captured_files_for_projection,
        )
        insert_snapshot_output(conn, "project_tree_markdown", "markdown", project_tree_markdown)
        insert_snapshot_output(conn, "project_filedump_markdown", "markdown", project_filedump_markdown)
        upsert_snapshot_metadata(conn, "project_tree_markdown_generated", 1)
        upsert_snapshot_metadata(conn, "project_filedump_markdown_generated", 1)

        manifest_summary = (
            "ProjectMapper SQLite snapshot containing project structure, selected text file contents, "
            "mapper state, exclusion rules, skipped paths, environment hints, and snapshot metadata."
        )
        manifest_body = "\n".join([
            "# ProjectMapper Snapshot Manifest",
            "",
            "## Purpose",
            manifest_summary,
            "",
            "## Snapshot",
            f"- Source root: `{root}`",
            f"- Snapshot file: `{snapshot_path.name}`",
            f"- Compiled at: `{created_at}`",
            f"- Tree entries: `{tree_entry_count}`",
            f"- Captured text files: `{captured_file_count}`",
            f"- Captured binary blobs: `{captured_blob_count}`",
            f"- Skipped paths: `{skipped_path_count}`",
            f"- Errors: `{error_count}`",
            f"- Cancelled: `{int(cancelled)}`",
            f"- Completion state: `{'partial' if cancelled else 'complete'}`",
            "",
            "## Core Tables",
            "- `snapshot_metadata`: key/value facts about this snapshot.",
            "- `snapshot_manifest`: this onboarding manifest.",
            "- `project_tree`: visible project structure captured in traversal order.",
            "- `project_files`: selected text-readable file contents.",
            "- `project_blobs`: optional selected binary file bytes for backup/rehydration mode.",
            "- `snapshot_exclusion_rules`: active exclusion policy at compile time.",
            "- `snapshot_skipped_paths`: files or folders omitted and why.",
            "- `snapshot_mapper_state`: checkbox state from the mapper tree.",
            "- `snapshot_environment`: local project environment hints.",
            "- `snapshot_outputs`: generated projection artifacts, including tree and filedump markdown.",
            "- `snapshot_errors`: non-fatal errors encountered during compilation.",
            "",
            "## Generated Outputs",
            "- `snapshot_manifest_markdown`: this manifest as DB-embedded markdown, not a required standalone export.",
            "- `project_tree_markdown`: lightweight project surface map export.",
            "- `project_filedump_markdown`: captured text files as markdown.",
            "- Combined tree + filedump markdown can be exported on demand from the UI.",
            "",
            "## Quick Start Queries",
            "```sql",
            "SELECT * FROM snapshot_manifest;",
            "SELECT key, value FROM snapshot_metadata ORDER BY key;",
            "SELECT relative_path, entry_type, is_selected FROM project_tree ORDER BY tree_order;",
            "SELECT relative_path, substr(content, 1, 400) AS preview FROM project_files ORDER BY dump_order LIMIT 20;",
            "SELECT relative_path, size_bytes, sha256 FROM project_blobs ORDER BY blob_order;",
            "SELECT * FROM snapshot_exclusion_rules ORDER BY source, pattern;",
            "SELECT * FROM snapshot_skipped_paths ORDER BY skip_reason, relative_path;",
            "SELECT * FROM snapshot_environment ORDER BY key;",
            "SELECT name, output_type, length(content) AS chars FROM snapshot_outputs ORDER BY name;",
            "SELECT content FROM snapshot_outputs WHERE name = 'project_tree_markdown';",
            "```",
        ])
        conn.execute(
            """
            INSERT OR REPLACE INTO snapshot_manifest (
                id, manifest_version, title, summary, contents_markdown, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                SNAPSHOT_SCHEMA_VERSION,
                "ProjectMapper Snapshot Manifest",
                manifest_summary,
                manifest_body,
                created_at,
            ),
        )
        insert_snapshot_output(conn, "snapshot_manifest_markdown", "markdown", manifest_body)
        conn.commit()

    emit(
        f"Snapshot compiled: {snapshot_path.name} ({tree_entry_count} tree entries, {captured_file_count} text files, {captured_blob_count} blobs, {skipped_path_count} skipped)"
    )
    return snapshot_path
# === [SECTION: SNAPSHOT_COMPILER] END ===


# === [SECTION: PROGRESS_POPUP] BEGIN ===
class ProgressPopup:
    def __init__(self, parent, title="Processing", on_cancel=None):
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.geometry("560x320")
        self.top.configure(bg=THEME["panel_bg"])
        self.top.transient(parent)
        self.top.grab_set()
        self.top.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        self.on_cancel = on_cancel
        self.is_cancelled = False

        tk.Label(
            self.top,
            text=f"{title}...",
            fg=THEME["text"],
            bg=THEME["panel_bg"],
            font=("Arial", 12, "bold"),
        ).pack(pady=10)

        self.log_display = scrolledtext.ScrolledText(
            self.top,
            height=10,
            bg=THEME["log_bg"],
            fg=THEME["log_accent"],
            insertbackground=THEME["log_text"],
            font=("Consolas", 9),
        )
        self.log_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.cancel_btn = tk.Button(
            self.top,
            text="CANCEL OPERATION",
            bg=THEME["danger"],
            fg=THEME["text"],
            activebackground=THEME["danger_hover"],
            activeforeground=THEME["text"],
            font=("Arial", 10, "bold"),
            command=self.trigger_cancel,
        )
        self.cancel_btn.pack(pady=10)

    def update_text(self, text):
        self.log_display.insert(tk.END, text + "\n")
        self.log_display.see(tk.END)

    def trigger_cancel(self):
        self.is_cancelled = True
        self.update_text("!!! CANCELLATION REQUESTED - STOPPING !!!")
        self.cancel_btn.config(state=tk.DISABLED, text="Stopping...")
        if self.on_cancel:
            self.on_cancel()

    def _on_close_attempt(self):
        if not self.is_cancelled:
            self.trigger_cancel()

    def close(self):
        try:
            self.top.destroy()
        except tk.TclError:
            pass
# === [SECTION: PROGRESS_POPUP] END ===


# === [SECTION: TK_APP_INIT] BEGIN ===
class ProjectMapperApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.gui_queue = queue.Queue()
        self.running_tasks = set()
        self.stop_event = threading.Event()
        self.widgets = {}
        self.current_progress_popup = None
        self.selected_root = DEFAULT_ROOT_DIR
        self.latest_snapshot_path = None
        self.state_lock = threading.RLock()
        self.folder_item_states = {}
        self.tree_rows = []
        self.scan_skipped_paths = []
        self.exclusion_policy = ExclusionPolicy()
        self.icon_imgs = {}
        self._create_tree_icons()

        self._setup_styles()
        self._setup_ui()
        self.process_gui_queue()
        self._activity_blinker()
        self.log_message("Snapshot Compiler loaded. Choose a project root, curate the tree, then compile a SQLite snapshot.")
        self.root.after(250, self.request_rescan_tree_silent)

    def _create_tree_icons(self):
        img_unchecked = tk.PhotoImage(width=14, height=14)
        img_unchecked.put((THEME["checkbox_border"],), to=(0, 0, 14, 1))
        img_unchecked.put((THEME["checkbox_border"],), to=(0, 13, 14, 14))
        img_unchecked.put((THEME["checkbox_border"],), to=(0, 0, 1, 14))
        img_unchecked.put((THEME["checkbox_border"],), to=(13, 0, 14, 14))
        self.icon_imgs[S_UNCHECKED] = img_unchecked

        img_checked = tk.PhotoImage(width=14, height=14)
        img_checked.put((THEME["checkbox_checked"],), to=(0, 0, 14, 14))
        img_checked.put(("#FFFFFF",), to=(3, 7, 6, 10))
        img_checked.put(("#FFFFFF",), to=(6, 5, 11, 8))
        self.icon_imgs[S_CHECKED] = img_checked
        # === [SECTION: TK_APP_INIT] END ===


# === [SECTION: TK_STYLES] BEGIN ===
    def _setup_styles(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self.default_ui_font = "Arial"
        try:
            if "DejaVu Sans" in tkFont.families():
                self.default_ui_font = "DejaVu Sans"
        except tk.TclError:
            pass

        style.configure(
            "Treeview",
            background=THEME["tree_bg"],
            foreground=THEME["text"],
            fieldbackground=THEME["tree_bg"],
            borderwidth=0,
            font=(self.default_ui_font, 10),
            rowheight=24,
        )
        style.configure(
            "Treeview.Heading",
            background=THEME["heading_bg"],
            foreground=THEME["heading_text"],
            relief=tk.FLAT,
        )
# === [SECTION: TK_STYLES] END ===


# === [SECTION: TK_UI_LAYOUT] BEGIN ===
    def _setup_ui(self):
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.configure(bg=THEME["app_bg"])
        self.root.geometry("1200x850")

        top_frame = tk.Frame(self.root, bg=THEME["panel_bg"])
        top_frame.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(top_frame, text="Project Root:", bg=THEME["panel_bg"], fg=THEME["text"]).pack(side=tk.LEFT)
        self.widgets["selected_root_var"] = tk.StringVar(value=str(DEFAULT_ROOT_DIR))
        self.widgets["project_path_entry"] = tk.Entry(
            top_frame,
            textvariable=self.widgets["selected_root_var"],
            bg=THEME["field_bg"],
            fg=THEME["field_text"],
            insertbackground=THEME["field_text"],
            relief=tk.FLAT,
        )
        self.widgets["project_path_entry"].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.widgets["project_path_entry"].bind("<Return>", lambda _event: self.choose_root_from_entry())

        self._make_button(top_frame, "Choose...", self.choose_root_dialog, THEME["secondary"], THEME["secondary_hover"]).pack(side=tk.RIGHT)
        self._make_button(top_frame, "↑", self.navigate_to_parent, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.RIGHT, padx=5)

        paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree_frame = tk.Frame(paned, bg=THEME["panel_bg"])
        self.widgets["folder_tree"] = ttk.Treeview(
            tree_frame,
            show="tree headings",
            columns=("nav_up", "nav_down", "size"),
            selectmode="browse",
        )
        self.widgets["folder_tree"].heading("#0", text="Explorer")
        self.widgets["folder_tree"].heading("nav_up", text="↑")
        self.widgets["folder_tree"].heading("nav_down", text="↓")
        self.widgets["folder_tree"].heading("size", text="Size")
        self.widgets["folder_tree"].column("#0", width=760)
        self.widgets["folder_tree"].column("nav_up", width=34, anchor="center", stretch=False)
        self.widgets["folder_tree"].column("nav_down", width=34, anchor="center", stretch=False)
        self.widgets["folder_tree"].column("size", width=120, anchor="e", stretch=False)
        self.widgets["folder_tree"].insert("", "end", text="Tree scanner pending", values=("", "", ""))

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.widgets["folder_tree"].yview)
        self.widgets["folder_tree"].configure(yscrollcommand=vsb.set)
        self.widgets["folder_tree"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.widgets["folder_tree"].bind("<ButtonRelease-1>", self.on_tree_item_click)
        paned.add(tree_frame, weight=3)

        action_frame = tk.Frame(paned, bg=THEME["panel_bg"])
        btn_row = tk.Frame(action_frame, bg=THEME["panel_bg"])
        btn_row.pack(fill=tk.X, padx=5, pady=6)

        self._make_button(btn_row, "Compile Snapshot", self.compile_snapshot_placeholder, THEME["accent"], THEME["accent_hover"], bold=True).pack(side=tk.LEFT, padx=4)
        self._make_button(btn_row, "Export Tree MD", self.export_tree_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
        self._make_button(btn_row, "Export Filedump MD", self.export_filedump_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
        self._make_button(btn_row, "Export Tree+Dump MD", self.export_combined_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
        self._make_button(btn_row, "Open Output Folder", self.open_output_folder, THEME["success"], THEME["success_hover"]).pack(side=tk.RIGHT, padx=4)

        control_row = tk.Frame(action_frame, bg=THEME["panel_bg"])
        control_row.pack(fill=tk.X, padx=5, pady=2)
        self.widgets["respect_exclusions"] = tk.BooleanVar(value=True)
        tk.Checkbutton(
            control_row,
            text="Respect .gitignore + exclusions",
            variable=self.widgets["respect_exclusions"],
            command=self.apply_exclusion_settings,
            bg=THEME["panel_bg"],
            fg=THEME["text"],
            selectcolor=THEME["tree_bg"],
            activebackground=THEME["panel_bg"],
            activeforeground=THEME["text"],
        ).pack(side=tk.LEFT, padx=6)
        self.widgets["include_tree_in_filedump"] = tk.BooleanVar(value=False)
        tk.Checkbutton(
            control_row,
            text="Tree in filedump export",
            variable=self.widgets["include_tree_in_filedump"],
            bg=THEME["panel_bg"],
            fg=THEME["text"],
            selectcolor=THEME["tree_bg"],
            activebackground=THEME["panel_bg"],
            activeforeground=THEME["text"],
        ).pack(side=tk.LEFT, padx=6)
        self.widgets["include_binary_blobs"] = tk.BooleanVar(value=False)
        tk.Checkbutton(
            control_row,
            text="Preserve binary blobs in DB",
            variable=self.widgets["include_binary_blobs"],
            bg=THEME["panel_bg"],
            fg=THEME["text"],
            selectcolor=THEME["tree_bg"],
            activebackground=THEME["panel_bg"],
            activeforeground=THEME["text"],
        ).pack(side=tk.LEFT, padx=6)
        self._make_button(control_row, "All", lambda: self.set_global_selection(S_CHECKED), THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=2)
        self._make_button(control_row, "None", lambda: self.set_global_selection(S_UNCHECKED), THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=2)
        tk.Label(control_row, text="Excl. Pattern:", bg=THEME["panel_bg"], fg=THEME["muted_text"]).pack(side=tk.RIGHT, padx=4)
        self.widgets["exclusion_entry"] = tk.Entry(
            control_row,
            bg=THEME["field_bg_alt"],
            fg=THEME["field_text"],
            insertbackground=THEME["field_text"],
            width=22,
            relief=tk.FLAT,
        )
        self.widgets["exclusion_entry"].pack(side=tk.RIGHT, padx=4)
        self._make_button(control_row, "Add", self.add_exclusion_from_entry, THEME["accent"], THEME["accent_hover"]).pack(side=tk.RIGHT, padx=2)
        self._make_button(control_row, "Exclusions", self.manage_exclusions_popup, THEME["success"], THEME["success_hover"]).pack(side=tk.RIGHT, padx=2)
        self._make_button(control_row, "Rescan", self.request_rescan_tree, THEME["secondary"], THEME["secondary_hover"]).pack(side=tk.RIGHT, padx=2)

        self.widgets["log_box"] = scrolledtext.ScrolledText(
            action_frame,
            bg=THEME["log_bg"],
            fg=THEME["log_text"],
            insertbackground=THEME["log_text"],
            font=("Consolas", 9),
            state=tk.DISABLED,
            height=10,
        )
        self.widgets["log_box"].pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        paned.add(action_frame, weight=1)

        self.widgets["status_var"] = tk.StringVar(value="Ready.")
        self.widgets["status_bar"] = tk.Label(
            self.root,
            textvariable=self.widgets["status_var"],
            bg=THEME["status_bg"],
            fg=THEME["status_text"],
            anchor="w",
        )
        self.widgets["status_bar"].pack(fill=tk.X, side=tk.BOTTOM)

    def _make_button(self, parent, text, command, bg, active_bg, bold=False):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=THEME["text"],
            activebackground=active_bg,
            activeforeground=THEME["text"],
            font=("Arial", 10, "bold" if bold else "normal"),
            relief=tk.RAISED,
            padx=10,
            pady=6,
        )
# === [SECTION: TK_UI_LAYOUT] END ===


# === [SECTION: TK_TREE_BEHAVIOR] BEGIN ===
    def request_rescan_tree(self):
        self.run_threaded_action(self._scan_tree_impl, "scan_tree", use_popup=True)

    def request_rescan_tree_silent(self):
        self.run_threaded_action(self._scan_tree_impl, "scan_tree", use_popup=False)

    def _scan_tree_impl(self):
        root = self.selected_root if self.selected_root and self.selected_root.is_dir() else None
        if root is None:
            self.schedule_log_message("Cannot scan: no valid project root.", "ERROR")
            return
        self.exclusion_policy.respect_exclusions = bool(self.widgets.get("respect_exclusions").get()) if self.widgets.get("respect_exclusions") else True
        self.exclusion_policy.load_gitignore(root)
        self.schedule_log_message(f"Scanning project tree: {root}")
        rows, skipped = scan_project_tree(root, self.exclusion_policy, stop_event=self.stop_event)
        if self.stop_event.is_set():
            self.schedule_log_message("Tree scan cancelled.", "WARNING")
            return
        with self.state_lock:
            self.tree_rows = rows
            self.scan_skipped_paths = skipped
            valid_paths = {str(row["path"]) for row in rows}
            self.folder_item_states = {key: value for key, value in self.folder_item_states.items() if key in valid_paths}
            for row in rows:
                key = str(row["path"])
                if key not in self.folder_item_states:
                    parent = row.get("parent")
                    parent_state = self.folder_item_states.get(str(parent), S_CHECKED) if parent else S_CHECKED
                    self.folder_item_states[key] = parent_state
        self.gui_queue.put(lambda: self.populate_tree(rows))
        self.schedule_log_message(f"Scan complete: {len(rows)} visible entries, {len(skipped)} skipped entries.")

    def populate_tree(self, rows: list[dict]):
        tree = self.widgets["folder_tree"]
        tree.delete(*tree.get_children())
        for row in rows:
            iid = str(row["path"])
            parent = "" if row["parent"] is None else str(row["parent"])
            state = self.folder_item_states.get(iid, S_UNCHECKED)
            prefix = "📁" if row["entry_type"] == "dir" else "📄"
            size_text = "" if row["size_bytes"] is None else format_display_size(row["size_bytes"])
            is_dir = row["entry_type"] == "dir"
            tree.insert(
                parent,
                "end",
                iid=iid,
                text=f"{prefix} {row['name']}",
                image=self.icon_imgs.get(state, self.icon_imgs[S_UNCHECKED]),
                values=("↑" if is_dir else "", "↓" if is_dir else "", size_text),
                open=row["depth"] < 2,
            )
        self.refresh_tree_visuals()

    def refresh_tree_visuals(self, start_iid: str | None = None):
        tree = self.widgets["folder_tree"]

        def refresh_one(iid: str):
            if not tree.exists(iid):
                return
            state = self.folder_item_states.get(iid, S_UNCHECKED)
            tree.item(iid, image=self.icon_imgs.get(state, self.icon_imgs[S_UNCHECKED]))
            path = Path(iid)
            if path.is_dir():
                tree.set(iid, "nav_up", "↑")
                tree.set(iid, "nav_down", "↓")
            else:
                tree.set(iid, "nav_up", "")
                tree.set(iid, "nav_down", "")
            for child in tree.get_children(iid):
                refresh_one(child)

        if start_iid:
            refresh_one(start_iid)
        else:
            for child in tree.get_children(""):
                refresh_one(child)

    def on_tree_item_click(self, event):
        tree = event.widget
        iid = tree.identify_row(event.y)
        if not iid:
            return

        column = tree.identify_column(event.x)
        element = tree.identify("element", event.x, event.y) or ""
        path = Path(iid)

        if column == "#1" and path.is_dir():
            self.navigate_tree_to_path(path.parent)
            return

        if column == "#2" and path.is_dir():
            self.navigate_tree_to_path(path)
            return

        if column == "#0" or "image" in element:
            self.toggle_tree_item(iid)

    def toggle_tree_item(self, iid: str):
        with self.state_lock:
            current = self.folder_item_states.get(iid, S_UNCHECKED)
            new_state = S_CHECKED if current != S_CHECKED else S_UNCHECKED
            self._set_tree_state_recursive(iid, new_state)
        self.refresh_tree_visuals(iid)

    def _set_tree_state_recursive(self, iid: str, state: str):
        tree = self.widgets["folder_tree"]
        self.folder_item_states[iid] = state
        for child in tree.get_children(iid):
            self._set_tree_state_recursive(child, state)

    def set_global_selection(self, state: str):
        tree = self.widgets.get("folder_tree")
        if tree is None:
            return
        with self.state_lock:
            for child in tree.get_children(""):
                self._set_tree_state_recursive(child, state)
        self.refresh_tree_visuals()
        self.log_message(f"Set visible tree selection to: {state}")

    def is_selected(self, path: Path) -> bool:
        try:
            key = str(path.resolve())
        except Exception:
            return False
        with self.state_lock:
            return self.folder_item_states.get(key, S_UNCHECKED) == S_CHECKED
# === [SECTION: TK_TREE_BEHAVIOR] END ===


# === [SECTION: TK_EXCLUSION_UI] BEGIN ===
    def apply_exclusion_settings(self):
        var = self.widgets.get("respect_exclusions")
        self.exclusion_policy.respect_exclusions = bool(var.get()) if var else True
        self.log_message(f"Respect exclusions: {self.exclusion_policy.respect_exclusions}")

    def add_exclusion_from_entry(self):
        entry = self.widgets.get("exclusion_entry")
        if entry is None:
            return
        value = entry.get().strip()
        if not value:
            return
        self.exclusion_policy.dynamic_patterns.add(value)
        entry.delete(0, tk.END)
        self.log_message(f"Added exclusion pattern: {value}")
        self.request_rescan_tree()

    def manage_exclusions_popup(self):
        top = tk.Toplevel(self.root)
        top.title("Exclusion Patterns")
        top.configure(bg=THEME["panel_bg"])
        top.geometry("420x320")

        tk.Label(
            top,
            text="Dynamic user exclusion patterns",
            bg=THEME["panel_bg"],
            fg=THEME["text"],
            font=("Arial", 11, "bold"),
        ).pack(pady=8)

        listbox = tk.Listbox(
            top,
            bg=THEME["tree_bg"],
            fg=THEME["text"],
            selectbackground=THEME["selection"],
            selectforeground=THEME["heading_text"],
        )
        listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        for pattern in sorted(self.exclusion_policy.dynamic_patterns):
            listbox.insert(tk.END, pattern)

        def remove_selected():
            selection = listbox.curselection()
            if not selection:
                return
            pattern = listbox.get(selection[0])
            self.exclusion_policy.dynamic_patterns.discard(pattern)
            top.destroy()
            self.log_message(f"Removed exclusion pattern: {pattern}")
            self.request_rescan_tree()

        self._make_button(top, "Remove Selected", remove_selected, THEME["danger"], THEME["danger_hover"]).pack(pady=8)
# === [SECTION: TK_EXCLUSION_UI] END ===


# === [SECTION: TK_ACTIONS] BEGIN ===
    def navigate_tree_to_path(self, target_path: Path):
        try:
            target = target_path.resolve()
        except Exception:
            return
        if not target.is_dir():
            return
        self.widgets["selected_root_var"].set(str(target))
        self.selected_root = target
        self.log_message(f"Project root set: {self.selected_root}")
        self.request_rescan_tree()

    def navigate_to_parent(self):
        root = self.selected_root if self.selected_root and self.selected_root.is_dir() else None
        if root is None:
            return
        parent = root.parent
        if parent != root and parent.is_dir():
            self.navigate_tree_to_path(parent)

    def choose_root_dialog(self):
        selected = filedialog.askdirectory()
        if selected:
            self.widgets["selected_root_var"].set(selected)
            self.choose_root_from_entry()

    def choose_root_from_entry(self):
        candidate = Path(self.widgets["selected_root_var"].get()).expanduser()
        if not candidate.is_dir():
            messagebox.showerror("Invalid Project Root", f"Not a directory:\n{candidate}")
            return
        self.selected_root = candidate.resolve()
        self.log_message(f"Project root set: {self.selected_root}")
        self.request_rescan_tree()

    def get_output_dir(self) -> Path:
        root = self.selected_root if self.selected_root and self.selected_root.is_dir() else DEFAULT_ROOT_DIR
        return ensure_dir(root / OUTPUT_ROOT_NAME)

    def compile_snapshot_placeholder(self):
        self.run_threaded_action(self._compile_snapshot_impl, "compile_snapshot", use_popup=True)

    def _compile_snapshot_impl(self):
        root = self.selected_root if self.selected_root and self.selected_root.is_dir() else None
        if root is None:
            self.schedule_log_message("Cannot compile snapshot: no valid project root.", "ERROR")
            return

        self.exclusion_policy.respect_exclusions = bool(self.widgets.get("respect_exclusions").get()) if self.widgets.get("respect_exclusions") else True
        self.exclusion_policy.load_gitignore(root)

        with self.state_lock:
            tree_rows = list(self.tree_rows)
            folder_item_states = dict(self.folder_item_states)
            scan_skipped_paths = list(self.scan_skipped_paths)

        include_binary_blobs = bool(self.widgets.get("include_binary_blobs").get()) if self.widgets.get("include_binary_blobs") else False

        snapshot_path = compile_snapshot(
            root=root,
            output_dir=self.get_output_dir(),
            tree_rows=tree_rows,
            folder_item_states=folder_item_states,
            policy=self.exclusion_policy,
            scan_skipped_paths=scan_skipped_paths,
            include_binary_blobs=include_binary_blobs,
            stop_event=self.stop_event,
            log_callback=self.schedule_log_message,
        )
        self.latest_snapshot_path = snapshot_path
        self.schedule_log_message(f"Latest snapshot set: {snapshot_path}")
        self.schedule_log_message("Markdown projections are stored in the DB. Export Tree, Filedump, or Combined MD when ready. Manifest remains embedded in the SQLite snapshot.")
        self.schedule_log_message(f"Output folder: {self.get_output_dir()}")

    def _require_latest_snapshot(self) -> Path | None:
        if self.latest_snapshot_path and Path(self.latest_snapshot_path).exists():
            return Path(self.latest_snapshot_path)

        root = self.selected_root if self.selected_root and self.selected_root.is_dir() else None
        if root is not None:
            candidate = self.get_output_dir() / f"{root.name}_{SNAPSHOT_DB_SUFFIX}"
            if candidate.exists():
                self.latest_snapshot_path = candidate
                return candidate

        self.log_message("No snapshot DB found yet. Compile Snapshot DB first.", "WARNING")
        return None

    def export_snapshot_output(self, output_name: str, suffix: str, content_override: str | None = None):
        snapshot_path = self._require_latest_snapshot()
        if snapshot_path is None:
            return
        root = self.selected_root if self.selected_root and self.selected_root.is_dir() else DEFAULT_ROOT_DIR
        out_path = self.get_output_dir() / snapshot_output_filename(root, suffix)
        try:
            content = content_override if content_override is not None else load_snapshot_output(snapshot_path, output_name)
            write_text_file(out_path, content)
            self.log_message(f"Exported {output_name}: {out_path}")
        except Exception as exc:
            self.log_message(f"Failed to export {output_name}: {exc}", "ERROR")

    def export_tree_markdown(self):
        self.export_snapshot_output("project_tree_markdown", TREE_MD_SUFFIX)

    def export_filedump_markdown(self):
        snapshot_path = self._require_latest_snapshot()
        if snapshot_path is None:
            return
        try:
            filedump_markdown = load_snapshot_output(snapshot_path, "project_filedump_markdown")
            include_tree = bool(self.widgets.get("include_tree_in_filedump").get()) if self.widgets.get("include_tree_in_filedump") else False
            if include_tree:
                tree_markdown = load_snapshot_output(snapshot_path, "project_tree_markdown")
                filedump_markdown = combine_tree_and_filedump_markdown(tree_markdown, filedump_markdown)
            self.export_snapshot_output("project_filedump_markdown", FILEDUMP_MD_SUFFIX, content_override=filedump_markdown)
        except Exception as exc:
            self.log_message(f"Failed to export filedump markdown: {exc}", "ERROR")

    def export_combined_markdown(self):
        snapshot_path = self._require_latest_snapshot()
        if snapshot_path is None:
            return
        try:
            tree_markdown = load_snapshot_output(snapshot_path, "project_tree_markdown")
            filedump_markdown = load_snapshot_output(snapshot_path, "project_filedump_markdown")
            combined = combine_tree_and_filedump_markdown(tree_markdown, filedump_markdown)
            self.export_snapshot_output("project_tree_and_filedump_markdown", COMBINED_MD_SUFFIX, content_override=combined)
        except Exception as exc:
            self.log_message(f"Failed to export combined markdown: {exc}", "ERROR")

    def export_manifest_markdown(self):
        self.export_snapshot_output("snapshot_manifest_markdown", MANIFEST_MD_SUFFIX)

    def pending_projection_notice(self):
        self.log_message("Projection export is available after compiling a snapshot DB.", "WARNING")

    def open_output_folder(self):
        out_dir = self.get_output_dir()
        try:
            if platform.system() == "Windows":
                os.startfile(out_dir)
            elif platform.system() == "Darwin":
                subprocess.run(["open", str(out_dir)], check=False)
            else:
                subprocess.run(["xdg-open", str(out_dir)], check=False)
            self.log_message(f"Opened output folder: {out_dir}")
        except Exception as exc:
            self.log_message(f"Could not open output folder: {exc}", "ERROR")
# === [SECTION: TK_ACTIONS] END ===


# === [SECTION: THREADING_AND_LOGGING] BEGIN ===
    def _activity_blinker(self):
        if self.running_tasks:
            task_names = ", ".join(sorted(self.running_tasks))
            self.widgets["status_var"].set(f"[ACTIVE] {task_names}")
            current_color = self.widgets["status_bar"].cget("bg")
            next_color = THEME["panel_alt_bg"] if current_color == THEME["status_bg"] else THEME["status_bg"]
            self.widgets["status_bar"].config(bg=next_color)
        else:
            self.widgets["status_bar"].config(bg=THEME["status_bg"])
        self.root.after(500, self._activity_blinker)

    def cancel_current_operations(self):
        self.stop_event.set()
        self.log_message("Stop signal sent to active task.", "WARNING")

    def run_threaded_action(self, target_function, task_id: str, use_popup=False):
        if task_id in self.running_tasks:
            self.log_message(f"Task already running: {task_id}", "WARNING")
            return

        if use_popup:
            self.current_progress_popup = ProgressPopup(self.root, title=f"Working: {task_id}", on_cancel=self.cancel_current_operations)

        def runner():
            self.running_tasks.add(task_id)
            self.stop_event.clear()
            try:
                target_function()
            except Exception as exc:
                self.schedule_log_message(f"CRASH in {task_id}: {exc}\n{traceback.format_exc()}", "CRITICAL")
            finally:
                self.running_tasks.discard(task_id)
                if use_popup and self.current_progress_popup:
                    popup = self.current_progress_popup
                    self.current_progress_popup = None
                    self.gui_queue.put(popup.close)
                self.schedule_log_message(f"Task finished: {task_id}")

        threading.Thread(target=runner, daemon=True).start()

    def schedule_log_message(self, msg: str, level: str = "INFO"):
        self.gui_queue.put(lambda: self.log_message(msg, level))
        if self.current_progress_popup:
            self.gui_queue.put(lambda: self.current_progress_popup.update_text(f"[{level}] {msg}") if self.current_progress_popup else None)

    def log_message(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("[%H:%M:%S]")
        full_msg = f"{ts} [{level}] {msg}\n"
        log_box = self.widgets.get("log_box")
        if log_box:
            log_box.config(state=tk.NORMAL)
            log_box.insert(tk.END, full_msg)
            log_box.config(state=tk.DISABLED)
            log_box.see(tk.END)
        status = self.widgets.get("status_var")
        if status:
            status.set(f"{ts} {msg}")

    def process_gui_queue(self):
        while True:
            try:
                callback = self.gui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:
                pass
        self.root.after(100, self.process_gui_queue)
# === [SECTION: THREADING_AND_LOGGING] END ===


# === [SECTION: CLI] BEGIN ===
# minimal CLI:
#   optional compile snapshot from path later
#   simple launch GUI for now
# === [SECTION: CLI] END ===


# === [SECTION: ENTRYPOINT] BEGIN ===
def run_gui():
    root = tk.Tk()
    ProjectMapperApp(root)
    root.mainloop()


def main():
    run_gui()


if __name__ == "__main__":
    main()
# === [SECTION: ENTRYPOINT] END ===



