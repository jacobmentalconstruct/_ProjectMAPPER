# Project Tree + Filedump

This combined export includes the project tree first, followed by the captured file dump.

---

# Project Tree

This standalone tree is intended as a lightweight project surface map. It can be shared without the full filedump so an agent can see the project shape, identify missing/unincluded files, and request specific follow-up uploads when needed.

The SQLite snapshot remains the authoritative truth source for the manifest, selected file contents, skipped paths, exclusion rules, mapper state, and environment hints.

- Source root: `C:\Users\jacob\Documents\_AppDesign\_LivePROJECTS\_ProjectMAPPER`
- Snapshot: `_ProjectMAPPER_snapshot.sqlite3`
- Generated: `2026-04-27T11:02:13`

```text
[x] 📁 _ProjectMAPPER/
    [x] 📁 assets/
        [x] 📁 icons/
            [x] 📄 projectmapper.ico
    [x] 📁 src/
        [x] 📄 __init__.py
        [x] 📄 app._lineNUMBERED.pipe.py
        [x] 📄 app.py
        [x] 📄 app_BACKUP.py
    [x] 📄 _ProjectMAPPER.spec
    [x] 📄 gitignore
    [x] 📄 LICENSE.md
    [x] 📄 README.md
    [x] 📄 requirements.txt
    [x] 📄 setup_env.bat
```

---

# Project Filedump

- Source root: `C:\Users\jacob\Documents\_AppDesign\_LivePROJECTS\_ProjectMAPPER`
- Snapshot: `_ProjectMAPPER_snapshot.sqlite3`
- Generated: `2026-04-27T11:02:13`
- Captured files: `10`

---

## FILE: `src/__init__.py`

```python

```

---

## FILE: `src/app._lineNUMBERED.pipe.py`

```python
   1│ # ==============================================================================
   2│ # ProjectMapper Snapshot Compiler
   3│ # Single-file tagged monolith scaffold
   4│ # ==============================================================================
   5│ 
   6│ # === [SECTION: IMPORTS] BEGIN ===
   7│ import sys
   8│ import os
   9│ import platform
  10│ import subprocess
  11│ import threading
  12│ import queue
  13│ import traceback
  14│ import fnmatch
  15│ import sqlite3
  16│ from pathlib import Path
  17│ from datetime import datetime
  18│ import tkinter as tk
  19│ from tkinter import filedialog, scrolledtext, ttk, messagebox
  20│ import tkinter.font as tkFont
  21│ # === [SECTION: IMPORTS] END ===
  22│ 
  23│ 
  24│ # === [SECTION: APP_METADATA] BEGIN ===
  25│ APP_NAME = "ProjectMapper Snapshot Compiler"
  26│ APP_VERSION = "0.3.0-snapshot-compiler"
  27│ SNAPSHOT_SCHEMA_VERSION = "0.1"
  28│ SNAPSHOT_COMPILER_ID = "projectmapper.snapshot_compiler"
  29│ # === [SECTION: APP_METADATA] END ===
  30│ 
  31│ 
  32│ # === [SECTION: CONSTANTS] BEGIN ===
  33│ APP_DIR = Path(__file__).resolve().parent
  34│ DEFAULT_ROOT_DIR = APP_DIR
  35│ OUTPUT_ROOT_NAME = "_projectmapper"
  36│ MAX_TEXT_FILE_SIZE_BYTES = 1_000_000
  37│ TEXT_ENCODING = "utf-8"
  38│ 
  39│ S_CHECKED = "checked"
  40│ S_UNCHECKED = "unchecked"
  41│ 
  42│ SNAPSHOT_DB_SUFFIX = "snapshot.sqlite3"
  43│ TREE_MD_SUFFIX = "project_tree.md"
  44│ FILEDUMP_MD_SUFFIX = "project_filedump.md"
  45│ MANIFEST_MD_SUFFIX = "snapshot_manifest.md"
  46│ COMBINED_MD_SUFFIX = "project_tree_and_filedump.md"
  47│ 
  48│ EXCLUDED_FOLDERS = {
  49│     "node_modules", ".git", "__pycache__", ".venv", ".mypy_cache",
  50│     "_logs", "_projectmapper", "dist", "build", ".vscode", ".idea",
  51│     "target", "out", "bin", "obj", "Debug", "Release", "logs", "venv"
  52│ }
  53│ 
  54│ PREDEFINED_EXCLUDED_FILENAMES = {
  55│     "package-lock.json", "yarn.lock", ".DS_Store", "Thumbs.db",
  56│     "*.pyc", "*.pyo", "*.swp", "*.swo"
  57│ }
  58│ 
  59│ FORCE_BINARY_EXTENSIONS_FOR_DUMP = {
  60│     ".tar.gz", ".gz", ".zip", ".rar", ".7z", ".bz2", ".xz", ".tgz",
  61│     ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff",
  62│     ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a",
  63│     ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
  64│     ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods",
  65│     ".exe", ".dll", ".so", ".o", ".a", ".lib", ".app", ".dmg", ".deb", ".rpm",
  66│     ".db", ".sqlite", ".sqlite3", ".db3", ".mdb", ".accdb", ".dat", ".idx", ".pickle", ".joblib",
  67│     ".pyc", ".pyo", ".class", ".jar", ".wasm",
  68│     ".ttf", ".otf", ".woff", ".woff2",
  69│     ".iso", ".img", ".bin", ".bak", ".data", ".asset", ".pak"
  70│ }
  71│ # === [SECTION: CONSTANTS] END ===
  72│ 
  73│ 
  74│ # === [SECTION: THEME] BEGIN ===
  75│ THEME = {
  76│     "app_bg": "#161A1F",
  77│     "panel_bg": "#1E252D",
  78│     "panel_alt_bg": "#273241",
  79│     "field_bg": "#263140",
  80│     "field_bg_alt": "#2D3948",
  81│     "tree_bg": "#1A212B",
  82│     "log_bg": "#10161E",
  83│     "status_bg": "#0D1117",
  84│     "status_text": "#89D6A0",
  85│     "text": "#E7EDF4",
  86│     "muted_text": "#97A4B3",
  87│     "field_text": "#D6E2EE",
  88│     "heading_bg": "#2A3441",
  89│     "heading_text": "#F3F6F9",
  90│     "selection": "#3B7E8D",
  91│     "accent": "#C56F3D",
  92│     "accent_hover": "#D78251",
  93│     "secondary": "#2E7081",
  94│     "secondary_hover": "#3A8EA2",
  95│     "success": "#2F8E6A",
  96│     "success_hover": "#3AA27C",
  97│     "danger": "#B75A4D",
  98│     "danger_hover": "#CB6B5E",
  99│     "checkbox_checked": "#C56F3D",
 100│     "checkbox_border": "#728195",
 101│     "log_text": "#E1E7EE",
 102│     "log_accent": "#89D6A0",
 103│ }
 104│ # === [SECTION: THEME] END ===
 105│ 
 106│ 
 107│ # === [SECTION: PYTHONW_SAFETY] BEGIN ===
 108│ if sys.stdout is None:
 109│     sys.stdout = open(os.devnull, "w")
 110│ if sys.stderr is None:
 111│     sys.stderr = open(os.devnull, "w")
 112│ # === [SECTION: PYTHONW_SAFETY] END ===
 113│ 
 114│ 
 115│ # === [SECTION: PURE_HELPERS] BEGIN ===
 116│ def now_stamp() -> str:
 117│     return datetime.now().strftime("%Y%m%d_%H%M%S")
 118│ 
 119│ 
 120│ def now_iso() -> str:
 121│     return datetime.now().isoformat(timespec="seconds")
 122│ 
 123│ 
 124│ def format_display_size(size_bytes: int) -> str:
 125│     if size_bytes < 1024:
 126│         return f"{size_bytes} B"
 127│     size_kb = size_bytes / 1024
 128│     if size_kb < 1024:
 129│         return f"{size_kb:.1f} KB"
 130│     size_mb = size_kb / 1024
 131│     if size_mb < 1024:
 132│         return f"{size_mb:.1f} MB"
 133│     size_gb = size_mb / 1024
 134│     return f"{size_gb:.2f} GB"
 135│ 
 136│ 
 137│ def ensure_dir(path: Path) -> Path:
 138│     path.mkdir(parents=True, exist_ok=True)
 139│     return path
 140│ 
 141│ 
 142│ def rel_posix(path: Path, root: Path) -> str:
 143│     try:
 144│         return path.relative_to(root).as_posix()
 145│     except Exception:
 146│         return path.name
 147│ 
 148│ 
 149│ def is_path_inside(path: Path, root: Path) -> bool:
 150│     try:
 151│         path.resolve().relative_to(root.resolve())
 152│         return True
 153│     except Exception:
 154│         return False
 155│ 
 156│ 
 157│ def is_binary(file_path: Path) -> bool:
 158│     try:
 159│         with open(file_path, "rb") as handle:
 160│             return b"\0" in handle.read(1024)
 161│     except Exception:
 162│         return True
 163│ 
 164│ 
 165│ def safe_stat_size(path: Path) -> int | None:
 166│     try:
 167│         return path.stat().st_size
 168│     except OSError:
 169│         return None
 170│ 
 171│ 
 172│ def get_folder_size_bytes(folder_path: Path, stop_event=None) -> int:
 173│     total_size = 0
 174│     try:
 175│         for entry in os.scandir(folder_path):
 176│             if stop_event is not None and stop_event.is_set():
 177│                 break
 178│             try:
 179│                 if entry.is_file(follow_symlinks=False):
 180│                     total_size += entry.stat(follow_symlinks=False).st_size
 181│                 elif entry.is_dir(follow_symlinks=False):
 182│                     total_size += get_folder_size_bytes(Path(entry.path), stop_event=stop_event)
 183│             except OSError:
 184│                 continue
 185│     except OSError:
 186│         pass
 187│     return total_size
 188│ 
 189│ 
 190│ def safe_read_text(path: Path, max_bytes: int = MAX_TEXT_FILE_SIZE_BYTES) -> tuple[str | None, str | None]:
 191│     size = safe_stat_size(path)
 192│     if size is None:
 193│         return None, "stat_failed"
 194│     if size > max_bytes:
 195│         return None, "over_size_limit"
 196│     if "".join(path.suffixes).lower() in FORCE_BINARY_EXTENSIONS_FOR_DUMP:
 197│         return None, "forced_binary_extension"
 198│     if is_binary(path):
 199│         return None, "binary_detected"
 200│     try:
 201│         return path.read_text(encoding=TEXT_ENCODING, errors="ignore"), None
 202│     except PermissionError:
 203│         return None, "permission_denied"
 204│     except Exception as exc:
 205│         return None, f"read_failed: {exc}"
 206│ # === [SECTION: PURE_HELPERS] END ===
 207│ 
 208│ 
 209│ # === [SECTION: SNAPSHOT_DATA_HELPERS] BEGIN ===
 210│ def snapshot_output_filename(root: Path, suffix: str) -> str:
 211│     return f"{root.name}_{suffix}"
 212│ 
 213│ 
 214│ def load_snapshot_output(snapshot_path: Path, output_name: str) -> str:
 215│     if not snapshot_path or not snapshot_path.exists():
 216│         raise FileNotFoundError(f"Snapshot DB not found: {snapshot_path}")
 217│     with sqlite3.connect(snapshot_path) as conn:
 218│         row = conn.execute(
 219│             "SELECT content FROM snapshot_outputs WHERE name = ?",
 220│             (output_name,),
 221│         ).fetchone()
 222│     if row is None:
 223│         raise KeyError(f"Snapshot output not found: {output_name}")
 224│     return row[0]
 225│ 
 226│ 
 227│ def write_text_file(path: Path, content: str) -> Path:
 228│     ensure_dir(path.parent)
 229│     path.write_text(content, encoding=TEXT_ENCODING, errors="ignore")
 230│     return path
 231│ 
 232│ 
 233│ def combine_tree_and_filedump_markdown(tree_markdown: str, filedump_markdown: str) -> str:
 234│     return "\n".join([
 235│         "# Project Tree + Filedump",
 236│         "",
 237│         "This combined export includes the project tree first, followed by the captured file dump.",
 238│         "",
 239│         "---",
 240│         "",
 241│         tree_markdown.rstrip(),
 242│         "",
 243│         "---",
 244│         "",
 245│         filedump_markdown.rstrip(),
 246│         "",
 247│     ])
 248│ # === [SECTION: SNAPSHOT_DATA_HELPERS] END ===
 249│ 
 250│ 
 251│ # === [SECTION: EXCLUSION_POLICY] BEGIN ===
 252│ class ExclusionPolicy:
 253│     def __init__(self):
 254│         self.respect_exclusions = True
 255│         self.dynamic_patterns = set()
 256│         self.gitignore_dirnames = set()
 257│         self.gitignore_file_patterns = set()
 258│         self.gitignore_path_patterns = set()
 259│ 
 260│     def load_gitignore(self, root: Path):
 261│         self.gitignore_dirnames.clear()
 262│         self.gitignore_file_patterns.clear()
 263│         self.gitignore_path_patterns.clear()
 264│ 
 265│         gi = root / ".gitignore"
 266│         if not gi.exists():
 267│             return
 268│ 
 269│         try:
 270│             lines = gi.read_text(encoding=TEXT_ENCODING, errors="ignore").splitlines()
 271│         except Exception:
 272│             return
 273│ 
 274│         for raw in lines:
 275│             pattern = raw.strip()
 276│             if not pattern or pattern.startswith("#") or pattern.startswith("!"):
 277│                 continue
 278│             pattern = pattern.replace("\\", "/")
 279│             if pattern.endswith("/"):
 280│                 value = pattern[:-1].strip("/")
 281│                 if value:
 282│                     self.gitignore_dirnames.add(value)
 283│             elif "/" in pattern:
 284│                 self.gitignore_path_patterns.add(pattern.strip("/"))
 285│             else:
 286│                 self.gitignore_file_patterns.add(pattern)
 287│ 
 288│     def collect_rules(self) -> list[dict]:
 289│         rules = []
 290│         rules.append({"rule_type": "toggle", "pattern": "respect_exclusions", "source": "ui", "active": int(self.respect_exclusions)})
 291│         for pattern in sorted(EXCLUDED_FOLDERS):
 292│             rules.append({"rule_type": "directory", "pattern": pattern, "source": "hardcoded_folder", "active": 1})
 293│         for pattern in sorted(PREDEFINED_EXCLUDED_FILENAMES):
 294│             rules.append({"rule_type": "filename", "pattern": pattern, "source": "predefined_filename", "active": 1})
 295│         for pattern in sorted(self.dynamic_patterns):
 296│             rules.append({"rule_type": "filename", "pattern": pattern, "source": "dynamic_user_pattern", "active": 1})
 297│         for pattern in sorted(self.gitignore_dirnames):
 298│             rules.append({"rule_type": "directory", "pattern": pattern, "source": "gitignore_dirname", "active": 1})
 299│         for pattern in sorted(self.gitignore_file_patterns):
 300│             rules.append({"rule_type": "filename", "pattern": pattern, "source": "gitignore_file_pattern", "active": 1})
 301│         for pattern in sorted(self.gitignore_path_patterns):
 302│             rules.append({"rule_type": "path", "pattern": pattern, "source": "gitignore_path_pattern", "active": 1})
 303│         return rules
 304│ 
 305│     def should_exclude_path(self, path: Path, root: Path) -> tuple[bool, str | None]:
 306│         if not self.respect_exclusions:
 307│             return False, None
 308│ 
 309│         try:
 310│             p = path.resolve()
 311│             r = root.resolve()
 312│         except Exception:
 313│             return False, None
 314│ 
 315│         if p != r and not is_path_inside(p, r):
 316│             return False, None
 317│ 
 318│         name = p.name
 319│         rel = rel_posix(p, r)
 320│ 
 321│         if p.is_dir():
 322│             if name in EXCLUDED_FOLDERS:
 323│                 return True, "hardcoded_folder"
 324│             if name in self.gitignore_dirnames:
 325│                 return True, "gitignore_dirname"
 326│             for pattern in self.gitignore_path_patterns:
 327│                 if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel + "/", pattern) or fnmatch.fnmatch(rel + "/", pattern + "/"):
 328│                     return True, "gitignore_path_pattern"
 329│             return False, None
 330│ 
 331│         patterns = set(PREDEFINED_EXCLUDED_FILENAMES).union(self.dynamic_patterns)
 332│         for pattern in patterns:
 333│             if fnmatch.fnmatch(name, pattern):
 334│                 return True, "filename_pattern"
 335│         for pattern in self.gitignore_file_patterns:
 336│             if fnmatch.fnmatch(name, pattern):
 337│                 return True, "gitignore_file_pattern"
 338│         for pattern in self.gitignore_path_patterns:
 339│             if fnmatch.fnmatch(rel, pattern):
 340│                 return True, "gitignore_path_pattern"
 341│         return False, None
 342│ # === [SECTION: EXCLUSION_POLICY] END ===
 343│ 
 344│ 
 345│ # === [SECTION: FILESYSTEM_SCANNER] BEGIN ===
 346│ def scan_project_tree(root: Path, policy: ExclusionPolicy, stop_event=None) -> tuple[list[dict], list[dict]]:
 347│     root = root.resolve()
 348│     rows = []
 349│     skipped = []
 350│ 
 351│     def add_row(path: Path, parent: Path | None, depth: int):
 352│         size_bytes = get_folder_size_bytes(path, stop_event=stop_event) if path.is_dir() else safe_stat_size(path)
 353│         rows.append({
 354│             "path": path.resolve(),
 355│             "parent": parent.resolve() if parent else None,
 356│             "relative_path": "." if path == root else rel_posix(path, root),
 357│             "parent_relative_path": None if parent is None else ("." if parent == root else rel_posix(parent, root)),
 358│             "name": path.name,
 359│             "entry_type": "dir" if path.is_dir() else "file",
 360│             "depth": depth,
 361│             "size_bytes": size_bytes,
 362│         })
 363│ 
 364│     def recurse(current: Path, depth: int):
 365│         if stop_event is not None and stop_event.is_set():
 366│             return
 367│         try:
 368│             items = sorted(list(current.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
 369│         except PermissionError:
 370│             skipped.append({"relative_path": rel_posix(current, root), "skip_reason": "permission_denied", "detail": "Cannot list directory"})
 371│             return
 372│         except Exception as exc:
 373│             skipped.append({"relative_path": rel_posix(current, root), "skip_reason": "list_failed", "detail": str(exc)})
 374│             return
 375│ 
 376│         for item in items:
 377│             if stop_event is not None and stop_event.is_set():
 378│                 return
 379│             excluded, reason = policy.should_exclude_path(item, root)
 380│             if excluded:
 381│                 skipped.append({"relative_path": rel_posix(item, root), "skip_reason": "excluded_by_rule", "detail": reason or "excluded"})
 382│                 continue
 383│             add_row(item, current, depth + 1)
 384│             if item.is_dir():
 385│                 recurse(item, depth + 1)
 386│ 
 387│     add_row(root, None, 0)
 388│     recurse(root, 0)
 389│     return rows, skipped
 390│ # === [SECTION: FILESYSTEM_SCANNER] END ===
 391│ 
 392│ 
 393│ # === [SECTION: SNAPSHOT_SCHEMA] BEGIN ===
 394│ def create_snapshot_schema(conn: sqlite3.Connection):
 395│     conn.execute(
 396│         """
 397│         CREATE TABLE IF NOT EXISTS snapshot_metadata (
 398│             key TEXT PRIMARY KEY,
 399│             value TEXT NOT NULL
 400│         )
 401│         """
 402│     )
 403│     conn.execute(
 404│         """
 405│         CREATE TABLE IF NOT EXISTS snapshot_manifest (
 406│             id INTEGER PRIMARY KEY CHECK (id = 1),
 407│             manifest_version TEXT NOT NULL,
 408│             title TEXT NOT NULL,
 409│             summary TEXT NOT NULL,
 410│             contents_markdown TEXT NOT NULL,
 411│             created_at TEXT NOT NULL
 412│         )
 413│         """
 414│     )
 415│     conn.execute(
 416│         """
 417│         CREATE TABLE IF NOT EXISTS project_tree (
 418│             tree_order INTEGER NOT NULL,
 419│             relative_path TEXT PRIMARY KEY,
 420│             parent_relative_path TEXT,
 421│             name TEXT NOT NULL,
 422│             entry_type TEXT NOT NULL,
 423│             depth INTEGER NOT NULL,
 424│             size_bytes INTEGER,
 425│             is_selected INTEGER NOT NULL
 426│         )
 427│         """
 428│     )
 429│     conn.execute(
 430│         """
 431│         CREATE TABLE IF NOT EXISTS project_files (
 432│             dump_order INTEGER NOT NULL,
 433│             relative_path TEXT PRIMARY KEY,
 434│             parent_relative_path TEXT,
 435│             size_bytes INTEGER NOT NULL,
 436│             content TEXT NOT NULL,
 437│             captured_at TEXT NOT NULL
 438│         )
 439│         """
 440│     )
 441│     conn.execute(
 442│         """
 443│         CREATE TABLE IF NOT EXISTS snapshot_exclusion_rules (
 444│             id INTEGER PRIMARY KEY AUTOINCREMENT,
 445│             rule_type TEXT NOT NULL,
 446│             pattern TEXT NOT NULL,
 447│             source TEXT NOT NULL,
 448│             active INTEGER NOT NULL
 449│         )
 450│         """
 451│     )
 452│     conn.execute(
 453│         """
 454│         CREATE TABLE IF NOT EXISTS snapshot_skipped_paths (
 455│             id INTEGER PRIMARY KEY AUTOINCREMENT,
 456│             relative_path TEXT NOT NULL,
 457│             skip_reason TEXT NOT NULL,
 458│             detail TEXT,
 459│             size_bytes INTEGER,
 460│             entry_type TEXT,
 461│             source TEXT NOT NULL
 462│         )
 463│         """
 464│     )
 465│     conn.execute(
 466│         """
 467│         CREATE TABLE IF NOT EXISTS snapshot_mapper_state (
 468│             relative_path TEXT PRIMARY KEY,
 469│             state TEXT NOT NULL,
 470│             entry_type TEXT,
 471│             is_visible INTEGER NOT NULL,
 472│             source TEXT NOT NULL
 473│         )
 474│         """
 475│     )
 476│     conn.execute(
 477│         """
 478│         CREATE TABLE IF NOT EXISTS snapshot_environment (
 479│             key TEXT PRIMARY KEY,
 480│             value TEXT NOT NULL
 481│         )
 482│         """
 483│     )
 484│     conn.execute(
 485│         """
 486│         CREATE TABLE IF NOT EXISTS snapshot_outputs (
 487│             name TEXT PRIMARY KEY,
 488│             output_type TEXT NOT NULL,
 489│             content TEXT NOT NULL,
 490│             created_at TEXT NOT NULL,
 491│             external_path TEXT
 492│         )
 493│         """
 494│     )
 495│     conn.execute(
 496│         """
 497│         CREATE TABLE IF NOT EXISTS snapshot_errors (
 498│             id INTEGER PRIMARY KEY AUTOINCREMENT,
 499│             relative_path TEXT,
 500│             error TEXT NOT NULL,
 501│             context TEXT,
 502│             created_at TEXT NOT NULL
 503│         )
 504│         """
 505│     )
 506│     conn.execute("CREATE INDEX IF NOT EXISTS idx_project_tree_order ON project_tree(tree_order)")
 507│     conn.execute("CREATE INDEX IF NOT EXISTS idx_project_tree_parent ON project_tree(parent_relative_path)")
 508│     conn.execute("CREATE INDEX IF NOT EXISTS idx_project_files_order ON project_files(dump_order)")
 509│     conn.execute("CREATE INDEX IF NOT EXISTS idx_skipped_reason ON snapshot_skipped_paths(skip_reason)")
 510│ # === [SECTION: SNAPSHOT_SCHEMA] END ===
 511│ 
 512│ 
 513│ # === [SECTION: SNAPSHOT_WRITERS] BEGIN ===
 514│ def upsert_snapshot_metadata(conn: sqlite3.Connection, key: str, value):
 515│     conn.execute(
 516│         "INSERT OR REPLACE INTO snapshot_metadata (key, value) VALUES (?, ?)",
 517│         (key, "" if value is None else str(value)),
 518│     )
 519│ 
 520│ 
 521│ def insert_project_tree_row(conn: sqlite3.Connection, tree_order: int, row: dict, is_selected: bool):
 522│     conn.execute(
 523│         """
 524│         INSERT OR REPLACE INTO project_tree (
 525│             tree_order, relative_path, parent_relative_path, name,
 526│             entry_type, depth, size_bytes, is_selected
 527│         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
 528│         """,
 529│         (
 530│             tree_order,
 531│             row["relative_path"],
 532│             row.get("parent_relative_path"),
 533│             row["name"],
 534│             row["entry_type"],
 535│             row["depth"],
 536│             row.get("size_bytes"),
 537│             int(is_selected),
 538│         ),
 539│     )
 540│ 
 541│ 
 542│ def insert_project_file(conn: sqlite3.Connection, dump_order: int, relative_path: str, parent_relative_path: str | None, size_bytes: int, content: str):
 543│     conn.execute(
 544│         """
 545│         INSERT OR REPLACE INTO project_files (
 546│             dump_order, relative_path, parent_relative_path, size_bytes, content, captured_at
 547│         ) VALUES (?, ?, ?, ?, ?, ?)
 548│         """,
 549│         (dump_order, relative_path, parent_relative_path, size_bytes, content, now_iso()),
 550│     )
 551│ 
 552│ 
 553│ def insert_exclusion_rules(conn: sqlite3.Connection, rules: list[dict]):
 554│     conn.executemany(
 555│         """
 556│         INSERT INTO snapshot_exclusion_rules (rule_type, pattern, source, active)
 557│         VALUES (?, ?, ?, ?)
 558│         """,
 559│         [
 560│             (
 561│                 rule.get("rule_type", "unknown"),
 562│                 rule.get("pattern", ""),
 563│                 rule.get("source", "unknown"),
 564│                 int(rule.get("active", 1)),
 565│             )
 566│             for rule in rules
 567│         ],
 568│     )
 569│ 
 570│ 
 571│ def insert_skipped_path(conn: sqlite3.Connection, relative_path: str, skip_reason: str, detail: str | None = None, size_bytes: int | None = None, entry_type: str | None = None, source: str = "snapshot_compiler"):
 572│     conn.execute(
 573│         """
 574│         INSERT INTO snapshot_skipped_paths (
 575│             relative_path, skip_reason, detail, size_bytes, entry_type, source
 576│         ) VALUES (?, ?, ?, ?, ?, ?)
 577│         """,
 578│         (relative_path, skip_reason, detail, size_bytes, entry_type, source),
 579│     )
 580│ 
 581│ 
 582│ def insert_mapper_state(conn: sqlite3.Connection, relative_path: str, state: str, entry_type: str | None, is_visible: bool, source: str = "tree_checkbox"):
 583│     conn.execute(
 584│         """
 585│         INSERT OR REPLACE INTO snapshot_mapper_state (
 586│             relative_path, state, entry_type, is_visible, source
 587│         ) VALUES (?, ?, ?, ?, ?)
 588│         """,
 589│         (relative_path, state, entry_type, int(is_visible), source),
 590│     )
 591│ 
 592│ 
 593│ def insert_environment_hints(conn: sqlite3.Connection, hints: dict):
 594│     conn.executemany(
 595│         "INSERT OR REPLACE INTO snapshot_environment (key, value) VALUES (?, ?)",
 596│         [(key, "" if value is None else str(value)) for key, value in sorted(hints.items())],
 597│     )
 598│ 
 599│ 
 600│ def insert_snapshot_output(conn: sqlite3.Connection, name: str, output_type: str, content: str, external_path: str | None = None):
 601│     conn.execute(
 602│         """
 603│         INSERT OR REPLACE INTO snapshot_outputs (
 604│             name, output_type, content, created_at, external_path
 605│         ) VALUES (?, ?, ?, ?, ?)
 606│         """,
 607│         (name, output_type, content, now_iso(), external_path),
 608│     )
 609│ 
 610│ 
 611│ def insert_snapshot_error(conn: sqlite3.Connection, error: str, relative_path: str | None = None, context: str | None = None):
 612│     conn.execute(
 613│         """
 614│         INSERT INTO snapshot_errors (relative_path, error, context, created_at)
 615│         VALUES (?, ?, ?, ?)
 616│         """,
 617│         (relative_path, error, context, now_iso()),
 618│     )
 619│ # === [SECTION: SNAPSHOT_WRITERS] END ===
 620│ 
 621│ 
 622│ # === [SECTION: ENVIRONMENT_HINTS] BEGIN ===
 623│ def detect_environment_hints(root: Path) -> dict:
 624│     root = root.resolve()
 625│     hints = {
 626│         "platform": platform.platform(),
 627│         "python_version": sys.version.replace("\n", " "),
 628│         "snapshot_compiler_id": SNAPSHOT_COMPILER_ID,
 629│         "app_version": APP_VERSION,
 630│         "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
 631│         "source_root_name": root.name,
 632│         "source_root_absolute_path": str(root),
 633│         "has_requirements_txt": int((root / "requirements.txt").exists()),
 634│         "has_pyproject_toml": int((root / "pyproject.toml").exists()),
 635│         "has_package_json": int((root / "package.json").exists()),
 636│         "has_environment_yml": int((root / "environment.yml").exists()),
 637│         "has_poetry_lock": int((root / "poetry.lock").exists()),
 638│         "has_uv_lock": int((root / "uv.lock").exists()),
 639│         "has_pipfile": int((root / "Pipfile").exists()),
 640│         "has_dot_venv": int((root / ".venv").is_dir()),
 641│         "has_venv": int((root / "venv").is_dir()),
 642│     }
 643│ 
 644│     pyvenv_cfg = root / ".venv" / "pyvenv.cfg"
 645│     if pyvenv_cfg.exists() and pyvenv_cfg.is_file():
 646│         content, error = safe_read_text(pyvenv_cfg, max_bytes=20_000)
 647│         if content is not None:
 648│             for line in content.splitlines():
 649│                 if "=" not in line:
 650│                     continue
 651│                 key, value = line.split("=", 1)
 652│                 key = key.strip().lower().replace(" ", "_")
 653│                 value = value.strip()
 654│                 if key in {"home", "implementation", "version", "include-system-site-packages"}:
 655│                     hints[f"dot_venv_{key}"] = value
 656│         elif error:
 657│             hints["dot_venv_pyvenv_cfg_error"] = error
 658│ 
 659│     return hints
 660│ # === [SECTION: ENVIRONMENT_HINTS] END ===
 661│ 
 662│ 
 663│ # === [SECTION: MARKDOWN_PROJECTIONS] BEGIN ===
 664│ def markdown_language_for_path(path_text: str) -> str:
 665│     suffix = Path(path_text).suffix.lower()
 666│     return {
 667│         ".py": "python",
 668│         ".js": "javascript",
 669│         ".jsx": "jsx",
 670│         ".ts": "typescript",
 671│         ".tsx": "tsx",
 672│         ".json": "json",
 673│         ".md": "markdown",
 674│         ".txt": "text",
 675│         ".html": "html",
 676│         ".css": "css",
 677│         ".scss": "scss",
 678│         ".xml": "xml",
 679│         ".yml": "yaml",
 680│         ".yaml": "yaml",
 681│         ".toml": "toml",
 682│         ".ini": "ini",
 683│         ".bat": "bat",
 684│         ".ps1": "powershell",
 685│         ".sh": "bash",
 686│         ".sql": "sql",
 687│         ".c": "c",
 688│         ".cpp": "cpp",
 689│         ".h": "c",
 690│         ".hpp": "cpp",
 691│         ".java": "java",
 692│         ".rs": "rust",
 693│         ".go": "go",
 694│         ".rb": "ruby",
 695│         ".php": "php",
 696│     }.get(suffix, "text")
 697│ 
 698│ 
 699│ def build_project_tree_markdown(root: Path, snapshot_name: str, created_at: str, tree_rows: list[dict], folder_item_states: dict) -> str:
 700│     lines = [
 701│         "# Project Tree",
 702│         "",
 703│         "This standalone tree is intended as a lightweight project surface map. It can be shared without the full filedump so an agent can see the project shape, identify missing/unincluded files, and request specific follow-up uploads when needed.",
 704│         "",
 705│         "The SQLite snapshot remains the authoritative truth source for the manifest, selected file contents, skipped paths, exclusion rules, mapper state, and environment hints.",
 706│         "",
 707│         f"- Source root: `{root}`",
 708│         f"- Snapshot: `{snapshot_name}`",
 709│         f"- Generated: `{created_at}`",
 710│         "",
 711│         "```text",
 712│     ]
 713│ 
 714│     for row in tree_rows:
 715│         depth = int(row.get("depth", 0))
 716│         indent = "    " * depth
 717│         icon = "📁" if row.get("entry_type") == "dir" else "📄"
 718│         state = folder_item_states.get(str(row.get("path")), S_UNCHECKED)
 719│         checkbox = "[x]" if state == S_CHECKED else "[ ]"
 720│         suffix = "/" if row.get("entry_type") == "dir" else ""
 721│         name = row.get("name", "")
 722│         if row.get("relative_path") == ".":
 723│             name = f"{name}/"
 724│             suffix = ""
 725│         lines.append(f"{indent}{checkbox} {icon} {name}{suffix}")
 726│ 
 727│     lines.extend(["```", ""])
 728│     return "\n".join(lines)
 729│ 
 730│ 
 731│ def build_filedump_markdown(root: Path, snapshot_name: str, created_at: str, captured_files: list[dict]) -> str:
 732│     lines = [
 733│         "# Project Filedump",
 734│         "",
 735│         f"- Source root: `{root}`",
 736│         f"- Snapshot: `{snapshot_name}`",
 737│         f"- Generated: `{created_at}`",
 738│         f"- Captured files: `{len(captured_files)}`",
 739│         "",
 740│     ]
 741│ 
 742│     for item in captured_files:
 743│         rel = item.get("relative_path", "")
 744│         content = item.get("content", "")
 745│         language = markdown_language_for_path(rel)
 746│         lines.extend([
 747│             "---",
 748│             "",
 749│             f"## FILE: `{rel}`",
 750│             "",
 751│             f"```{language}",
 752│             content.rstrip(),
 753│             "```",
 754│             "",
 755│         ])
 756│ 
 757│     return "\n".join(lines)
 758│ # === [SECTION: MARKDOWN_PROJECTIONS] END ===
 759│ 
 760│ 
 761│ # === [SECTION: SNAPSHOT_COMPILER] BEGIN ===
 762│ def compile_snapshot(
 763│     root: Path,
 764│     output_dir: Path,
 765│     tree_rows: list[dict],
 766│     folder_item_states: dict,
 767│     policy: ExclusionPolicy,
 768│     scan_skipped_paths: list[dict],
 769│     stop_event=None,
 770│     log_callback=None,
 771│ ) -> Path:
 772│     root = root.resolve()
 773│     output_dir = ensure_dir(output_dir)
 774│     snapshot_path = output_dir / f"{root.name}_{SNAPSHOT_DB_SUFFIX}"
 775│ 
 776│     if snapshot_path.exists():
 777│         snapshot_path.unlink()
 778│ 
 779│     created_at = now_iso()
 780│     visible_rows = list(tree_rows)
 781│     skipped_paths = list(scan_skipped_paths)
 782│ 
 783│     if not visible_rows:
 784│         if log_callback:
 785│             log_callback("No cached tree rows found; scanning before snapshot compile.")
 786│         policy.load_gitignore(root)
 787│         visible_rows, skipped_paths = scan_project_tree(root, policy, stop_event=stop_event)
 788│ 
 789│     tree_entry_count = 0
 790│     mapper_state_count = 0
 791│     captured_file_count = 0
 792│     skipped_path_count = 0
 793│     error_count = 0
 794│     cancelled = False
 795│     captured_files_for_projection = []
 796│ 
 797│     def emit(message: str, level: str = "INFO"):
 798│         if log_callback:
 799│             log_callback(message, level)
 800│ 
 801│     with sqlite3.connect(snapshot_path) as conn:
 802│         create_snapshot_schema(conn)
 803│ 
 804│         base_metadata = {
 805│             "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
 806│             "snapshot_compiler_id": SNAPSHOT_COMPILER_ID,
 807│             "app_name": APP_NAME,
 808│             "app_version": APP_VERSION,
 809│             "source_root_name": root.name,
 810│             "source_root_absolute_path": str(root),
 811│             "compiled_at": created_at,
 812│             "respect_exclusions": int(policy.respect_exclusions),
 813│             "max_text_file_size_bytes": MAX_TEXT_FILE_SIZE_BYTES,
 814│             "text_encoding": TEXT_ENCODING,
 815│             "snapshot_filename": snapshot_path.name,
 816│         }
 817│         for key, value in base_metadata.items():
 818│             upsert_snapshot_metadata(conn, key, value)
 819│ 
 820│         insert_environment_hints(conn, detect_environment_hints(root))
 821│         insert_exclusion_rules(conn, policy.collect_rules())
 822│ 
 823│         for tree_order, row in enumerate(visible_rows):
 824│             if stop_event is not None and stop_event.is_set():
 825│                 cancelled = True
 826│                 break
 827│             abs_key = str(row["path"])
 828│             state = folder_item_states.get(abs_key, S_UNCHECKED)
 829│             is_selected = state == S_CHECKED
 830│             insert_project_tree_row(conn, tree_order, row, is_selected)
 831│             insert_mapper_state(conn, row["relative_path"], state, row["entry_type"], True)
 832│             tree_entry_count += 1
 833│             mapper_state_count += 1
 834│ 
 835│         for skipped in skipped_paths:
 836│             insert_skipped_path(
 837│                 conn,
 838│                 skipped.get("relative_path", ""),
 839│                 skipped.get("skip_reason", "unknown"),
 840│                 skipped.get("detail"),
 841│                 skipped.get("size_bytes"),
 842│                 skipped.get("entry_type"),
 843│                 source="scanner",
 844│             )
 845│             skipped_path_count += 1
 846│ 
 847│         for row in visible_rows:
 848│             if stop_event is not None and stop_event.is_set():
 849│                 cancelled = True
 850│                 break
 851│ 
 852│             if row["entry_type"] != "file":
 853│                 continue
 854│ 
 855│             abs_key = str(row["path"])
 856│             state = folder_item_states.get(abs_key, S_UNCHECKED)
 857│             if state != S_CHECKED:
 858│                 insert_skipped_path(
 859│                     conn,
 860│                     row["relative_path"],
 861│                     "unchecked_by_user",
 862│                     "Visible file was not selected in mapper tree.",
 863│                     row.get("size_bytes"),
 864│                     row.get("entry_type"),
 865│                     source="mapper_state",
 866│                 )
 867│                 skipped_path_count += 1
 868│                 continue
 869│ 
 870│             content, read_error = safe_read_text(row["path"], max_bytes=MAX_TEXT_FILE_SIZE_BYTES)
 871│             if read_error:
 872│                 insert_skipped_path(
 873│                     conn,
 874│                     row["relative_path"],
 875│                     read_error.split(":", 1)[0],
 876│                     read_error,
 877│                     row.get("size_bytes"),
 878│                     row.get("entry_type"),
 879│                     source="file_capture",
 880│                 )
 881│                 skipped_path_count += 1
 882│                 continue
 883│ 
 884│             try:
 885│                 insert_project_file(
 886│                     conn,
 887│                     captured_file_count,
 888│                     row["relative_path"],
 889│                     row.get("parent_relative_path"),
 890│                     int(row.get("size_bytes") or 0),
 891│                     content or "",
 892│                 )
 893│                 captured_files_for_projection.append({
 894│                     "relative_path": row["relative_path"],
 895│                     "content": content or "",
 896│                     "size_bytes": int(row.get("size_bytes") or 0),
 897│                 })
 898│                 captured_file_count += 1
 899│                 if captured_file_count % 10 == 0:
 900│                     emit(f"Captured {captured_file_count} text files...")
 901│             except Exception as exc:
 902│                 insert_snapshot_error(conn, str(exc), row["relative_path"], "insert_project_file")
 903│                 error_count += 1
 904│ 
 905│         upsert_snapshot_metadata(conn, "tree_entry_count", tree_entry_count)
 906│         upsert_snapshot_metadata(conn, "mapper_state_count", mapper_state_count)
 907│         upsert_snapshot_metadata(conn, "captured_file_count", captured_file_count)
 908│         upsert_snapshot_metadata(conn, "skipped_path_count", skipped_path_count)
 909│         upsert_snapshot_metadata(conn, "error_count", error_count)
 910│         upsert_snapshot_metadata(conn, "was_cancelled", int(cancelled))
 911│         upsert_snapshot_metadata(conn, "snapshot_completion_state", "partial" if cancelled else "complete")
 912│ 
 913│         project_tree_markdown = build_project_tree_markdown(
 914│             root=root,
 915│             snapshot_name=snapshot_path.name,
 916│             created_at=created_at,
 917│             tree_rows=visible_rows,
 918│             folder_item_states=folder_item_states,
 919│         )
 920│         project_filedump_markdown = build_filedump_markdown(
 921│             root=root,
 922│             snapshot_name=snapshot_path.name,
 923│             created_at=created_at,
 924│             captured_files=captured_files_for_projection,
 925│         )
 926│         insert_snapshot_output(conn, "project_tree_markdown", "markdown", project_tree_markdown)
 927│         insert_snapshot_output(conn, "project_filedump_markdown", "markdown", project_filedump_markdown)
 928│         upsert_snapshot_metadata(conn, "project_tree_markdown_generated", 1)
 929│         upsert_snapshot_metadata(conn, "project_filedump_markdown_generated", 1)
 930│ 
 931│         manifest_summary = (
 932│             "ProjectMapper SQLite snapshot containing project structure, selected text file contents, "
 933│             "mapper state, exclusion rules, skipped paths, environment hints, and snapshot metadata."
 934│         )
 935│         manifest_body = "\n".join([
 936│             "# ProjectMapper Snapshot Manifest",
 937│             "",
 938│             "## Purpose",
 939│             manifest_summary,
 940│             "",
 941│             "## Snapshot",
 942│             f"- Source root: `{root}`",
 943│             f"- Snapshot file: `{snapshot_path.name}`",
 944│             f"- Compiled at: `{created_at}`",
 945│             f"- Tree entries: `{tree_entry_count}`",
 946│             f"- Captured text files: `{captured_file_count}`",
 947│             f"- Skipped paths: `{skipped_path_count}`",
 948│             f"- Errors: `{error_count}`",
 949│             f"- Cancelled: `{int(cancelled)}`",
 950│             f"- Completion state: `{'partial' if cancelled else 'complete'}`",
 951│             "",
 952│             "## Core Tables",
 953│             "- `snapshot_metadata`: key/value facts about this snapshot.",
 954│             "- `snapshot_manifest`: this onboarding manifest.",
 955│             "- `project_tree`: visible project structure captured in traversal order.",
 956│             "- `project_files`: selected text-readable file contents.",
 957│             "- `snapshot_exclusion_rules`: active exclusion policy at compile time.",
 958│             "- `snapshot_skipped_paths`: files or folders omitted and why.",
 959│             "- `snapshot_mapper_state`: checkbox state from the mapper tree.",
 960│             "- `snapshot_environment`: local project environment hints.",
 961│             "- `snapshot_outputs`: generated projection artifacts, including tree and filedump markdown.",
 962│             "- `snapshot_errors`: non-fatal errors encountered during compilation.",
 963│             "",
 964│             "## Generated Outputs",
 965│             "- `snapshot_manifest_markdown`: this manifest as DB-embedded markdown, not a required standalone export.",
 966│             "- `project_tree_markdown`: lightweight project surface map export.",
 967│             "- `project_filedump_markdown`: captured text files as markdown.",
 968│             "- Combined tree + filedump markdown can be exported on demand from the UI.",
 969│             "",
 970│             "## Quick Start Queries",
 971│             "```sql",
 972│             "SELECT * FROM snapshot_manifest;",
 973│             "SELECT key, value FROM snapshot_metadata ORDER BY key;",
 974│             "SELECT relative_path, entry_type, is_selected FROM project_tree ORDER BY tree_order;",
 975│             "SELECT relative_path, substr(content, 1, 400) AS preview FROM project_files ORDER BY dump_order LIMIT 20;",
 976│             "SELECT * FROM snapshot_exclusion_rules ORDER BY source, pattern;",
 977│             "SELECT * FROM snapshot_skipped_paths ORDER BY skip_reason, relative_path;",
 978│             "SELECT * FROM snapshot_environment ORDER BY key;",
 979│             "SELECT name, output_type, length(content) AS chars FROM snapshot_outputs ORDER BY name;",
 980│             "SELECT content FROM snapshot_outputs WHERE name = 'project_tree_markdown';",
 981│             "```",
 982│         ])
 983│         conn.execute(
 984│             """
 985│             INSERT OR REPLACE INTO snapshot_manifest (
 986│                 id, manifest_version, title, summary, contents_markdown, created_at
 987│             ) VALUES (?, ?, ?, ?, ?, ?)
 988│             """,
 989│             (
 990│                 1,
 991│                 SNAPSHOT_SCHEMA_VERSION,
 992│                 "ProjectMapper Snapshot Manifest",
 993│                 manifest_summary,
 994│                 manifest_body,
 995│                 created_at,
 996│             ),
 997│         )
 998│         insert_snapshot_output(conn, "snapshot_manifest_markdown", "markdown", manifest_body)
 999│         conn.commit()
1000│ 
1001│     emit(
1002│         f"Snapshot compiled: {snapshot_path.name} ({tree_entry_count} tree entries, {captured_file_count} files, {skipped_path_count} skipped)"
1003│     )
1004│     return snapshot_path
1005│ # === [SECTION: SNAPSHOT_COMPILER] END ===
1006│ 
1007│ 
1008│ # === [SECTION: PROGRESS_POPUP] BEGIN ===
1009│ class ProgressPopup:
1010│     def __init__(self, parent, title="Processing", on_cancel=None):
1011│         self.top = tk.Toplevel(parent)
1012│         self.top.title(title)
1013│         self.top.geometry("560x320")
1014│         self.top.configure(bg=THEME["panel_bg"])
1015│         self.top.transient(parent)
1016│         self.top.grab_set()
1017│         self.top.protocol("WM_DELETE_WINDOW", self._on_close_attempt)
1018│ 
1019│         self.on_cancel = on_cancel
1020│         self.is_cancelled = False
1021│ 
1022│         tk.Label(
1023│             self.top,
1024│             text=f"{title}...",
1025│             fg=THEME["text"],
1026│             bg=THEME["panel_bg"],
1027│             font=("Arial", 12, "bold"),
1028│         ).pack(pady=10)
1029│ 
1030│         self.log_display = scrolledtext.ScrolledText(
1031│             self.top,
1032│             height=10,
1033│             bg=THEME["log_bg"],
1034│             fg=THEME["log_accent"],
1035│             insertbackground=THEME["log_text"],
1036│             font=("Consolas", 9),
1037│         )
1038│         self.log_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
1039│ 
1040│         self.cancel_btn = tk.Button(
1041│             self.top,
1042│             text="CANCEL OPERATION",
1043│             bg=THEME["danger"],
1044│             fg=THEME["text"],
1045│             activebackground=THEME["danger_hover"],
1046│             activeforeground=THEME["text"],
1047│             font=("Arial", 10, "bold"),
1048│             command=self.trigger_cancel,
1049│         )
1050│         self.cancel_btn.pack(pady=10)
1051│ 
1052│     def update_text(self, text):
1053│         self.log_display.insert(tk.END, text + "\n")
1054│         self.log_display.see(tk.END)
1055│ 
1056│     def trigger_cancel(self):
1057│         self.is_cancelled = True
1058│         self.update_text("!!! CANCELLATION REQUESTED - STOPPING !!!")
1059│         self.cancel_btn.config(state=tk.DISABLED, text="Stopping...")
1060│         if self.on_cancel:
1061│             self.on_cancel()
1062│ 
1063│     def _on_close_attempt(self):
1064│         if not self.is_cancelled:
1065│             self.trigger_cancel()
1066│ 
1067│     def close(self):
1068│         try:
1069│             self.top.destroy()
1070│         except tk.TclError:
1071│             pass
1072│ # === [SECTION: PROGRESS_POPUP] END ===
1073│ 
1074│ 
1075│ # === [SECTION: TK_APP_INIT] BEGIN ===
1076│ class ProjectMapperApp:
1077│     def __init__(self, root: tk.Tk):
1078│         self.root = root
1079│         self.gui_queue = queue.Queue()
1080│         self.running_tasks = set()
1081│         self.stop_event = threading.Event()
1082│         self.widgets = {}
1083│         self.current_progress_popup = None
1084│         self.selected_root = DEFAULT_ROOT_DIR
1085│         self.latest_snapshot_path = None
1086│         self.state_lock = threading.RLock()
1087│         self.folder_item_states = {}
1088│         self.tree_rows = []
1089│         self.scan_skipped_paths = []
1090│         self.exclusion_policy = ExclusionPolicy()
1091│         self.icon_imgs = {}
1092│         self._create_tree_icons()
1093│ 
1094│         self._setup_styles()
1095│         self._setup_ui()
1096│         self.process_gui_queue()
1097│         self._activity_blinker()
1098│         self.log_message("Snapshot Compiler loaded. Choose a project root, curate the tree, then compile a SQLite snapshot.")
1099│         self.root.after(250, self.request_rescan_tree_silent)
1100│ 
1101│             def _create_tree_icons(self):
1102│         img_unchecked = tk.PhotoImage(width=14, height=14)
1103│         img_unchecked.put((THEME["checkbox_border"],), to=(0, 0, 14, 1))
1104│         img_unchecked.put((THEME["checkbox_border"],), to=(0, 13, 14, 14))
1105│         img_unchecked.put((THEME["checkbox_border"],), to=(0, 0, 1, 14))
1106│         img_unchecked.put((THEME["checkbox_border"],), to=(13, 0, 14, 14))
1107│         self.icon_imgs[S_UNCHECKED] = img_unchecked
1108│ 
1109│         img_checked = tk.PhotoImage(width=14, height=14)
1110│         img_checked.put((THEME["checkbox_checked"],), to=(0, 0, 14, 14))
1111│         img_checked.put(("#FFFFFF",), to=(3, 7, 6, 10))
1112│         img_checked.put(("#FFFFFF",), to=(6, 5, 11, 8))
1113│         self.icon_imgs[S_CHECKED] = img_checked
1114│         # === [SECTION: TK_APP_INIT] END ===
1115│ 
1116│ 
1117│ # === [SECTION: TK_STYLES] BEGIN ===
1118│     def _setup_styles(self):
1119│         style = ttk.Style()
1120│         if "clam" in style.theme_names():
1121│             style.theme_use("clam")
1122│ 
1123│         self.default_ui_font = "Arial"
1124│         try:
1125│             if "DejaVu Sans" in tkFont.families():
1126│                 self.default_ui_font = "DejaVu Sans"
1127│         except tk.TclError:
1128│             pass
1129│ 
1130│         style.configure(
1131│             "Treeview",
1132│             background=THEME["tree_bg"],
1133│             foreground=THEME["text"],
1134│             fieldbackground=THEME["tree_bg"],
1135│             borderwidth=0,
1136│             font=(self.default_ui_font, 10),
1137│             rowheight=24,
1138│         )
1139│         style.configure(
1140│             "Treeview.Heading",
1141│             background=THEME["heading_bg"],
1142│             foreground=THEME["heading_text"],
1143│             relief=tk.FLAT,
1144│         )
1145│ # === [SECTION: TK_STYLES] END ===
1146│ 
1147│ 
1148│ # === [SECTION: TK_UI_LAYOUT] BEGIN ===
1149│     def _setup_ui(self):
1150│         self.root.title(f"{APP_NAME} v{APP_VERSION}")
1151│         self.root.configure(bg=THEME["app_bg"])
1152│         self.root.geometry("1200x850")
1153│ 
1154│         top_frame = tk.Frame(self.root, bg=THEME["panel_bg"])
1155│         top_frame.pack(fill=tk.X, padx=10, pady=8)
1156│ 
1157│         tk.Label(top_frame, text="Project Root:", bg=THEME["panel_bg"], fg=THEME["text"]).pack(side=tk.LEFT)
1158│         self.widgets["selected_root_var"] = tk.StringVar(value=str(DEFAULT_ROOT_DIR))
1159│         self.widgets["project_path_entry"] = tk.Entry(
1160│             top_frame,
1161│             textvariable=self.widgets["selected_root_var"],
1162│             bg=THEME["field_bg"],
1163│             fg=THEME["field_text"],
1164│             insertbackground=THEME["field_text"],
1165│             relief=tk.FLAT,
1166│         )
1167│         self.widgets["project_path_entry"].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
1168│         self.widgets["project_path_entry"].bind("<Return>", lambda _event: self.choose_root_from_entry())
1169│ 
1170│         self._make_button(top_frame, "Choose...", self.choose_root_dialog, THEME["secondary"], THEME["secondary_hover"]).pack(side=tk.RIGHT)
1171│         self._make_button(top_frame, "↑", self.navigate_to_parent, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.RIGHT, padx=5)
1172│ 
1173│         paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
1174│         paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
1175│ 
1176│         tree_frame = tk.Frame(paned, bg=THEME["panel_bg"])
1177│         self.widgets["folder_tree"] = ttk.Treeview(
1178│             tree_frame,
1179│             show="tree headings",
1180│             columns=("nav_up", "nav_down", "size"),
1181│             selectmode="browse",
1182│         )
1183│         self.widgets["folder_tree"].heading("#0", text="Explorer")
1184│         self.widgets["folder_tree"].heading("nav_up", text="↑")
1185│         self.widgets["folder_tree"].heading("nav_down", text="↓")
1186│         self.widgets["folder_tree"].heading("size", text="Size")
1187│         self.widgets["folder_tree"].column("#0", width=760)
1188│         self.widgets["folder_tree"].column("nav_up", width=34, anchor="center", stretch=False)
1189│         self.widgets["folder_tree"].column("nav_down", width=34, anchor="center", stretch=False)
1190│         self.widgets["folder_tree"].column("size", width=120, anchor="e", stretch=False)
1191│         self.widgets["folder_tree"].insert("", "end", text="Tree scanner pending", values=("", "", ""))
1192│ 
1193│         vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.widgets["folder_tree"].yview)
1194│         self.widgets["folder_tree"].configure(yscrollcommand=vsb.set)
1195│         self.widgets["folder_tree"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
1196│         vsb.pack(side=tk.RIGHT, fill=tk.Y)
1197│         self.widgets["folder_tree"].bind("<ButtonRelease-1>", self.on_tree_item_click)
1198│         paned.add(tree_frame, weight=3)
1199│ 
1200│         action_frame = tk.Frame(paned, bg=THEME["panel_bg"])
1201│         btn_row = tk.Frame(action_frame, bg=THEME["panel_bg"])
1202│         btn_row.pack(fill=tk.X, padx=5, pady=6)
1203│ 
1204│         self._make_button(btn_row, "Compile Snapshot", self.compile_snapshot_placeholder, THEME["accent"], THEME["accent_hover"], bold=True).pack(side=tk.LEFT, padx=4)
1205│         self._make_button(btn_row, "Export Tree MD", self.export_tree_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
1206│         self._make_button(btn_row, "Export Filedump MD", self.export_filedump_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
1207│         self._make_button(btn_row, "Export Tree+Dump MD", self.export_combined_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
1208│         self._make_button(btn_row, "Open Output Folder", self.open_output_folder, THEME["success"], THEME["success_hover"]).pack(side=tk.RIGHT, padx=4)
1209│ 
1210│         control_row = tk.Frame(action_frame, bg=THEME["panel_bg"])
1211│         control_row.pack(fill=tk.X, padx=5, pady=2)
1212│         self.widgets["respect_exclusions"] = tk.BooleanVar(value=True)
1213│         tk.Checkbutton(
1214│             control_row,
1215│             text="Respect .gitignore + exclusions",
1216│             variable=self.widgets["respect_exclusions"],
1217│             command=self.apply_exclusion_settings,
1218│             bg=THEME["panel_bg"],
1219│             fg=THEME["text"],
1220│             selectcolor=THEME["tree_bg"],
1221│             activebackground=THEME["panel_bg"],
1222│             activeforeground=THEME["text"],
1223│         ).pack(side=tk.LEFT, padx=6)
1224│         self.widgets["include_tree_in_filedump"] = tk.BooleanVar(value=False)
1225│         tk.Checkbutton(
1226│             control_row,
1227│             text="Tree in filedump export",
1228│             variable=self.widgets["include_tree_in_filedump"],
1229│             bg=THEME["panel_bg"],
1230│             fg=THEME["text"],
1231│             selectcolor=THEME["tree_bg"],
1232│             activebackground=THEME["panel_bg"],
1233│             activeforeground=THEME["text"],
1234│         ).pack(side=tk.LEFT, padx=6)
1235│         self._make_button(control_row, "All", lambda: self.set_global_selection(S_CHECKED), THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=2)
1236│         self._make_button(control_row, "None", lambda: self.set_global_selection(S_UNCHECKED), THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=2)
1237│         tk.Label(control_row, text="Excl. Pattern:", bg=THEME["panel_bg"], fg=THEME["muted_text"]).pack(side=tk.RIGHT, padx=4)
1238│         self.widgets["exclusion_entry"] = tk.Entry(
1239│             control_row,
1240│             bg=THEME["field_bg_alt"],
1241│             fg=THEME["field_text"],
1242│             insertbackground=THEME["field_text"],
1243│             width=22,
1244│             relief=tk.FLAT,
1245│         )
1246│         self.widgets["exclusion_entry"].pack(side=tk.RIGHT, padx=4)
1247│         self._make_button(control_row, "Add", self.add_exclusion_from_entry, THEME["accent"], THEME["accent_hover"]).pack(side=tk.RIGHT, padx=2)
1248│         self._make_button(control_row, "Exclusions", self.manage_exclusions_popup, THEME["success"], THEME["success_hover"]).pack(side=tk.RIGHT, padx=2)
1249│         self._make_button(control_row, "Rescan", self.request_rescan_tree, THEME["secondary"], THEME["secondary_hover"]).pack(side=tk.RIGHT, padx=2)
1250│ 
1251│         self.widgets["log_box"] = scrolledtext.ScrolledText(
1252│             action_frame,
1253│             bg=THEME["log_bg"],
1254│             fg=THEME["log_text"],
1255│             insertbackground=THEME["log_text"],
1256│             font=("Consolas", 9),
1257│             state=tk.DISABLED,
1258│             height=10,
1259│         )
1260│         self.widgets["log_box"].pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
1261│         paned.add(action_frame, weight=1)
1262│ 
1263│         self.widgets["status_var"] = tk.StringVar(value="Ready.")
1264│         self.widgets["status_bar"] = tk.Label(
1265│             self.root,
1266│             textvariable=self.widgets["status_var"],
1267│             bg=THEME["status_bg"],
1268│             fg=THEME["status_text"],
1269│             anchor="w",
1270│         )
1271│         self.widgets["status_bar"].pack(fill=tk.X, side=tk.BOTTOM)
1272│ 
1273│     def _make_button(self, parent, text, command, bg, active_bg, bold=False):
1274│         return tk.Button(
1275│             parent,
1276│             text=text,
1277│             command=command,
1278│             bg=bg,
1279│             fg=THEME["text"],
1280│             activebackground=active_bg,
1281│             activeforeground=THEME["text"],
1282│             font=("Arial", 10, "bold" if bold else "normal"),
1283│             relief=tk.RAISED,
1284│             padx=10,
1285│             pady=6,
1286│         )
1287│ # === [SECTION: TK_UI_LAYOUT] END ===
1288│ 
1289│ 
1290│ # === [SECTION: TK_TREE_BEHAVIOR] BEGIN ===
1291│     def request_rescan_tree(self):
1292│         self.run_threaded_action(self._scan_tree_impl, "scan_tree", use_popup=True)
1293│ 
1294│     def request_rescan_tree_silent(self):
1295│         self.run_threaded_action(self._scan_tree_impl, "scan_tree", use_popup=False)
1296│ 
1297│     def _scan_tree_impl(self):
1298│         root = self.selected_root if self.selected_root and self.selected_root.is_dir() else None
1299│         if root is None:
1300│             self.schedule_log_message("Cannot scan: no valid project root.", "ERROR")
1301│             return
1302│         self.exclusion_policy.respect_exclusions = bool(self.widgets.get("respect_exclusions").get()) if self.widgets.get("respect_exclusions") else True
1303│         self.exclusion_policy.load_gitignore(root)
1304│         self.schedule_log_message(f"Scanning project tree: {root}")
1305│         rows, skipped = scan_project_tree(root, self.exclusion_policy, stop_event=self.stop_event)
1306│         if self.stop_event.is_set():
1307│             self.schedule_log_message("Tree scan cancelled.", "WARNING")
1308│             return
1309│         with self.state_lock:
1310│             self.tree_rows = rows
1311│             self.scan_skipped_paths = skipped
1312│             valid_paths = {str(row["path"]) for row in rows}
1313│             self.folder_item_states = {key: value for key, value in self.folder_item_states.items() if key in valid_paths}
1314│             for row in rows:
1315│                 key = str(row["path"])
1316│                 if key not in self.folder_item_states:
1317│                     parent = row.get("parent")
1318│                     parent_state = self.folder_item_states.get(str(parent), S_CHECKED) if parent else S_CHECKED
1319│                     self.folder_item_states[key] = parent_state
1320│         self.gui_queue.put(lambda: self.populate_tree(rows))
1321│         self.schedule_log_message(f"Scan complete: {len(rows)} visible entries, {len(skipped)} skipped entries.")
1322│ 
1323│     def populate_tree(self, rows: list[dict]):
1324│         tree = self.widgets["folder_tree"]
1325│         tree.delete(*tree.get_children())
1326│         for row in rows:
1327│             iid = str(row["path"])
1328│             parent = "" if row["parent"] is None else str(row["parent"])
1329│             state = self.folder_item_states.get(iid, S_UNCHECKED)
1330│             prefix = "📁" if row["entry_type"] == "dir" else "📄"
1331│             size_text = "" if row["size_bytes"] is None else format_display_size(row["size_bytes"])
1332│             is_dir = row["entry_type"] == "dir"
1333│             tree.insert(
1334│                 parent,
1335│                 "end",
1336│                 iid=iid,
1337│                 text=f"{prefix} {row['name']}",
1338│                 image=self.icon_imgs.get(state, self.icon_imgs[S_UNCHECKED]),
1339│                 values=("↑" if is_dir else "", "↓" if is_dir else "", size_text),
1340│                 open=row["depth"] < 2,
1341│             )
1342│         self.refresh_tree_visuals()
1343│ 
1344│     def refresh_tree_visuals(self, start_iid: str | None = None):
1345│         tree = self.widgets["folder_tree"]
1346│ 
1347│         def refresh_one(iid: str):
1348│             if not tree.exists(iid):
1349│                 return
1350│             state = self.folder_item_states.get(iid, S_UNCHECKED)
1351│             tree.item(iid, image=self.icon_imgs.get(state, self.icon_imgs[S_UNCHECKED]))
1352│             path = Path(iid)
1353│             if path.is_dir():
1354│                 tree.set(iid, "nav_up", "↑")
1355│                 tree.set(iid, "nav_down", "↓")
1356│             else:
1357│                 tree.set(iid, "nav_up", "")
1358│                 tree.set(iid, "nav_down", "")
1359│             for child in tree.get_children(iid):
1360│                 refresh_one(child)
1361│ 
1362│         if start_iid:
1363│             refresh_one(start_iid)
1364│         else:
1365│             for child in tree.get_children(""):
1366│                 refresh_one(child)
1367│ 
1368│     def on_tree_item_click(self, event):
1369│         tree = event.widget
1370│         iid = tree.identify_row(event.y)
1371│         if not iid:
1372│             return
1373│ 
1374│         column = tree.identify_column(event.x)
1375│         element = tree.identify("element", event.x, event.y) or ""
1376│         path = Path(iid)
1377│ 
1378│         if column == "#1" and path.is_dir():
1379│             self.navigate_tree_to_path(path.parent)
1380│             return
1381│ 
1382│         if column == "#2" and path.is_dir():
1383│             self.navigate_tree_to_path(path)
1384│             return
1385│ 
1386│         if column == "#0" or "image" in element:
1387│             self.toggle_tree_item(iid)
1388│ 
1389│     def toggle_tree_item(self, iid: str):
1390│         with self.state_lock:
1391│             current = self.folder_item_states.get(iid, S_UNCHECKED)
1392│             new_state = S_CHECKED if current != S_CHECKED else S_UNCHECKED
1393│             self._set_tree_state_recursive(iid, new_state)
1394│         self.refresh_tree_visuals(iid)
1395│ 
1396│     def _set_tree_state_recursive(self, iid: str, state: str):
1397│         tree = self.widgets["folder_tree"]
1398│         self.folder_item_states[iid] = state
1399│         for child in tree.get_children(iid):
1400│             self._set_tree_state_recursive(child, state)
1401│ 
1402│     def set_global_selection(self, state: str):
1403│         tree = self.widgets.get("folder_tree")
1404│         if tree is None:
1405│             return
1406│         with self.state_lock:
1407│             for child in tree.get_children(""):
1408│                 self._set_tree_state_recursive(child, state)
1409│         self.refresh_tree_visuals()
1410│         self.log_message(f"Set visible tree selection to: {state}")
1411│ 
1412│     def is_selected(self, path: Path) -> bool:
1413│         try:
1414│             key = str(path.resolve())
1415│         except Exception:
1416│             return False
1417│         with self.state_lock:
1418│             return self.folder_item_states.get(key, S_UNCHECKED) == S_CHECKED
1419│ # === [SECTION: TK_TREE_BEHAVIOR] END ===
1420│ 
1421│ 
1422│ # === [SECTION: TK_EXCLUSION_UI] BEGIN ===
1423│     def apply_exclusion_settings(self):
1424│         var = self.widgets.get("respect_exclusions")
1425│         self.exclusion_policy.respect_exclusions = bool(var.get()) if var else True
1426│         self.log_message(f"Respect exclusions: {self.exclusion_policy.respect_exclusions}")
1427│ 
1428│     def add_exclusion_from_entry(self):
1429│         entry = self.widgets.get("exclusion_entry")
1430│         if entry is None:
1431│             return
1432│         value = entry.get().strip()
1433│         if not value:
1434│             return
1435│         self.exclusion_policy.dynamic_patterns.add(value)
1436│         entry.delete(0, tk.END)
1437│         self.log_message(f"Added exclusion pattern: {value}")
1438│         self.request_rescan_tree()
1439│ 
1440│     def manage_exclusions_popup(self):
1441│         top = tk.Toplevel(self.root)
1442│         top.title("Exclusion Patterns")
1443│         top.configure(bg=THEME["panel_bg"])
1444│         top.geometry("420x320")
1445│ 
1446│         tk.Label(
1447│             top,
1448│             text="Dynamic user exclusion patterns",
1449│             bg=THEME["panel_bg"],
1450│             fg=THEME["text"],
1451│             font=("Arial", 11, "bold"),
1452│         ).pack(pady=8)
1453│ 
1454│         listbox = tk.Listbox(
1455│             top,
1456│             bg=THEME["tree_bg"],
1457│             fg=THEME["text"],
1458│             selectbackground=THEME["selection"],
1459│             selectforeground=THEME["heading_text"],
1460│         )
1461│         listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
1462│         for pattern in sorted(self.exclusion_policy.dynamic_patterns):
1463│             listbox.insert(tk.END, pattern)
1464│ 
1465│         def remove_selected():
1466│             selection = listbox.curselection()
1467│             if not selection:
1468│                 return
1469│             pattern = listbox.get(selection[0])
1470│             self.exclusion_policy.dynamic_patterns.discard(pattern)
1471│             top.destroy()
1472│             self.log_message(f"Removed exclusion pattern: {pattern}")
1473│             self.request_rescan_tree()
1474│ 
1475│         self._make_button(top, "Remove Selected", remove_selected, THEME["danger"], THEME["danger_hover"]).pack(pady=8)
1476│ # === [SECTION: TK_EXCLUSION_UI] END ===
1477│ 
1478│ 
1479│ # === [SECTION: TK_ACTIONS] BEGIN ===
1480│     def navigate_tree_to_path(self, target_path: Path):
1481│         try:
1482│             target = target_path.resolve()
1483│         except Exception:
1484│             return
1485│         if not target.is_dir():
1486│             return
1487│         self.widgets["selected_root_var"].set(str(target))
1488│         self.selected_root = target
1489│         self.log_message(f"Project root set: {self.selected_root}")
1490│         self.request_rescan_tree()
1491│ 
1492│     def navigate_to_parent(self):
1493│         root = self.selected_root if self.selected_root and self.selected_root.is_dir() else None
1494│         if root is None:
1495│             return
1496│         parent = root.parent
1497│         if parent != root and parent.is_dir():
1498│             self.navigate_tree_to_path(parent)
1499│ 
1500│     def choose_root_dialog(self):
1501│         selected = filedialog.askdirectory()
1502│         if selected:
1503│             self.widgets["selected_root_var"].set(selected)
1504│             self.choose_root_from_entry()
1505│ 
1506│     def choose_root_from_entry(self):
1507│         candidate = Path(self.widgets["selected_root_var"].get()).expanduser()
1508│         if not candidate.is_dir():
1509│             messagebox.showerror("Invalid Project Root", f"Not a directory:\n{candidate}")
1510│             return
1511│         self.selected_root = candidate.resolve()
1512│         self.log_message(f"Project root set: {self.selected_root}")
1513│         self.request_rescan_tree()
1514│ 
1515│     def get_output_dir(self) -> Path:
1516│         root = self.selected_root if self.selected_root and self.selected_root.is_dir() else DEFAULT_ROOT_DIR
1517│         return ensure_dir(root / OUTPUT_ROOT_NAME)
1518│ 
1519│     def compile_snapshot_placeholder(self):
1520│         self.run_threaded_action(self._compile_snapshot_impl, "compile_snapshot", use_popup=True)
1521│ 
1522│     def _compile_snapshot_impl(self):
1523│         root = self.selected_root if self.selected_root and self.selected_root.is_dir() else None
1524│         if root is None:
1525│             self.schedule_log_message("Cannot compile snapshot: no valid project root.", "ERROR")
1526│             return
1527│ 
1528│         self.exclusion_policy.respect_exclusions = bool(self.widgets.get("respect_exclusions").get()) if self.widgets.get("respect_exclusions") else True
1529│         self.exclusion_policy.load_gitignore(root)
1530│ 
1531│         with self.state_lock:
1532│             tree_rows = list(self.tree_rows)
1533│             folder_item_states = dict(self.folder_item_states)
1534│             scan_skipped_paths = list(self.scan_skipped_paths)
1535│ 
1536│         snapshot_path = compile_snapshot(
1537│             root=root,
1538│             output_dir=self.get_output_dir(),
1539│             tree_rows=tree_rows,
1540│             folder_item_states=folder_item_states,
1541│             policy=self.exclusion_policy,
1542│             scan_skipped_paths=scan_skipped_paths,
1543│             stop_event=self.stop_event,
1544│             log_callback=self.schedule_log_message,
1545│         )
1546│         self.latest_snapshot_path = snapshot_path
1547│         self.schedule_log_message(f"Latest snapshot set: {snapshot_path}")
1548│         self.schedule_log_message("Markdown projections are stored in the DB. Export Tree, Filedump, or Combined MD when ready. Manifest remains embedded in the SQLite snapshot.")
1549│         self.schedule_log_message(f"Output folder: {self.get_output_dir()}")
1550│ 
1551│     def _require_latest_snapshot(self) -> Path | None:
1552│         if self.latest_snapshot_path and Path(self.latest_snapshot_path).exists():
1553│             return Path(self.latest_snapshot_path)
1554│ 
1555│         root = self.selected_root if self.selected_root and self.selected_root.is_dir() else None
1556│         if root is not None:
1557│             candidate = self.get_output_dir() / f"{root.name}_{SNAPSHOT_DB_SUFFIX}"
1558│             if candidate.exists():
1559│                 self.latest_snapshot_path = candidate
1560│                 return candidate
1561│ 
1562│         self.log_message("No snapshot DB found yet. Compile Snapshot DB first.", "WARNING")
1563│         return None
1564│ 
1565│     def export_snapshot_output(self, output_name: str, suffix: str, content_override: str | None = None):
1566│         snapshot_path = self._require_latest_snapshot()
1567│         if snapshot_path is None:
1568│             return
1569│         root = self.selected_root if self.selected_root and self.selected_root.is_dir() else DEFAULT_ROOT_DIR
1570│         out_path = self.get_output_dir() / snapshot_output_filename(root, suffix)
1571│         try:
1572│             content = content_override if content_override is not None else load_snapshot_output(snapshot_path, output_name)
1573│             write_text_file(out_path, content)
1574│             self.log_message(f"Exported {output_name}: {out_path}")
1575│         except Exception as exc:
1576│             self.log_message(f"Failed to export {output_name}: {exc}", "ERROR")
1577│ 
1578│     def export_tree_markdown(self):
1579│         self.export_snapshot_output("project_tree_markdown", TREE_MD_SUFFIX)
1580│ 
1581│     def export_filedump_markdown(self):
1582│         snapshot_path = self._require_latest_snapshot()
1583│         if snapshot_path is None:
1584│             return
1585│         try:
1586│             filedump_markdown = load_snapshot_output(snapshot_path, "project_filedump_markdown")
1587│             include_tree = bool(self.widgets.get("include_tree_in_filedump").get()) if self.widgets.get("include_tree_in_filedump") else False
1588│             if include_tree:
1589│                 tree_markdown = load_snapshot_output(snapshot_path, "project_tree_markdown")
1590│                 filedump_markdown = combine_tree_and_filedump_markdown(tree_markdown, filedump_markdown)
1591│             self.export_snapshot_output("project_filedump_markdown", FILEDUMP_MD_SUFFIX, content_override=filedump_markdown)
1592│         except Exception as exc:
1593│             self.log_message(f"Failed to export filedump markdown: {exc}", "ERROR")
1594│ 
1595│     def export_combined_markdown(self):
1596│         snapshot_path = self._require_latest_snapshot()
1597│         if snapshot_path is None:
1598│             return
1599│         try:
1600│             tree_markdown = load_snapshot_output(snapshot_path, "project_tree_markdown")
1601│             filedump_markdown = load_snapshot_output(snapshot_path, "project_filedump_markdown")
1602│             combined = combine_tree_and_filedump_markdown(tree_markdown, filedump_markdown)
1603│             self.export_snapshot_output("project_tree_and_filedump_markdown", COMBINED_MD_SUFFIX, content_override=combined)
1604│         except Exception as exc:
1605│             self.log_message(f"Failed to export combined markdown: {exc}", "ERROR")
1606│ 
1607│     def export_manifest_markdown(self):
1608│         self.export_snapshot_output("snapshot_manifest_markdown", MANIFEST_MD_SUFFIX)
1609│ 
1610│     def pending_projection_notice(self):
1611│         self.log_message("Projection export is available after compiling a snapshot DB.", "WARNING")
1612│ 
1613│     def open_output_folder(self):
1614│         out_dir = self.get_output_dir()
1615│         try:
1616│             if platform.system() == "Windows":
1617│                 os.startfile(out_dir)
1618│             elif platform.system() == "Darwin":
1619│                 subprocess.run(["open", str(out_dir)], check=False)
1620│             else:
1621│                 subprocess.run(["xdg-open", str(out_dir)], check=False)
1622│             self.log_message(f"Opened output folder: {out_dir}")
1623│         except Exception as exc:
1624│             self.log_message(f"Could not open output folder: {exc}", "ERROR")
1625│ # === [SECTION: TK_ACTIONS] END ===
1626│ 
1627│ 
1628│ # === [SECTION: THREADING_AND_LOGGING] BEGIN ===
1629│     def _activity_blinker(self):
1630│         if self.running_tasks:
1631│             task_names = ", ".join(sorted(self.running_tasks))
1632│             self.widgets["status_var"].set(f"[ACTIVE] {task_names}")
1633│             current_color = self.widgets["status_bar"].cget("bg")
1634│             next_color = THEME["panel_alt_bg"] if current_color == THEME["status_bg"] else THEME["status_bg"]
1635│             self.widgets["status_bar"].config(bg=next_color)
1636│         else:
1637│             self.widgets["status_bar"].config(bg=THEME["status_bg"])
1638│         self.root.after(500, self._activity_blinker)
1639│ 
1640│     def cancel_current_operations(self):
1641│         self.stop_event.set()
1642│         self.log_message("Stop signal sent to active task.", "WARNING")
1643│ 
1644│     def run_threaded_action(self, target_function, task_id: str, use_popup=False):
1645│         if task_id in self.running_tasks:
1646│             self.log_message(f"Task already running: {task_id}", "WARNING")
1647│             return
1648│ 
1649│         if use_popup:
1650│             self.current_progress_popup = ProgressPopup(self.root, title=f"Working: {task_id}", on_cancel=self.cancel_current_operations)
1651│ 
1652│         def runner():
1653│             self.running_tasks.add(task_id)
1654│             self.stop_event.clear()
1655│             try:
1656│                 target_function()
1657│             except Exception as exc:
1658│                 self.schedule_log_message(f"CRASH in {task_id}: {exc}\n{traceback.format_exc()}", "CRITICAL")
1659│             finally:
1660│                 self.running_tasks.discard(task_id)
1661│                 if use_popup and self.current_progress_popup:
1662│                     popup = self.current_progress_popup
1663│                     self.current_progress_popup = None
1664│                     self.gui_queue.put(popup.close)
1665│                 self.schedule_log_message(f"Task finished: {task_id}")
1666│ 
1667│         threading.Thread(target=runner, daemon=True).start()
1668│ 
1669│     def schedule_log_message(self, msg: str, level: str = "INFO"):
1670│         self.gui_queue.put(lambda: self.log_message(msg, level))
1671│         if self.current_progress_popup:
1672│             self.gui_queue.put(lambda: self.current_progress_popup.update_text(f"[{level}] {msg}") if self.current_progress_popup else None)
1673│ 
1674│     def log_message(self, msg: str, level: str = "INFO"):
1675│         ts = datetime.now().strftime("[%H:%M:%S]")
1676│         full_msg = f"{ts} [{level}] {msg}\n"
1677│         log_box = self.widgets.get("log_box")
1678│         if log_box:
1679│             log_box.config(state=tk.NORMAL)
1680│             log_box.insert(tk.END, full_msg)
1681│             log_box.config(state=tk.DISABLED)
1682│             log_box.see(tk.END)
1683│         status = self.widgets.get("status_var")
1684│         if status:
1685│             status.set(f"{ts} {msg}")
1686│ 
1687│     def process_gui_queue(self):
1688│         while True:
1689│             try:
1690│                 callback = self.gui_queue.get_nowait()
1691│             except queue.Empty:
1692│                 break
1693│             try:
1694│                 callback()
1695│             except Exception:
1696│                 pass
1697│         self.root.after(100, self.process_gui_queue)
1698│ # === [SECTION: THREADING_AND_LOGGING] END ===
1699│ 
1700│ 
1701│ # === [SECTION: CLI] BEGIN ===
1702│ # minimal CLI:
1703│ #   optional compile snapshot from path later
1704│ #   simple launch GUI for now
1705│ # === [SECTION: CLI] END ===
1706│ 
1707│ 
1708│ # === [SECTION: ENTRYPOINT] BEGIN ===
1709│ def run_gui():
1710│     root = tk.Tk()
1711│     ProjectMapperApp(root)
1712│     root.mainloop()
1713│ 
1714│ 
1715│ def main():
1716│     run_gui()
1717│ 
1718│ 
1719│ if __name__ == "__main__":
1720│     main()
1721│ # === [SECTION: ENTRYPOINT] END ===
1722│ 
1723│
```

---

## FILE: `src/app.py`

```python
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
                insert_skipped_path(
                    conn,
                    row["relative_path"],
                    read_error.split(":", 1)[0],
                    read_error,
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
        f"Snapshot compiled: {snapshot_path.name} ({tree_entry_count} tree entries, {captured_file_count} files, {skipped_path_count} skipped)"
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

        snapshot_path = compile_snapshot(
            root=root,
            output_dir=self.get_output_dir(),
            tree_rows=tree_rows,
            folder_item_states=folder_item_states,
            policy=self.exclusion_policy,
            scan_skipped_paths=scan_skipped_paths,
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
```

---

## FILE: `src/app_BACKUP.py`

```python
import sys
import argparse
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import tkinter.font as tkFont
from pathlib import Path
from datetime import datetime
import subprocess
import platform
import threading
import queue
import traceback
import fnmatch
import os
import json
import tarfile
import sqlite3

# ==============================================================================
# 0. PYTHONW SAFETY CHECK
# ==============================================================================
# Fixes issues where pythonw crashes because it has no stdout/stderr attached
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# ==============================================================================
# 1. CORE CONFIGURATION & CONSTANTS
# ==============================================================================

APP_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT_DIR = APP_DIR

# --- Exclusions ---
EXCLUDED_FOLDERS = {
    "node_modules", ".git", "__pycache__", ".venv", ".mypy_cache",
    "_logs", "dist", "build", ".vscode", ".idea", "target", "out",
    "bin", "obj", "Debug", "Release", "logs", "venv"
}
PREDEFINED_EXCLUDED_FILENAMES = {
    "package-lock.json", "yarn.lock", ".DS_Store", "Thumbs.db",
    "*.pyc", "*.pyo", "*.swp", "*.swo"
}

# --- Binary Extensions (for skipping in dump) ---
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

# --- Log Configuration ---
LOG_ROOT_NAME = "_logs"
PROJECT_CONFIG_FILENAME = "_project_mapper_config.json"

# --- State Constants ---
S_CHECKED = "checked"
S_UNCHECKED = "unchecked"

# --- Theme ---
THEME = {
    "app_bg": "#161A1F",
    "panel_bg": "#1E252D",
    "panel_alt_bg": "#273241",
    "field_bg": "#263140",
    "field_bg_alt": "#2D3948",
    "tree_bg": "#1A212B",
    "tree_bg_disabled": "#313B48",
    "log_bg": "#10161E",
    "status_bg": "#0D1117",
    "status_text": "#89D6A0",
    "text": "#E7EDF4",
    "muted_text": "#97A4B3",
    "field_text": "#D6E2EE",
    "heading_bg": "#2A3441",
    "heading_text": "#F3F6F9",
    "selection": "#3B7E8D",
    "tree_row_highlight": "#D8E8FF",
    "tree_row_highlight_text": "#12283D",
    "accent": "#C56F3D",
    "accent_hover": "#D78251",
    "accent_active": "#A65A31",
    "secondary": "#2E7081",
    "secondary_hover": "#3A8EA2",
    "secondary_active": "#245867",
    "success": "#2F8E6A",
    "success_hover": "#3AA27C",
    "success_active": "#256F54",
    "danger": "#B75A4D",
    "danger_hover": "#CB6B5E",
    "danger_active": "#91473D",
    "checkbox_checked": "#C56F3D",
    "checkbox_border": "#728195",
    "log_text": "#E1E7EE",
    "log_accent": "#89D6A0",
}

# ==============================================================================
# 2. HELPER FUNCTIONS (Pure Logic / Stateless)
# ==============================================================================

def is_binary(file_path: Path) -> bool:
    """Check if a file is binary by reading the first chunk."""
    try:
        with open(file_path, 'rb') as f:
            return b'\0' in f.read(1024)
    except (IOError, PermissionError):
        return True
    except Exception:
        return True

def get_folder_size_bytes(folder_path: Path) -> int:
    """Recursively calculate folder size."""
    total_size = 0
    try:
        for entry in os.scandir(folder_path):
            if entry.is_file(follow_symlinks=False):
                try: total_size += entry.stat(follow_symlinks=False).st_size
                except OSError: pass
            elif entry.is_dir(follow_symlinks=False):
                try: total_size += get_folder_size_bytes(Path(entry.path))
                except OSError: pass
    except OSError: pass
    return total_size

def format_display_size(size_bytes: int) -> str:
    """Format bytes into readable string."""
    if size_bytes < 1024: return f"{size_bytes} B"
    size_kb = size_bytes / 1024
    if size_kb < 1024: return f"{size_kb:.1f} KB"
    size_mb = size_kb / 1024
    if size_mb < 1024: return f"{size_mb:.1f} MB"
    size_gb = size_mb / 1024
    return f"{size_gb:.2f} GB"

# ==============================================================================
# 3. GUI COMPONENTS & PROGRESS POPUP
# ==============================================================================

class ProgressPopup:
    """A popup window that streams activity and allows cancellation."""
    def __init__(self, parent, title="Processing", on_cancel=None):
        self.top = tk.Toplevel(parent)
        self.top.title(title)
        self.top.geometry("500x300")
        self.top.configure(bg=THEME["panel_bg"])
        self.top.transient(parent)
        self.top.grab_set()
        
        self.top.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        self.on_cancel = on_cancel
        self.is_cancelled = False

        # UI Elements
        lbl = tk.Label(
            self.top,
            text=f"{title}...",
            fg=THEME["text"],
            bg=THEME["panel_bg"],
            font=("Arial", 12, "bold"),
        )
        lbl.pack(pady=10)

        self.log_display = scrolledtext.ScrolledText(
            self.top,
            height=10,
            bg=THEME["log_bg"],
            fg=THEME["log_accent"],
            insertbackground=THEME["log_text"],
            font=("Consolas", 9),
        )
        self.log_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_frame = tk.Frame(self.top, bg=THEME["panel_bg"])
        btn_frame.pack(fill=tk.X, pady=10)

        self.cancel_btn = tk.Button(
            btn_frame,
            text="CANCEL OPERATION",
            bg=THEME["danger"],
            fg=THEME["text"],
            activebackground=THEME["danger_hover"],
            activeforeground=THEME["text"],
            font=("Arial", 10, "bold"),
            command=self.trigger_cancel,
        )
        self.cancel_btn.pack()

    def update_text(self, text):
        self.log_display.insert(tk.END, text + "\n")
        self.log_display.see(tk.END)

    def trigger_cancel(self):
        self.is_cancelled = True
        self.log_display.insert(tk.END, "\n!!! CANCELLATION REQUESTED - STOPPING !!!\n")
        self.log_display.see(tk.END)
        self.cancel_btn.config(state=tk.DISABLED, text="Stopping...")
        if self.on_cancel:
            self.on_cancel()

    def _on_close_attempt(self):
        if not self.is_cancelled:
            self.trigger_cancel()
        
    def close(self):
        self.top.destroy()


class ProjectMapperApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.gui_queue = queue.Queue()

        # Application State
        self.folder_item_states = {}
        self.dynamic_global_excluded_filenames = set()

        # .gitignore support (best-effort, simple patterns)
        self.gitignore_dirnames = set()
        self.gitignore_file_patterns = set()
        self.gitignore_path_patterns = set()

        self.running_tasks = set()
        self._tree_is_ready = False
        
        # Threading Safety
        self.state_lock = threading.RLock()
        self.stop_event = threading.Event()

        # References
        self.widgets = {}
        self.current_progress_popup = None

        # --- GENERATE ICONS PROGRAMMATICALLY (Robust/No Base64) ---
        self.icon_imgs = {}

        # 1. Unchecked Icon (Gray Border, Transparent Center)
        img_u = tk.PhotoImage(width=14, height=14)
        img_u.put((THEME["checkbox_border"],), to=(0, 0, 14, 1))    # Top border
        img_u.put((THEME["checkbox_border"],), to=(0, 13, 14, 14))  # Bottom border
        img_u.put((THEME["checkbox_border"],), to=(0, 0, 1, 14))    # Left border
        img_u.put((THEME["checkbox_border"],), to=(13, 0, 14, 14))  # Right border
        self.icon_imgs[S_UNCHECKED] = img_u

        # 2. Checked Icon (Blue Fill, White Checkmarkish shape)
        img_c = tk.PhotoImage(width=14, height=14)
        img_c.put((THEME["checkbox_checked"],), to=(0, 0, 14, 14))   # Warm accent background
        # Simple white "check" pixels
        img_c.put(("#FFFFFF",), to=(3, 7, 6, 10))    # Short leg
        img_c.put(("#FFFFFF",), to=(6, 5, 11, 8))    # Long leg
        self.icon_imgs[S_CHECKED] = img_c
        # ----------------------------------------------------------

        self._setup_styles()
        self._setup_ui()
        self.process_gui_queue()
        
        self._activity_blinker()

        # Initial Actions
        self.root.after(100, lambda: self.run_threaded_action(self._load_conda_info_impl, task_id='load_conda'))
        self.root.after(200, self._rescan_project_tree)

        # File Icon (Simple text document shape)
        img_f = tk.PhotoImage(width=14, height=14)
        # Outline
        img_f.put(("#FFFFFF",), to=(2, 1, 12, 2))   # Top
        img_f.put(("#FFFFFF",), to=(2, 1, 3, 13))   # Left
        img_f.put(("#FFFFFF",), to=(11, 1, 12, 13)) # Right
        img_f.put(("#FFFFFF",), to=(2, 12, 12, 13)) # Bottom
        # Lines representing text
        img_f.put((THEME["muted_text"],), to=(4, 4, 10, 5))
        img_f.put((THEME["muted_text"],), to=(4, 7, 10, 8))
        img_f.put((THEME["muted_text"],), to=(4, 10, 8, 11))
        self.icon_imgs["file"] = img_f

    # --- UI Setup ---
    def _setup_styles(self):
        style = ttk.Style()
        if "clam" in style.theme_names(): style.theme_use("clam")
        
        self.default_ui_font = "Arial"
        if "DejaVu Sans" in tkFont.families(): self.default_ui_font = "DejaVu Sans"

        tree_font = tkFont.Font(family=self.default_ui_font, size=11)
        
        self.widgets['tree_bg_normal'] = THEME["tree_bg"]
        self.widgets['tree_bg_disabled'] = THEME["tree_bg_disabled"]

        style.configure("Treeview", background=self.widgets['tree_bg_normal'], 
                        foreground=THEME["text"], fieldbackground=self.widgets['tree_bg_normal'],
                        borderwidth=0, font=tree_font, rowheight=24)
        style.map(
            "Treeview",
            background=[('selected', THEME["tree_row_highlight"])],
            foreground=[('selected', THEME["tree_row_highlight_text"])],
        )
        style.configure("Treeview.Heading", background=THEME["heading_bg"], foreground=THEME["heading_text"], relief=tk.FLAT)
        
        style.configure(
            'TCombobox',
            fieldbackground=THEME["field_bg"],
            background=THEME["panel_alt_bg"],
            foreground=THEME["field_text"],
            arrowcolor=THEME["heading_text"],
        )
        style.map(
            'TCombobox',
            fieldbackground=[('readonly', THEME["field_bg"])],
            background=[('readonly', THEME["panel_alt_bg"])],
            foreground=[('readonly', THEME["field_text"])],
        )

    def _setup_ui(self):
        self.root.title("Project Mapper - Systems Thinker Edition")
        self.root.configure(bg=THEME["app_bg"])
        self.root.geometry("1200x850")

        # 1. Top Bar
        top_frame = tk.Frame(self.root, bg=THEME["panel_bg"])
        top_frame.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(top_frame, text="Project Root:", bg=THEME["panel_bg"], fg=THEME["text"]).pack(side=tk.LEFT)
        
        self.widgets['selected_root_var'] = tk.StringVar(value=str(DEFAULT_ROOT_DIR))
        self.widgets['project_path_entry'] = tk.Entry(
            top_frame,
            textvariable=self.widgets['selected_root_var'],
            bg=THEME["field_bg"],
            fg=THEME["field_text"],
            insertbackground=THEME["field_text"],
            width=60,
            relief=tk.FLAT,
        )
        self.widgets['project_path_entry'].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.widgets['project_path_entry'].bind("<Return>", self._on_project_root_commit)

        tk.Button(
            top_frame,
            text="Choose...",
            command=self._on_choose_project_directory,
            bg=THEME["secondary"],
            fg=THEME["text"],
            activebackground=THEME["secondary_hover"],
            activeforeground=THEME["text"],
        ).pack(side=tk.RIGHT)
        tk.Button(
            top_frame,
            text="↑",
            command=self._on_click_up_dir,
            bg=THEME["panel_alt_bg"],
            fg=THEME["text"],
            activebackground=THEME["field_bg_alt"],
            activeforeground=THEME["text"],
        ).pack(side=tk.RIGHT, padx=5)

        # 2. Main Split (Changed to VERTICAL for pythonw layout stability)
        paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Top Pane: Tree
        left_frame = tk.Frame(paned, bg=THEME["panel_bg"])
        self.widgets['folder_tree'] = ttk.Treeview(
            left_frame,
            show="tree headings",
            columns=("nav_up", "nav_down", "size"),
            selectmode="browse",
        )
        self.widgets['folder_tree'].column("#0", width=760)
        self.widgets['folder_tree'].column("nav_up", width=34, anchor="center", stretch=False)
        self.widgets['folder_tree'].column("nav_down", width=34, anchor="center", stretch=False)
        self.widgets['folder_tree'].column("size", width=100, anchor="e", stretch=False)
        self.widgets['folder_tree'].heading("#0", text="Explorer")
        self.widgets['folder_tree'].heading("nav_up", text="↑")
        self.widgets['folder_tree'].heading("nav_down", text="↓")
        self.widgets['folder_tree'].heading("size", text="Size")
        
        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=self.widgets['folder_tree'].yview)
        self.widgets['folder_tree'].configure(yscrollcommand=vsb.set)
        
        self.widgets['folder_tree'].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.widgets['folder_tree'].bind("<ButtonRelease-1>", self.on_tree_item_click)
        self.widgets['folder_tree'].bind("<FocusOut>", self._on_tree_focus_out)
        
        paned.add(left_frame, weight=3) # Give tree more initial weight

        # Bottom Pane: Actions & Logs
        right_frame = tk.Frame(paned, bg=THEME["panel_bg"])

        # Action Buttons Grid
        btn_grid = tk.Frame(right_frame, bg=THEME["panel_bg"])
        btn_grid.pack(fill=tk.X, pady=5)
        
        self.widgets['buttons'] = {}
        actions = [
            ("Map Project Tree", self.build_folder_tree_impl, True),
            ("Dump Source Files", self.dump_files_impl, True),
            ("Export SQLite DB", self.export_sqlite_impl, True),
            ("Backup Project (Zip)", self.backup_project_impl, True),
            ("Audit System Info", self.audit_system_impl, False)
        ]

        for idx, (lbl, func, save) in enumerate(actions):
            r, c = divmod(idx, 4) # Spread buttons horizontally
            b = tk.Button(
                btn_grid,
                text=lbl,
                bg=THEME["accent"],
                fg=THEME["text"],
                activebackground=THEME["accent_hover"],
                activeforeground=THEME["text"],
                font=("Arial", 11, "bold"),
                pady=8,
            )
            task_id = lbl.split()[0].lower()
            b.config(command=lambda f=func, t=task_id, s=save: self.run_threaded_action(f, task_id=t, save_config_after=s, use_popup=True))
            b.grid(row=r, column=c, sticky="ew", padx=5, pady=5)
            btn_grid.columnconfigure(c, weight=1)
            self.widgets['buttons'][task_id] = b

        # Controls & Utility Section
        util_frame = tk.Frame(right_frame, bg=THEME["panel_bg"])
        util_frame.pack(fill=tk.X, pady=5)

        # -- Timestamp Checkbox --
        self.widgets['use_timestamps'] = tk.BooleanVar(value=False)
        ts_chk = tk.Checkbutton(
            util_frame,
            text="Append Timestamps to Filenames",
            variable=self.widgets['use_timestamps'],
            bg=THEME["panel_bg"],
            fg=THEME["text"],
            selectcolor=THEME["tree_bg"],
            activebackground=THEME["panel_bg"],
            activeforeground=THEME["text"],
        )
        ts_chk.pack(side=tk.LEFT, padx=10)

        # -- Exclusion / .gitignore Toggle (default ON) --
        self.widgets['respect_exclusions'] = tk.BooleanVar(value=True)
        excl_chk = tk.Checkbutton(
            util_frame,
            text="Respect .gitignore + exclusions",
            variable=self.widgets['respect_exclusions'],
            bg=THEME["panel_bg"],
            fg=THEME["text"],
            selectcolor=THEME["tree_bg"],
            activebackground=THEME["panel_bg"],
            activeforeground=THEME["text"],
        )
        excl_chk.pack(side=tk.LEFT, padx=10)

        # -- Conda --
        tk.Label(util_frame, text="| Env:", bg=THEME["panel_bg"], fg=THEME["muted_text"]).pack(side=tk.LEFT)
        self.widgets['conda_env_var'] = tk.StringVar()
        self.widgets['conda_env_combo'] = ttk.Combobox(util_frame, textvariable=self.widgets['conda_env_var'], state="readonly", width=15)
        self.widgets['conda_env_combo'].pack(side=tk.LEFT, padx=5)
        tk.Button(
            util_frame,
            text="Audit",
            bg=THEME["panel_alt_bg"],
            fg=THEME["text"],
            activebackground=THEME["field_bg_alt"],
            activeforeground=THEME["text"],
            font=("Arial", 8),
            command=lambda: self.run_threaded_action(self.audit_conda_impl, task_id='audit_conda', use_popup=True),
        ).pack(side=tk.LEFT)

        # -- Utility --
        tk.Button(
            util_frame,
            text="Open Logs",
            command=self.open_main_log_directory,
            bg=THEME["panel_alt_bg"],
            fg=THEME["text"],
            activebackground=THEME["field_bg_alt"],
            activeforeground=THEME["text"],
        ).pack(side=tk.RIGHT, padx=5)
        tk.Button(
            util_frame,
            text="Exclusions",
            command=self.manage_dynamic_exclusions_popup,
            bg=THEME["success"],
            fg=THEME["text"],
            activebackground=THEME["success_hover"],
            activeforeground=THEME["text"],
        ).pack(side=tk.RIGHT, padx=5)
        tk.Button(
            util_frame,
            text="All",
            command=lambda: self.set_global_selection(S_CHECKED),
            bg=THEME["panel_alt_bg"],
            fg=THEME["text"],
            activebackground=THEME["field_bg_alt"],
            activeforeground=THEME["text"],
            width=4,
        ).pack(side=tk.RIGHT, padx=2)
        tk.Button(
            util_frame,
            text="None",
            command=lambda: self.set_global_selection(S_UNCHECKED),
            bg=THEME["panel_alt_bg"],
            fg=THEME["text"],
            activebackground=THEME["field_bg_alt"],
            activeforeground=THEME["text"],
            width=4,
        ).pack(side=tk.RIGHT, padx=2)

        # -- Quick Add Exclusion --
        tk.Button(
            util_frame,
            text="Add",
            command=lambda: self.add_excluded_filename(self.exc_entry),
            bg=THEME["accent"],
            fg=THEME["text"],
            activebackground=THEME["accent_hover"],
            activeforeground=THEME["text"],
            font=("Arial", 8),
        ).pack(side=tk.RIGHT, padx=5)
        self.exc_entry = tk.Entry(
            util_frame,
            bg=THEME["field_bg_alt"],
            fg=THEME["field_text"],
            insertbackground=THEME["field_text"],
            width=15,
            relief=tk.FLAT,
        )
        self.exc_entry.pack(side=tk.RIGHT, padx=5)
        tk.Label(util_frame, text="Excl. Pattern:", bg=THEME["panel_bg"], fg=THEME["muted_text"]).pack(side=tk.RIGHT)

        # Log Box
        self.widgets['log_box'] = scrolledtext.ScrolledText(
            right_frame,
            bg=THEME["log_bg"],
            fg=THEME["log_text"],
            insertbackground=THEME["log_text"],
            font=("Consolas", 9),
            state=tk.DISABLED,
            height=10,
        )
        self.widgets['log_box'].pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        paned.add(right_frame, weight=1)

        # Status Bar
        self.widgets['status_var'] = tk.StringVar(value="Ready.")
        self.widgets['status_bar'] = tk.Label(
            self.root,
            textvariable=self.widgets['status_var'],
            bg=THEME["status_bg"],
            fg=THEME["status_text"],
            anchor="w",
        )
        self.widgets['status_bar'].pack(fill=tk.X, side=tk.BOTTOM)

    # --- Threading & Activity Logic ---
    def _activity_blinker(self):
        if self.running_tasks:
            current_color = self.widgets['status_bar'].cget("bg")
            next_color = THEME["panel_alt_bg"] if current_color == THEME["status_bg"] else THEME["status_bg"]
            self.widgets['status_bar'].config(bg=next_color)
            task_names = ", ".join(self.running_tasks)
            self.widgets['status_var'].set(f"[ACTIVE] Processing: {task_names}")
        else:
            self.widgets['status_bar'].config(bg=THEME["status_bg"])
            
        self.root.after(500, self._activity_blinker)

    def cancel_current_operations(self):
        self.stop_event.set()
        self.log_message("Stop signal sent to background threads.", "WARNING")

    def run_threaded_action(self, target_function_impl, task_id: str, widgets_to_disable=None, save_config_after=False, use_popup=False):
        if task_id in self.running_tasks:
            self.log_message(f"Task '{task_id}' is already running.", "WARNING")
            return

        if use_popup:
            self.current_progress_popup = ProgressPopup(self.root, title=f"Working: {task_id}", on_cancel=self.cancel_current_operations)

        def thread_target_wrapper():
            self.running_tasks.add(task_id)
            self.stop_event.clear()
            
            try:
                target_function_impl()
                if save_config_after:
                    path = self._get_current_project_path()
                    if path: self.save_project_config(path)
            except Exception as e:
                err_msg = f"CRASH in {task_id}: {e}\n{traceback.format_exc()}"
                self.schedule_log_message(err_msg, "CRITICAL")
            finally:
                if task_id in self.running_tasks:
                    self.running_tasks.remove(task_id)
                if use_popup and self.current_progress_popup:
                    self.gui_queue.put(self.current_progress_popup.close)
                    self.current_progress_popup = None
                self.schedule_log_message(f"Task '{task_id}' finished.", "INFO")

        threading.Thread(target=thread_target_wrapper, daemon=True).start()

    def schedule_log_message(self, msg: str, level: str = "INFO"):
        self.gui_queue.put(lambda: self.log_message(msg, level))
        def _update_popup_safely():
            if self.current_progress_popup:
                self.current_progress_popup.update_text(f"[{level}] {msg}")
        self.gui_queue.put(_update_popup_safely)

    def log_message(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("[%H:%M:%S]")
        full_msg = f"{ts} [{level}] {msg}\n"
        lb = self.widgets.get('log_box')
        if lb:
            lb.config(state=tk.NORMAL)
            lb.insert(tk.END, full_msg)
            lb.config(state=tk.DISABLED)
            lb.see(tk.END)
        self.widgets['status_var'].set(f"{ts} {msg}")

    def process_gui_queue(self):
        while not self.gui_queue.empty():
            try:
                cb = self.gui_queue.get_nowait()
                try: cb()
                except Exception: pass
            except queue.Empty: pass
        self.root.after(100, self.process_gui_queue)

    # --- Project Management Logic ---
    def _on_choose_project_directory(self):
        d = filedialog.askdirectory()
        if d:
            self.widgets['selected_root_var'].set(d)
            self._rescan_project_tree()

    def _on_project_root_commit(self, event=None):
        self._rescan_project_tree()

    def _on_click_up_dir(self):
        p = self._get_current_project_path()
        if p:
            self.widgets['selected_root_var'].set(str(p.parent))
            self._rescan_project_tree()

    def _get_current_project_path(self) -> Path | None:
        p_str = self.widgets['selected_root_var'].get()
        if p_str:
            p = Path(p_str)
            if p.is_dir(): return p
        return None

    def _rescan_project_tree(self):
        path = self._get_current_project_path()
        tree = self.widgets['folder_tree']
        for i in tree.get_children(): tree.delete(i)
        
        if not path:
            tree.insert("", "end", text="Invalid Root Path")
            return
            
        tree.insert("", "end", text="Scanning...")
        self.run_threaded_action(lambda: self._initial_tree_load_impl(path), task_id='load_tree')

    def _navigate_tree_to_path(self, target_path: Path):
        try:
            resolved = target_path.resolve()
        except Exception:
            return

        if not resolved.is_dir():
            return

        self.widgets['selected_root_var'].set(str(resolved))
        self.schedule_log_message(f"Explorer root changed to: {resolved}")
        self._rescan_project_tree()

    def _set_active_tree_row(self, iid: str | None):
        tree = self.widgets['folder_tree']
        if not iid or not tree.exists(iid):
            return
        tree.focus_set()
        tree.focus(iid)
        tree.selection_set(iid)

    def _clear_active_tree_row(self, _event=None):
        tree = self.widgets['folder_tree']
        tree.selection_remove(tree.selection())
        tree.focus("")

    def _on_tree_focus_out(self, _event):
        self.root.after(1, self._clear_active_tree_row)

    def _initial_tree_load_impl(self, root_path: Path):
        with self.state_lock:
            self.folder_item_states.clear()
        
        self.load_project_config(root_path)
        tree_data = []

        def _recurse(current: Path, parent_iid: str):
            if self.stop_event.is_set(): return
            try:
                # LIST ALL ITEMS (Files + Folders)
                # Sort: Folders first, then files (case insensitive)
                items = sorted(list(current.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
                
                for p in items:
                    # 1. SAFETY: Skip Excluded Folders/Files immediately
                    if self.should_exclude_path(p, root_path):
                        continue

                    path_str = str(p.resolve())
                    
                    # 2. State Inheritance
                    # If we don't have a specific state saved, inherit from parent
                    if path_str not in self.folder_item_states:
                        parent_state = self.folder_item_states.get(parent_iid, S_CHECKED)
                        with self.state_lock:
                            self.folder_item_states[path_str] = parent_state
                    
                    # 3. Add to Tree Data
                    # We add a visual prefix for files since we are using the image slot for the checkbox
                    display_text = f" {p.name}"
                    
                    tree_data.append({
                        'parent': parent_iid, 
                        'iid': path_str, 
                        'text': display_text
                    })
                    
                    # 4. Recurse only if Directory
                    if p.is_dir():
                        _recurse(p, path_str)
                        
            except PermissionError: pass

        root_str = str(root_path.resolve())
        with self.state_lock: self.folder_item_states[root_str] = S_CHECKED
        tree_data.append({'parent': '', 'iid': root_str, 'text': f" {root_path.name}", 'open': True})
        
        _recurse(root_path, root_str)
        self.gui_queue.put(lambda: self._populate_tree(tree_data))
    def _populate_tree(self, data):
        tree = self.widgets['folder_tree']
        for i in tree.get_children(): tree.delete(i)
        for d in data:
            tree.insert(
                d['parent'],
                "end",
                iid=d['iid'],
                text=d['text'],
                open=d.get('open', False),
                values=("", "", "..."),
            )
            tree.set(d['iid'], "size", "...")
        
        self.refresh_tree_visuals()
        root_path = self._get_current_project_path()
        if root_path:
             threading.Thread(target=self._calc_sizes_async, args=(str(root_path),), daemon=True).start()

    def _calc_sizes_async(self, root_iid):
        tree = self.widgets['folder_tree']
        q = [root_iid]
        while q:
            if self.stop_event.is_set(): break
            iid = q.pop(0)
            try:
                if not tree.exists(iid): continue
                sz = get_folder_size_bytes(Path(iid))
                fmt = format_display_size(sz)
                self.gui_queue.put(lambda i=iid, s=fmt: (tree.set(i, "size", s), self.refresh_tree_visuals(i)))
                q.extend(tree.get_children(iid))
            except: pass

    def refresh_tree_visuals(self, start_node=None):
        tree = self.widgets['folder_tree']
        def _refresh(iid):
            if not tree.exists(iid): return
            with self.state_lock:
                st = self.folder_item_states.get(iid, S_UNCHECKED)
            
            # Use Checkbox Icon
            icon = self.icon_imgs.get(st, self.icon_imgs[S_UNCHECKED])
            
            # Add File/Folder distinction to text
            p = Path(iid)
            prefix = "📄 " if p.is_file() else "" 
            
            tree.item(iid, text=f" {prefix}{p.name}", image=icon)
            if p.is_dir():
                tree.set(iid, "nav_up", "↑")
                tree.set(iid, "nav_down", "↓")
            else:
                tree.set(iid, "nav_up", "")
                tree.set(iid, "nav_down", "")
            
            # Recursion only needed for folders (files have no children)
            if tree.get_children(iid):
                for child in tree.get_children(iid): _refresh(child)
        
        if start_node: _refresh(start_node)
        else:
            root = self._get_current_project_path()
            if root: _refresh(str(root.resolve()))

    def _get_tree_click_action(self, tree, event):
        """Return the explicit control action for a tree click, or None."""
        iid = tree.identify_row(event.y)
        if not iid:
            return None, None

        element = tree.identify("element", event.x, event.y) or ""
        column = tree.identify_column(event.x)
        path = Path(iid)

        if "image" in element:
            return "toggle_checkbox", iid

        if not path.is_dir():
            return None, iid

        if column == "#1" and tree.set(iid, "nav_up") == "↑":
            return "navigate_up", iid

        if column == "#2" and tree.set(iid, "nav_down") == "↓":
            return "navigate_down", iid

        return None, iid

    def on_tree_item_click(self, event):
        tree = event.widget
        action, iid = self._get_tree_click_action(tree, event)

        if not iid:
            self._clear_active_tree_row()
            return

        self._set_active_tree_row(iid)

        if not action:
            return

        if action == "toggle_checkbox":
            with self.state_lock:
                curr = self.folder_item_states.get(iid, S_UNCHECKED)
                new = S_CHECKED if curr != S_CHECKED else S_UNCHECKED
                self.folder_item_states[iid] = new
            self.refresh_tree_visuals(iid)
            return

        p = Path(iid)
        if action == "navigate_up":
            parent = p.parent
            if parent != p and parent.is_dir():
                self._navigate_tree_to_path(parent)
            return

        if action == "navigate_down":
            self._navigate_tree_to_path(p)

    def set_global_selection(self, state):
        with self.state_lock:
            for k in self.folder_item_states:
                self.folder_item_states[k] = state
        self.refresh_tree_visuals()

    def is_selected(self, path: Path, project_root: Path) -> bool:
        try: p = path.resolve()
        except: return False
        root = project_root.resolve()
        if p != root and not str(p).startswith(str(root)): return False
        curr = p
        while True:
            st = self.folder_item_states.get(str(curr))
            if st == S_UNCHECKED: return False
            if curr == root: return st != S_UNCHECKED
            if curr.parent == curr: break
            curr = curr.parent
        return True

    def _load_gitignore_patterns(self, root: Path):
        """Best-effort .gitignore parsing.

        Supported (simple):
          - dir ignores via trailing '/'
          - bare patterns like '*.log'
          - path-ish patterns containing '/'

        Not supported (yet):
          - negation rules starting with '!'
          - advanced gitignore semantics (root anchoring, '**' edge cases, etc.)
        """
        gi = root / ".gitignore"
        with self.state_lock:
            self.gitignore_dirnames = set()
            self.gitignore_file_patterns = set()
            self.gitignore_path_patterns = set()

        if not gi.exists():
            return

        try:
            lines = gi.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return

        dirnames = set()
        file_pats = set()
        path_pats = set()

        for raw in lines:
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            # Skip negation rules for now
            if s.startswith("!"):
                continue

            # Normalize Windows separators to POSIX-ish for matching
            s = s.replace("\\", "/")

            if s.endswith("/"):
                # directory name or dir-pattern
                d = s[:-1].strip("/")
                if d:
                    dirnames.add(d)
                continue

            if "/" in s:
                path_pats.add(s.strip("/"))
            else:
                file_pats.add(s)

        with self.state_lock:
            self.gitignore_dirnames = dirnames
            self.gitignore_file_patterns = file_pats
            self.gitignore_path_patterns = path_pats

    def _rel_posix(self, p: Path, root: Path) -> str:
        """Return a posix-style relative path; fall back to name if relative fails."""
        try:
            return p.relative_to(root).as_posix()
        except Exception:
            return p.name

    def _respect_exclusions_enabled(self) -> bool:
        """UI/engine toggle: when False, include everything (verbose mapping)."""
        try:
            var = self.widgets.get('respect_exclusions')
            if var is None:
                return True
            return bool(var.get())
        except Exception:
            return True

    def should_exclude_dir(self, dir_path: Path, project_root: Path) -> bool:
        """Directory exclusion check: hard-coded exclusions + .gitignore (best-effort)."""
        if not self._respect_exclusions_enabled():
            return False

        name = dir_path.name
        if name in EXCLUDED_FOLDERS:
            return True

        rel = self._rel_posix(dir_path, project_root)

        with self.state_lock:
            if name in self.gitignore_dirnames:
                return True
            # Match path patterns against directory relpath
            for pat in self.gitignore_path_patterns:
                if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel + "/", pat) or fnmatch.fnmatch(rel + "/", pat + "/"):
                    return True

        return False

    def should_exclude_file(self, filename: str, rel_posix: str | None = None) -> bool:
        """File exclusion check: predefined + dynamic + .gitignore (best-effort)."""
        if not self._respect_exclusions_enabled():
            return False

        with self.state_lock:
            pats = PREDEFINED_EXCLUDED_FILENAMES.union(self.dynamic_global_excluded_filenames)
            gi_files = set(self.gitignore_file_patterns)
            gi_paths = set(self.gitignore_path_patterns)

        # filename-based patterns
        if any(fnmatch.fnmatch(filename, p) for p in pats):
            return True
        if any(fnmatch.fnmatch(filename, p) for p in gi_files):
            return True

        # relative-path patterns (if available)
        if rel_posix:
            rel_posix = rel_posix.replace("\\", "/")
            for pat in gi_paths:
                if fnmatch.fnmatch(rel_posix, pat):
                    return True

        return False

    def should_exclude_path(self, path: Path, project_root: Path) -> bool:
        """Unified exclusion gate for BOTH files and directories.

        This centralizes the behavior so initial scan, map, dump, and backup stay consistent.
        Uses:
          - Hard excluded folders
          - Predefined + dynamic filename patterns
          - .gitignore patterns (best-effort)
          - UI toggle to disable all exclusions
        """
        if not self._respect_exclusions_enabled():
            return False

        try:
            root = project_root.resolve()
            p = path.resolve()
        except Exception:
            return False

        # Only apply exclusions inside the active project root
        if p != root and not str(p).startswith(str(root)):
            return False

        if p.is_dir():
            return self.should_exclude_dir(p, root)

        relp = self._rel_posix(p, root)
        return self.should_exclude_file(p.name, rel_posix=relp)

    # --- Core Actions ---
    def get_log_dir(self, root: Path) -> Path | None:
        if not root: return None
        # CHANGED: All logs go directly to _logs, no subdirectories
        d = root / LOG_ROOT_NAME
        try: d.mkdir(parents=True, exist_ok=True)
        except: return None
        return d

    def _generate_filename(self, root_name: str, base_suffix: str, extension: str) -> str:
        # CHANGED: Naming convention logic
        # Default: FolderName_suffix.ext
        # If timestamp enabled: FolderName_suffix_timestamp.ext
        name = f"{root_name}_{base_suffix}"
        if self.widgets['use_timestamps'].get():
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            name += f"_{ts}"
        name += extension
        return name

    def build_folder_tree_impl(self):
        root = self._get_current_project_path()
        if not root: return
        
        out_dir = self.get_log_dir(root)
        fname = self._generate_filename(root.name, "project_folder_tree", ".txt")
        out_file = out_dir / fname
        
        lines = [f"Project Tree: {root}\nGenerated: {datetime.now()}\n"]
        
        def _write_recurse(curr, prefix):
            if self.stop_event.is_set(): 
                lines.append(f"{prefix}!!! CANCELLED !!!")
                return

            try: items = sorted(list(curr.iterdir()), key=lambda x: (x.is_file(), x.name.lower()))
            except: return
            
            for i, item in enumerate(items):
                is_last = (i == len(items) - 1)
                conn = "└── " if is_last else "├── "
                
                if item.is_dir():
                    # Respect exclusions/.gitignore (unless toggled off)
                    if self.should_exclude_path(item, root):
                        continue

                    if self.is_selected(item, root):
                        lines.append(f"{prefix}{conn}📁 {item.name}/")
                        _write_recurse(item, prefix + ("    " if is_last else "│   "))
                else:
                    if (not self.should_exclude_path(item, root)) and self.is_selected(item.parent, root):
                         lines.append(f"{prefix}{conn}📄 {item.name}")
        
        _write_recurse(root, "")
        
        with open(out_file, "w", encoding="utf-8") as f: f.write("\n".join(lines))
        self.schedule_log_message(f"Tree saved: {fname}")

    def dump_files_impl(self):
        root = self._get_current_project_path()
        if not root: return
        
        out_dir = self.get_log_dir(root)
        fname = self._generate_filename(root.name, "filedump", ".txt")
        out_file = out_dir / fname
        
        count = 0
        with open(out_file, "w", encoding="utf-8") as f_out:
            f_out.write(f"Dump: {root}\n\n")
            
            for r, d, f in os.walk(root):
                if self.stop_event.is_set(): 
                    f_out.write("\n\n!!! DUMP CANCELLED BY USER !!!")
                    break
    
                curr = Path(r)
                # First remove excluded folders (hard + .gitignore), then apply selection logic
                kept_dirs = []
                for x in d:
                    dp = curr / x
                    if self.should_exclude_path(dp, root):
                        continue
                    if not self.is_selected(dp, root):
                        continue
                    kept_dirs.append(x)
                d[:] = kept_dirs
                if not self.is_selected(curr, root): continue
                
                for fname_item in f:
                    if self.stop_event.is_set(): break

                    fpath = curr / fname_item
                    if self.should_exclude_path(fpath, root):
                        continue
                    if fpath.stat().st_size > 1_000_000: continue
                    if is_binary(fpath) or "".join(fpath.suffixes).lower() in FORCE_BINARY_EXTENSIONS_FOR_DUMP: continue
                    
                    rel = fpath.relative_to(root)
                    if count % 5 == 0: self.schedule_log_message(f"Dumping: {rel}", "DEBUG")
                    
                    try:
                        f_out.write(f"\n{'-'*80}\nFILE: {rel}\n{'-'*80}\n")
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f_in:
                            f_out.write(f_in.read())
                        count += 1
                    except Exception as e:
                        f_out.write(f"\n[ERROR READING FILE: {e}]\n")
        
        self.schedule_log_message(f"Dump saved: {fname} ({count} files)")

    def export_sqlite_impl(self):
        root = self._get_current_project_path()
        if not root: return

        out_dir = self.get_log_dir(root)
        fname = self._generate_filename(root.name, "project_export", ".sqlite3")
        out_file = out_dir / fname

        if out_file.exists():
            try:
                out_file.unlink()
            except Exception as e:
                self.schedule_log_message(f"SQLite export failed: could not replace {fname} ({e})", "ERROR")
                return

        created_at = datetime.now().isoformat(timespec="seconds")
        dumped_file_count = 0
        tree_entry_count = 0
        cancelled = False

        def upsert_metadata(conn, key: str, value):
            conn.execute(
                "INSERT OR REPLACE INTO export_metadata (key, value) VALUES (?, ?)",
                (key, "" if value is None else str(value)),
            )

        conn = None
        try:
            conn = sqlite3.connect(out_file)
            with conn:
                conn.execute(
                    """
                    CREATE TABLE export_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE project_tree (
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
                    CREATE TABLE project_files (
                        dump_order INTEGER NOT NULL,
                        relative_path TEXT PRIMARY KEY,
                        parent_relative_path TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        content TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE export_errors (
                        relative_path TEXT PRIMARY KEY,
                        error TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE export_artifacts (
                        name TEXT PRIMARY KEY,
                        content TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE export_manifest (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        manifest_version TEXT NOT NULL,
                        title TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        contents_markdown TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )

                base_metadata = {
                    "project_root": str(root),
                    "created_at": created_at,
                    "export_format_version": "1.1",
                    "respect_exclusions": int(self._respect_exclusions_enabled()),
                    "timestamps_enabled": int(self.widgets['use_timestamps'].get()),
                    "max_dump_file_size_bytes": 1_000_000,
                    "dump_encoding": "utf-8",
                    "manifest_table": "export_manifest",
                    "manifest_artifact_name": "agent_manifest_markdown",
                }
                for key, value in base_metadata.items():
                    upsert_metadata(conn, key, value)

                tree_lines = [f"Project Tree: {root}\nGenerated: {created_at}\n"]
                tree_order = 0

                def insert_tree_row(path: Path, parent_rel: str | None, entry_type: str, is_selected: bool):
                    nonlocal tree_entry_count, tree_order
                    rel = "." if path == root else self._rel_posix(path, root)
                    try:
                        size_bytes = get_folder_size_bytes(path) if path.is_dir() else path.stat().st_size
                    except OSError:
                        size_bytes = None

                    depth = 0 if rel == "." else len(rel.split("/"))
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO project_tree (
                            tree_order, relative_path, parent_relative_path, name,
                            entry_type, depth, size_bytes, is_selected
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            tree_order,
                            rel,
                            parent_rel,
                            path.name,
                            entry_type,
                            depth,
                            size_bytes,
                            int(is_selected),
                        ),
                    )
                    tree_order += 1
                    tree_entry_count += 1
                    return rel

                insert_tree_row(root, None, "dir", True)

                def walk_tree(curr: Path, prefix: str):
                    nonlocal cancelled
                    if self.stop_event.is_set():
                        cancelled = True
                        tree_lines.append(f"{prefix}!!! CANCELLED !!!")
                        return

                    try:
                        items = sorted(list(curr.iterdir()), key=lambda x: (x.is_file(), x.name.lower()))
                    except Exception:
                        return

                    visible_items = []
                    for item in items:
                        if item.is_dir():
                            if self.should_exclude_path(item, root):
                                continue
                            if not self.is_selected(item, root):
                                continue
                        else:
                            if self.should_exclude_path(item, root):
                                continue
                            if not self.is_selected(item.parent, root):
                                continue
                        visible_items.append(item)

                    parent_rel = "." if curr == root else self._rel_posix(curr, root)
                    for i, item in enumerate(visible_items):
                        if self.stop_event.is_set():
                            cancelled = True
                            tree_lines.append(f"{prefix}!!! CANCELLED !!!")
                            return

                        is_last = i == len(visible_items) - 1
                        connector = "└── " if is_last else "├── "

                        if item.is_dir():
                            insert_tree_row(item, parent_rel, "dir", True)
                            tree_lines.append(f"{prefix}{connector}📁 {item.name}/")
                            walk_tree(item, prefix + ("    " if is_last else "│   "))
                        else:
                            insert_tree_row(item, parent_rel, "file", True)
                            tree_lines.append(f"{prefix}{connector}📄 {item.name}")

                walk_tree(root, "")
                conn.execute(
                    "INSERT OR REPLACE INTO export_artifacts (name, content) VALUES (?, ?)",
                    ("project_tree_text", "\n".join(tree_lines)),
                )
                conn.commit()

                for r, d, f in os.walk(root):
                    if self.stop_event.is_set():
                        cancelled = True
                        break

                    curr = Path(r)
                    kept_dirs = []
                    for dirname in d:
                        dir_path = curr / dirname
                        if self.should_exclude_path(dir_path, root):
                            continue
                        if not self.is_selected(dir_path, root):
                            continue
                        kept_dirs.append(dirname)
                    d[:] = kept_dirs

                    if not self.is_selected(curr, root):
                        continue

                    for fname_item in f:
                        if self.stop_event.is_set():
                            cancelled = True
                            break

                        fpath = curr / fname_item
                        if self.should_exclude_path(fpath, root):
                            continue

                        try:
                            size_bytes = fpath.stat().st_size
                        except OSError as e:
                            conn.execute(
                                "INSERT OR REPLACE INTO export_errors (relative_path, error) VALUES (?, ?)",
                                (self._rel_posix(fpath, root), f"stat failed: {e}"),
                            )
                            continue

                        if size_bytes > 1_000_000:
                            continue
                        if is_binary(fpath) or "".join(fpath.suffixes).lower() in FORCE_BINARY_EXTENSIONS_FOR_DUMP:
                            continue

                        rel = self._rel_posix(fpath, root)
                        if dumped_file_count % 5 == 0:
                            self.schedule_log_message(f"Exporting to SQLite: {rel}", "DEBUG")

                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f_in:
                                content = f_in.read()
                            conn.execute(
                                """
                                INSERT OR REPLACE INTO project_files (
                                    dump_order, relative_path, parent_relative_path, size_bytes, content
                                ) VALUES (?, ?, ?, ?, ?)
                                """,
                                (
                                    dumped_file_count,
                                    rel,
                                    "." if curr == root else self._rel_posix(curr, root),
                                    size_bytes,
                                    content,
                                ),
                            )
                            dumped_file_count += 1
                            if dumped_file_count % 25 == 0:
                                conn.commit()
                        except Exception as e:
                            conn.execute(
                                "INSERT OR REPLACE INTO export_errors (relative_path, error) VALUES (?, ?)",
                                (rel, str(e)),
                            )

                upsert_metadata(conn, "tree_entry_count", tree_entry_count)
                upsert_metadata(conn, "dumped_file_count", dumped_file_count)
                upsert_metadata(conn, "was_cancelled", int(cancelled))
                manifest_summary = (
                    "Portable ProjectMapper snapshot containing the selected project tree, "
                    "selected text file contents, export metadata, and any read errors."
                )
                manifest_body = "\n".join([
                    "# ProjectMapper SQLite Export Manifest",
                    "",
                    "## Purpose",
                    manifest_summary,
                    "",
                    "## Snapshot",
                    f"- Source project root: `{root}`",
                    f"- Export file: `{fname}`",
                    f"- Generated at: `{created_at}`",
                    f"- Tree entries exported: `{tree_entry_count}`",
                    f"- Text files dumped: `{dumped_file_count}`",
                    f"- Export cancelled: `{int(cancelled)}`",
                    "",
                    "## Tables",
                    "- `export_manifest`: this onboarding document.",
                    "- `export_metadata`: key/value facts about this export run.",
                    "- `project_tree`: selected directories and files in traversal order.",
                    "- `project_files`: dumped text file contents keyed by relative path.",
                    "- `export_errors`: paths that could not be read or stat-ed cleanly.",
                    "- `export_artifacts`: derived human-readable artifacts stored in the DB.",
                    "",
                    "## Inclusion Rules",
                    "- Selection follows the checkbox state in the ProjectMapper tree.",
                    "- If `respect_exclusions` is `1`, `.gitignore`, hard exclusions, and dynamic filename exclusions were applied.",
                    "- `project_files` only includes text-readable files at or below `1000000` bytes.",
                    "- Binary-like files and known database/archive/media formats are skipped from `project_files`.",
                    "- The root path is represented as `.` in relative-path columns.",
                    "",
                    "## Path Conventions",
                    "- `relative_path` values use POSIX-style `/` separators.",
                    "- `parent_relative_path` points to the containing directory, with root as `.`.",
                    "- Join `project_tree.relative_path` to `project_files.relative_path` to map tree nodes to dumped content.",
                    "",
                    "## Important Metadata Keys",
                    "- `export_format_version`",
                    "- `project_root`",
                    "- `created_at`",
                    "- `respect_exclusions`",
                    "- `timestamps_enabled`",
                    "- `max_dump_file_size_bytes`",
                    "- `tree_entry_count`",
                    "- `dumped_file_count`",
                    "- `was_cancelled`",
                    "",
                    "## Quick Start Queries",
                    "```sql",
                    "SELECT * FROM export_manifest;",
                    "SELECT key, value FROM export_metadata ORDER BY key;",
                    "SELECT relative_path, entry_type, size_bytes FROM project_tree ORDER BY tree_order;",
                    "SELECT relative_path, substr(content, 1, 400) AS preview FROM project_files ORDER BY dump_order LIMIT 20;",
                    "SELECT * FROM export_errors ORDER BY relative_path;",
                    "```",
                    "",
                    "## Caveats",
                    "- File contents were read as UTF-8 with `errors='ignore'`.",
                    "- If `was_cancelled` is `1`, this database may be partial.",
                    "- Files omitted by selection or exclusion rules do not appear in exported tables.",
                ])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO export_manifest (
                        id, manifest_version, title, summary, contents_markdown, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        1,
                        "1.1",
                        "ProjectMapper SQLite Export Manifest",
                        manifest_summary,
                        manifest_body,
                        created_at,
                    ),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO export_artifacts (name, content) VALUES (?, ?)",
                    ("agent_manifest_markdown", manifest_body),
                )
                conn.commit()

            if cancelled:
                self.schedule_log_message(
                    f"SQLite export cancelled: {fname} ({tree_entry_count} tree entries, {dumped_file_count} files captured)",
                    "WARNING",
                )
            else:
                self.schedule_log_message(
                    f"SQLite export saved: {fname} ({tree_entry_count} tree entries, {dumped_file_count} files)",
                )
        except Exception as e:
            self.schedule_log_message(f"SQLite export failed: {e}", "ERROR")
        finally:
            if conn is not None:
                conn.close()

    def backup_project_impl(self):
        root = self._get_current_project_path()
        if not root: return
        
        out_dir = self.get_log_dir(root)
        fname = self._generate_filename(root.name, "backup", ".tar.gz")
        out_file = out_dir / fname
        
        count = 0
        with tarfile.open(out_file, "w:gz") as tar:
            for r, d, f in os.walk(root):
                if self.stop_event.is_set(): break
                curr = Path(r)
                kept_dirs = []
                for x in d:
                    dp = curr / x
                    if self.should_exclude_path(dp, root):
                        continue
                    if not self.is_selected(dp, root):
                        continue
                    kept_dirs.append(x)
                d[:] = kept_dirs
                if not self.is_selected(curr, root): continue
                for fname_item in f:
                    fpath = curr / fname_item
                    if self.should_exclude_path(fpath, root):
                        continue
                    tar.add(fpath, arcname=fpath.relative_to(root))
                    count += 1
                    if count % 10 == 0: self.schedule_log_message(f"Archiving: {fname_item}", "DEBUG")

        if self.stop_event.is_set():
            self.schedule_log_message("Backup Cancelled.", "WARNING")
        else:
            self.schedule_log_message(f"Backup saved: {fname}")

    def audit_system_impl(self):
        root = self._get_current_project_path() or DEFAULT_ROOT_DIR
        out_dir = self.get_log_dir(root)
        fname = self._generate_filename(root.name, "system_audit", ".txt")
        out_file = out_dir / fname
        
        lines = [f"System Audit: {datetime.now()}", f"Platform: {platform.platform()}"]
        lines.append(f"Python: {sys.version}")
        lines.append("\nEnvironment Variables (Keys only):")
        for k in os.environ.keys(): lines.append(f"  {k}")
        
        with open(out_file, "w") as f: f.write("\n".join(lines))
        self.schedule_log_message(f"System audit saved: {fname}")

    def audit_conda_impl(self):
        env_name = self.widgets['conda_env_var'].get()
        if not env_name: return
        root = self._get_current_project_path() or DEFAULT_ROOT_DIR
        out_dir = self.get_log_dir(root)
        fname = self._generate_filename(f"conda_{env_name}", "audit", ".txt")
        out_file = out_dir / fname
        
        self.schedule_log_message(f"Auditing Conda Env: {env_name}...")
        try:
            res = subprocess.run(["conda", "list", "-n", env_name], capture_output=True, text=True, shell=True)
            with open(out_file, "w") as f: f.write(res.stdout)
            self.schedule_log_message(f"Conda audit saved: {fname}")
        except Exception as e:
            self.schedule_log_message(f"Conda audit failed: {e}", "ERROR")

    def _load_conda_info_impl(self):
        try:
            res = subprocess.run(["conda", "env", "list", "--json"], capture_output=True, text=True, shell=True)
            data = json.loads(res.stdout)
            envs = [Path(p).name for p in data.get('envs', [])]
            self.gui_queue.put(lambda: self.widgets['conda_env_combo'].config(values=envs))
            if envs: self.gui_queue.put(lambda: self.widgets['conda_env_combo'].current(0))
        except: pass

    # --- Persistence ---
    def save_project_config(self, root: Path):
        cfg = self.get_log_dir(root) / PROJECT_CONFIG_FILENAME
        rel_states = {}
        with self.state_lock:
            for k, v in self.folder_item_states.items():
                try: rel_states[str(Path(k).relative_to(root))] = v
                except: pass
            data = {
                "folder_states": rel_states,
                "dynamic_exclusions": list(self.dynamic_global_excluded_filenames)
            }
        with open(cfg, "w") as f: json.dump(data, f, indent=2)

    def load_project_config(self, root: Path):
        # Always (re)load .gitignore for the active root (best-effort)
        self._load_gitignore_patterns(root)

        cfg = self.get_log_dir(root) / PROJECT_CONFIG_FILENAME
        if not cfg.exists(): return
        try:
            with open(cfg, "r") as f: data = json.load(f)
            for k, v in data.get("folder_states", {}).items():
                self.folder_item_states[str((root / k).resolve())] = v
            self.dynamic_global_excluded_filenames.update(data.get("dynamic_exclusions", []))
        except: pass

    # --- Dynamic Exclusions ---
    def add_excluded_filename(self, entry):
        val = entry.get().strip()
        if val:
            self.dynamic_global_excluded_filenames.add(val)
            entry.delete(0, tk.END)
            self.schedule_log_message(f"Added exclusion: {val}")

    def manage_dynamic_exclusions_popup(self):
        top = tk.Toplevel(self.root)
        top.title("Exclusions")
        top.configure(bg=THEME["panel_bg"])
        lb = tk.Listbox(
            top,
            bg=THEME["tree_bg"],
            fg=THEME["text"],
            selectbackground=THEME["selection"],
            selectforeground=THEME["heading_text"],
        )
        lb.pack(fill=tk.BOTH, expand=True)
        for x in self.dynamic_global_excluded_filenames: lb.insert(tk.END, x)
        def _rem():
            sel = lb.curselection()
            if not sel: return
            val = lb.get(sel[0])
            self.dynamic_global_excluded_filenames.remove(val)
            top.destroy()
            self.manage_dynamic_exclusions_popup()
        tk.Button(
            top,
            text="Remove Selected",
            command=_rem,
            bg=THEME["danger"],
            fg=THEME["text"],
            activebackground=THEME["danger_hover"],
            activeforeground=THEME["text"],
        ).pack(pady=8)

    def open_main_log_directory(self):
        p = self._get_current_project_path()
        if not p: return
        d = self.get_log_dir(p)
        if platform.system() == "Windows": os.startfile(d)
        elif platform.system() == "Darwin": subprocess.run(["open", d])
        else: subprocess.run(["xdg-open", d])


# ==============================================================================
# 4. ENTRY POINTS
# ==============================================================================

def run_gui():
    root = tk.Tk()
    app = ProjectMapperApp(root)
    root.mainloop()

def run_cli():
    parser = argparse.ArgumentParser(description="ProjectMapper CLI")
    parser.add_argument("path", nargs="?", default=".", help="Root path to map")
    args = parser.parse_args()
    
    target = Path(args.path).resolve()
    print(f"--- Project Mapper CLI ---\nMapping: {target}\n")
    
    if not target.is_dir():
        print("Error: Invalid directory.")
        sys.exit(1)
        
    for item in target.rglob("*"):
        depth = len(item.relative_to(target).parts)
        indent = "  " * depth
        print(f"{indent}{item.name}")
        
    print("\nDone. For full features (backup, dumping, config), use GUI mode.")

def main():
    if len(sys.argv) > 1 and sys.argv[1] not in ["-m", "src.app"]:
        run_cli()
    else:
        run_gui()

if __name__ == "__main__":
    main()
```

---

## FILE: `_ProjectMAPPER.spec`

```text
# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\src\\app.py'],
    pathex=['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER'],
    binaries=[],
    datas=[('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\assets', 'assets'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\assets', 'assets'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\src', 'src')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='_ProjectMAPPER',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_ProjectMAPPER\\assets\\icons\\projectmapper.ico'],
)
```

---

## FILE: `gitignore`

```text
# Dependencies
node_modules
.pnp
.pnp.js

# Testing
coverage

# Production
build
dist

# Misc
.DS_Store
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# Logs
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Editor directories and files
.idea
.vscode
*.swp
*.swo
```

---

## FILE: `LICENSE.md`

```markdown
MIT License

Copyright (c) 2025 Jacob Lambert

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## FILE: `README.md`

```markdown

```

---

## FILE: `requirements.txt`

```text
tk>=0.1.0
```

---

## FILE: `setup_env.bat`

```bat
@echo off
echo [SYSTEM] Initializing new project environment...

:: 1. Create the venv if it doesn't exist
if not exist .venv (
    echo [SYSTEM] Creating .venv...
    py -m venv .venv
)

:: 2. Upgrade pip and install requirements
echo [SYSTEM] Installing dependencies...
.venv\Scripts\python.exe -m pip install --upgrade pip
if exist requirements.txt (
    .venv\Scripts\pip install -r requirements.txt
)

echo.
echo [SUCCESS] Environment ready!
echo You can now open this folder in VS Code or launch via scripts_menu.py
pause
```
