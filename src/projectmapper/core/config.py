"""Application constants without UI dependencies."""
from pathlib import Path

APP_NAME = "ProjectMapper Snapshot Compiler"
APP_VERSION = "0.4.0"  # Single version source; pyproject.toml reads it.
SNAPSHOT_SCHEMA_VERSION = "0.1"
SNAPSHOT_COMPILER_ID = "projectmapper.snapshot_compiler"

APP_DIR = Path(__file__).resolve().parents[1]


def _source_checkout_root():
    """Repository root for a src-layout checkout; None for an installed package."""
    candidate = APP_DIR.parents[1]
    if (candidate / "pyproject.toml").is_file() and candidate / "src" / APP_DIR.name == APP_DIR:
        return candidate
    return None


SOURCE_ROOT = _source_checkout_root()
OUTPUT_ROOT_NAME = "_projectmapper"
VENDOR_EXPORT_ROOT_NAME = "vendor_exports"
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
    "package-lock.json", "yarn.lock", ".DS_Store", "Thumbs.db", "*.bak",
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

VENDOR_EXPORT_INCLUDE_FILES = (
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE.md",
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "run.bat",
    "setup_env.bat",
)

VENDOR_EXPORT_INCLUDE_DIRS = (
    "assets",
    "src",
    "tools",
)

VENDOR_EXPORT_EXCLUDED_NAMES = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    ".idea", ".vscode", "node_modules", "coverage", "build", "dist",
    OUTPUT_ROOT_NAME, VENDOR_EXPORT_ROOT_NAME, "_logs", "logs",
}

VENDOR_EXPORT_EXCLUDED_PREFIXES = (
    ".env",
)

VENDOR_EXPORT_EXCLUDED_SUFFIXES = (
    ".pyc", ".pyo", ".pyd", ".log", ".tmp", ".sqlite", ".sqlite3",
    ".db", ".db3", ".bak", ".egg-info",
)
