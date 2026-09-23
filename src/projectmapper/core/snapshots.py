"""Headless snapshots services."""
from uuid import uuid4
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

def snapshot_output_filename(root: Path, suffix: str) -> str:
    return f"{root.name}_{suffix}"


def load_snapshot_output(snapshot_path: Path, output_name: str) -> str:
    if not snapshot_path or not snapshot_path.exists():
        raise FileNotFoundError(f"Snapshot DB not found: {snapshot_path}")
    with contextlib.closing(sqlite3.connect(snapshot_path)) as conn:
        row = conn.execute(
            "SELECT content FROM snapshot_outputs WHERE name = ?",
            (output_name,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Snapshot output not found: {output_name}")
    return row[0]


def load_snapshot_metadata(snapshot_path: Path) -> dict:
    if not snapshot_path or not Path(snapshot_path).exists():
        return {}
    try:
        with contextlib.closing(sqlite3.connect(snapshot_path)) as conn:
            rows = conn.execute("SELECT key, value FROM snapshot_metadata").fetchall()
    except sqlite3.Error:
        return {}
    return {key: value for key, value in rows}


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

def capture_signature(root, policy, selection, include_binary=False, stop_event=None):
    rows, skipped = scan_project_tree(root, policy, stop_event)
    inventory = []
    for row in rows:
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("Capture verification cancelled.")
        value = [row["relative_path"], row["entry_type"], selection.get(str(row["path"]), S_CHECKED)]
        if row["entry_type"] == "file":
            digest = hashlib.sha256()
            with row["path"].open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    if stop_event is not None and stop_event.is_set():
                        raise RuntimeError("Capture verification cancelled.")
                    digest.update(chunk)
            value.append(digest.hexdigest())
        inventory.append(value)
    return hashlib.sha256(json.dumps([inventory, policy.collect_rules(), bool(include_binary), skipped], sort_keys=True).encode()).hexdigest()


def snapshot_matches(path, root, policy, selection, include_binary=False):
    try:
        expected = load_snapshot_metadata(path).get("capture_signature")
    except (OSError, sqlite3.Error):
        return False
    return bool(expected) and expected == capture_signature(root, policy, selection, include_binary)


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
    build_path = output_dir / f".{root.name}-{uuid4().hex}.building"
    signature = capture_signature(root, policy, folder_item_states, include_binary_blobs, stop_event)

    # Build into a scratch DB first, then swap it over the live one, so a locked
    # or half-written snapshot can never be mistaken for a fresh one.
    gc.collect()
    for leftover in (build_path, Path(str(build_path) + "-journal")):
        if leftover.exists():
            remove_file_with_retry(leftover)

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

    with contextlib.closing(sqlite3.connect(build_path)) as conn:
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
            "source_max_mtime": max_tree_mtime(visible_rows),
            "capture_signature": signature,
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

    gc.collect()
    if cancelled or (stop_event is not None and stop_event.is_set()):
        remove_file_with_retry(build_path)
        raise RuntimeError("Snapshot compilation cancelled; previous snapshot preserved.")
    if signature != capture_signature(root, policy, folder_item_states, include_binary_blobs, stop_event):
        remove_file_with_retry(build_path)
        raise RuntimeError("Project changed during capture; previous snapshot preserved.")
    os.replace(build_path, snapshot_path)

    emit(
        f"Snapshot compiled: {snapshot_path.name} ({tree_entry_count} tree entries, {captured_file_count} text files, {captured_blob_count} blobs, {skipped_path_count} skipped)"
    )
    return snapshot_path
