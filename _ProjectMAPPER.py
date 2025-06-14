# projectMAPPER.py
# A standalone project mapping + auditing + backup tool
# Version 0.6.1 - Integrated thread-safe scan timeout.
"""
ProjectMAPPER: A Tkinter-based desktop application for project analysis.

This tool allows users to:
- Select a project root directory.
- Interactively select folders and files for inclusion/exclusion.
- Generate a textual project tree map.
- Dump the content of selected (non-binary) files into a single log.
- Audit the system environment (Python version, pip freeze, OS details).
- Audit Conda environments (list all, show packages for selected/active).
- Create a compressed tar.gz backup of selected project files and folders.
- Manage dynamic filename exclusion patterns.
- Persist selection and exclusion configurations per project.
- View all operations and messages in an in-app log, which can also be saved.
"""

import os
import json
import tarfile
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import tkinter.font as tkFont
from pathlib import Path
from datetime import datetime
import subprocess
import platform
import threading
import queue
import sys
import time

# ==============================================================================
# --- Constants ---
# ==============================================================================

# --- Application Version ---
SCRIPT_VERSION: str = "0.6.1"

# --- Application Paths & Default Configuration ---
APP_DIR: Path = Path(__file__).resolve().parent
DEFAULT_ROOT_DIR: Path = APP_DIR # Default script dir
PROJECT_CONFIG_FILENAME: str = "_project_mapper_config.json"
MAX_SCAN_TIME_SECONDS: int = 20 # Seconds before asking user to continue a long scan

# --- Predefined Exclusions ---
EXCLUDED_FOLDERS: set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", ".mypy_cache",
    "_logs", "dist", "build", ".vscode", ".idea", "target", "out",
    "bin", "obj", "Debug", "Release", "logs"
}
PREDEFINED_EXCLUDED_FILENAMES: set[str] = {
    "package-lock.json", "yarn.lock", ".DS_Store", "Thumbs.db",
    "*.pyc", "*.pyo", "*.swp", "*.swo"  # Common temp/compiled files
}

# --- File Type Definitions (for content dumping) ---
FORCE_BINARY_EXTENSIONS_FOR_DUMP: set[str] = {
    # Archives
    ".tar.gz", ".gz", ".zip", ".rar", ".7z", ".bz2", ".xz", ".tgz",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff",
    # Audio
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a",
    # Video
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
    # Executables & Libraries
    ".exe", ".dll", ".so", ".o", ".a", ".lib", ".app", ".dmg", ".deb", ".rpm",
    # Databases & Various Data Files
    ".db", ".sqlite", ".mdb", ".accdb", ".dat", ".idx", ".pickle", ".joblib",
    # Compiled code
    ".pyc", ".pyo", ".class", ".jar", ".wasm",
    # Fonts
    ".ttf", ".otf", ".woff", ".woff2",
    # Other common binary formats
    ".iso", ".img", ".bin", ".bak", ".data", ".asset", ".pak"
}

# --- Log Subdirectory Names (relative to project's _logs folder) ---
LOG_SUBDIR_ROOT: str = "_logs"  # Base name for the logs directory within a project
LOG_SUBDIR_TREE: str = "_projectTREE_maps"
LOG_SUBDIR_DUMP: str = "_projectDUMP_contents"
LOG_SUBDIR_CONDA: str = "_condaENV_audits"
LOG_SUBDIR_SYSTEM: str = "_systemENV_audits"
LOG_SUBDIR_BACKUP: str = "_projectBACKUP_zips"
LOG_SUBDIR_SESSION: str = "_appSESSION_logs"

# --- Logging Levels (for in-app and file logs) ---
LOG_DEBUG: str = "DEBUG"
LOG_INFO: str = "INFO"
LOG_WARNING: str = "WARNING"
LOG_ERROR: str = "ERROR"
LOG_CRITICAL: str = "CRITICAL"

# --- UI State Constants & Glyphs ---
S_CHECKED: str = "checked"        # Represents a checked state for tree items
S_UNCHECKED: str = "unchecked"    # Represents an unchecked state for tree items
GLYPH_CHECKED: str = "[X]"        # Visual indicator for checked items
GLYPH_UNCHECKED: str = "[ ]"      # Visual indicator for unchecked items
GLYPH_TRISTATE: str = "[/]"       # Visual indicator for items with mixed children states

# ==============================================================================
# --- Global Variables & Application State ---
# ==============================================================================

# --- Mutable Global Collections (managed by specific functions) ---
folder_tree_item_states: dict[str, str] = {}  # Stores explicit check state of folder tree items (path_str: S_CHECKED/S_UNCHECKED)
dynamic_global_excluded_filenames: set[str] = set() # User-added filename/pattern exclusions
popup_exclusion_checkbox_vars: dict[str, tk.IntVar] = {} # Stores tk.IntVar for checkboxes in exclusion management popup

# --- Queues & Application State Dictionary ---
gui_queue: queue.Queue = queue.Queue() # Queue for GUI updates from threads
scan_timeout_result_queue: queue.Queue = queue.Queue() # Queue for timeout messagebox result

app_state: dict = {
    "root": None,                            # Main tk.Tk() window instance
    "log_box": None,                         # scrolledtext.ScrolledText widget for in-app logs
    "status_var": None,                      # tk.StringVar for the status bar
    "selected_root_var": None,               # tk.StringVar for the project root path Entry
    "folder_tree": None,                     # ttk.Treeview widget for displaying folder structure
    "project_path_entry": None,              # tk.Entry widget for project root path
    "project_path_entry_normal_fg": "lightblue", # Default text color for project path entry
    "project_path_entry_error_fg": "salmon",   # Error text color for project path entry
    "default_ui_font": "Arial",              # Default font family for UI elements

    # Conda related state
    "conda_executable": None,                # Path to conda executable (str) or "conda" (if general) or None
    "selected_conda_env_var": None,          # tk.StringVar for Conda environment Combobox selection
    "conda_env_names_list": ["Checking Conda..."], # List of names for Conda Combobox
    "conda_env_paths_map": {},               # Maps Conda environment name (str) to its full path (str)
    "conda_combobox": None,                  # ttk.Combobox widget for Conda environment selection
    "conda_initially_found_basic": False     # Boolean: Basic 'conda --version' check successful on startup
}

# ==============================================================================
# --- 🧰 Helper Functions ---
# ==============================================================================

def get_log_output_dir(selected_root_path: Path, sub_dir_key: str = None, ensure_exists: bool = True) -> Path | None:
    """
    Determines and optionally creates the logging directory for a given sub-category.

    All logs are placed within a main '_logs' directory inside the selected_root_path.
    This function constructs the path to a specific subdirectory (e.g., for tree maps, dumps).
    If creation fails, it attempts to use a fallback directory in the application's own folder.

    Args:
        selected_root_path: The Path object for the currently selected project root.
        sub_dir_key: Optional string key (e.g., LOG_SUBDIR_TREE) to specify a subdirectory
                     within the main '_logs' folder. If None, returns the main '_logs' path.
        ensure_exists: If True, attempts to create the directory if it doesn't exist.

    Returns:
        A Path object to the target log directory, or None if a critical error occurs
        and no fallback directory can be established.
    """
    if not selected_root_path or not isinstance(selected_root_path, Path):
        schedule_log_message(f"Invalid selected_root_path type: {type(selected_root_path)} for get_log_output_dir", LOG_ERROR)
        # Critical fallback if project path is unusable
        critical_fallback = APP_DIR / "_projectMAPPER_critical_error_logs"
        if ensure_exists:
            try:
                critical_fallback.mkdir(parents=True, exist_ok=True)
            except OSError: # Should not happen with APP_DIR usually
                return None
        return critical_fallback

    base_log_dir = selected_root_path / LOG_SUBDIR_ROOT
    target_dir = base_log_dir / sub_dir_key if sub_dir_key else base_log_dir

    if ensure_exists:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            schedule_log_message(f"Could not create/access log directory {target_dir}: {e}", LOG_ERROR)
            # Fallback to a directory within the application's own directory
            fb_name = "_projectMAPPER_fallback_logs"
            fb_dir_base = APP_DIR / fb_name
            fb_dir = fb_dir_base / (sub_dir_key or "")
            try:
                fb_dir.mkdir(parents=True, exist_ok=True)
                schedule_log_message(f"Using fallback log directory: {fb_dir}", LOG_WARNING)
                return fb_dir
            except OSError as e_fb:
                schedule_log_message(f"CRITICAL ERROR: No log directory writable, including fallback: {e_fb}", LOG_CRITICAL)
                return None
    return target_dir

def log_message(msg: str, log_box_widget: scrolledtext.ScrolledText, status_var_widget: tk.StringVar, level: str = LOG_INFO) -> None:
    """
    Logs a message to the in-app ScrolledText widget and updates the status bar.

    This function is intended to be called directly from the main GUI thread.
    For logging from other threads, use `schedule_log_message`.

    Args:
        msg: The message string to log.
        log_box_widget: The ScrolledText widget used for displaying logs.
        status_var_widget: The tk.StringVar linked to the status bar label.
        level: The logging level (e.g., LOG_INFO, LOG_ERROR).
    """
    if not log_box_widget or not status_var_widget:
        print(f"[{level}][Early Log - UI Not Ready]: {msg}") # Fallback if UI components aren't set
        return

    timestamp = datetime.now().strftime("[%H:%M:%S]")
    full_message = f"{timestamp} [{level}] {msg}\n"

    try:
        # Temporarily enable the widget to insert text, then disable again
        original_state = log_box_widget.cget("state")
        log_box_widget.config(state=tk.NORMAL)
        log_box_widget.insert(tk.END, full_message)
        log_box_widget.config(state=original_state) # Restore original state
        log_box_widget.see(tk.END)  # Scroll to the end to show the latest message

        status_var_widget.set(f"{timestamp} {msg}") # Update status bar (shorter message)
    except Exception as e:
        # Critical fallback if logging to UI fails
        print(f"CONSOLE: Exception in log_message while updating UI: {e}. Original Msg: {msg}")

def schedule_log_message(msg: str, level: str = LOG_INFO) -> None:
    """
    Schedules a message to be logged to the GUI from any thread.

    This function puts a logging task onto a queue, which is processed by the
    main GUI thread, ensuring thread-safe updates to Tkinter widgets.

    Args:
        msg: The message string to log.
        level: The logging level (e.g., LOG_INFO, LOG_ERROR).
    """
    log_box = app_state.get('log_box')
    status_var = app_state.get('status_var')

    if log_box and status_var:
        # lambda: function captures current log_box & status_var for execution in GUI thread
        gui_queue.put(lambda lb=log_box, sv=status_var: log_message(msg, lb, sv, level))
    else:
        # Fallback if UI elements are not yet initialized in app_state
        print(f"CONSOLE: [{level}][Scheduled Log - UI Widgets Not Ready in app_state]: {msg}")

def apply_timestamp(name: str) -> str:
    """
    Appends a timestamp to a filename string.

    The timestamp is in the format 'YYYY-MM-DD_HH-MM-SS'.
    Example: "report.txt" -> "report_2023-10-27_15-30-00.txt"

    Args:
        name: The original filename string.

    Returns:
        The filename string with an appended timestamp before the extension.
    """
    path_obj = Path(name)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    return f"{path_obj.stem}_{timestamp}{path_obj.suffix}"

def is_binary(file_path: Path) -> bool:
    """
    Checks if a file is likely binary.

    First, it checks against a list of known binary extensions.
    If not a known binary extension, it reads a small chunk of the file
    and checks for the presence of null bytes, a common indicator of binary files.

    Args:
        file_path: Path object of the file to check.

    Returns:
        True if the file is likely binary, False otherwise.
        Returns True and logs a warning if the file cannot be read.
    """
    try:
        # Check by extension first for common binary types
        if "".join(file_path.suffixes).lower() in FORCE_BINARY_EXTENSIONS_FOR_DUMP:
            return True
        # If not in the force list, check content for null bytes
        with open(file_path, 'rb') as f:
            return b'\0' in f.read(1024)  # Read first 1KB
    except (IOError, PermissionError) as e:
        schedule_log_message(f"Cannot read file {file_path.name} to check if binary: {e}. Assuming binary.", LOG_WARNING)
        return True
    except Exception as e_general:
        schedule_log_message(f"Unexpected error checking if file {file_path.name} is binary: {e_general}. Assuming binary.", LOG_WARNING)
        return True

def get_folder_size_bytes(folder_path: Path) -> int:
    """
    Recursively calculates the total size of all files within a folder.

    Args:
        folder_path: Path object of the folder.

    Returns:
        Total size of files in bytes. Returns 0 if folder is inaccessible or empty.
    """
    total_size = 0
    try:
        for entry in os.scandir(folder_path):
            if entry.is_file(follow_symlinks=False):
                try:
                    total_size += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    pass  # File might have been deleted or become inaccessible
            elif entry.is_dir(follow_symlinks=False):
                try:
                    total_size += get_folder_size_bytes(Path(entry.path))
                except OSError:
                    pass  # Sub-folder might be inaccessible
    except OSError:
        pass # Folder itself might be inaccessible
    return total_size

def format_display_size(size_bytes: int) -> str:
    """
    Formats a size in bytes into a human-readable string (B, KB, MB, GB).

    Args:
        size_bytes: The size in bytes.

    Returns:
        A string representing the formatted size, e.g., "(1.2 MB)".
    """
    if size_bytes == 0:
        return "(0 B)" # Changed from KB to B for 0 size for clarity
    if size_bytes < 1024:
        return f"({size_bytes} B)"
    size_kb = size_bytes / 1024
    if size_kb < 1024:
        return f"({size_kb:.1f} KB)"
    size_mb = size_kb / 1024
    if size_mb < 1024:
        return f"({size_mb:.1f} MB)"
    size_gb = size_mb / 1024
    return f"({size_gb:.2f} GB)"

# --- Project Config Persistence ---
def get_project_config_file_path(project_root: Path) -> Path | None:
    """
    Gets the full path to the project-specific configuration file.

    The config file is stored in the main '_logs' directory of the project.

    Args:
        project_root: The Path object for the project's root directory.

    Returns:
        A Path object to the config file, or None if the log directory cannot be determined.
    """
    log_dir = get_log_output_dir(project_root, sub_dir_key=None, ensure_exists=True) # Ensure base _logs dir exists
    if log_dir:
        return log_dir / PROJECT_CONFIG_FILENAME
    schedule_log_message(f"Could not determine base log directory for project config at {project_root}", LOG_ERROR)
    return None

def save_project_config(project_root: Path) -> None:
    """
    Saves the current project's configuration (folder selection states, dynamic exclusions)
    to a JSON file within the project's _logs directory.

    Args:
        project_root: The Path object for the project's root directory.
    """
    if not project_root or not project_root.is_dir():
        schedule_log_message("Cannot save project config: invalid project root provided.", LOG_ERROR)
        return

    config_file_path = get_project_config_file_path(project_root)
    if not config_file_path:
        schedule_log_message(f"Could not get path to save project config for '{project_root.name}'", LOG_ERROR)
        return

    relative_folder_states = {}
    for abs_path_str, state in folder_tree_item_states.items():
        try:
            abs_path = Path(abs_path_str)
            # Ensure paths are stored relative to the project root if possible
            if abs_path.is_absolute() and project_root.is_absolute() and abs_path.is_relative_to(project_root):
                 relative_path_str = str(abs_path.relative_to(project_root))
            else:
                 relative_path_str = abs_path_str # Keep as is if not relative (should ideally not happen for tree items)
            relative_folder_states[relative_path_str] = state
        except ValueError: # Path is not relative to project_root
            relative_folder_states[abs_path_str] = state # Store absolute path as fallback
        except Exception as e:
            schedule_log_message(f"Error converting path '{abs_path_str}' for saving config: {e}", LOG_ERROR)

    config_to_save = {
        "folder_states": relative_folder_states,
        "dynamic_file_exclusions": sorted(list(dynamic_global_excluded_filenames))
    }

    try:
        with open(config_file_path, "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, indent=2)
        schedule_log_message(f"Project config saved: {config_file_path.name}", LOG_DEBUG)
    except IOError as e:
        schedule_log_message(f"Failed to save project config to {config_file_path}: {e}", LOG_ERROR)

def load_project_config(project_root: Path) -> dict[str, str]:
    """
    Loads project-specific configuration from its JSON file.

    This includes previously saved folder selection states and dynamic file exclusions.
    Paths are resolved to absolute paths based on the current project_root.

    Args:
        project_root: The Path object for the project's root directory.

    Returns:
        A dictionary mapping absolute folder path strings to their selection state
        (S_CHECKED or S_UNCHECKED). Returns an empty dictionary if no config is found
        or if loading fails.
    """
    global dynamic_global_excluded_filenames # Modifies this global set
    loaded_abs_folder_states: dict[str, str] = {}
    dynamic_global_excluded_filenames.clear() # Clear existing dynamic exclusions before loading
    # popup_exclusion_checkbox_vars is UI related, cleared when popup is built

    if not project_root or not project_root.is_dir():
        return loaded_abs_folder_states # No valid project root to load config for

    config_file_path = get_project_config_file_path(project_root)
    if not config_file_path or not config_file_path.exists():
        schedule_log_message(f"No project config file found for '{project_root.name}'. Using defaults.", LOG_DEBUG)
        return loaded_abs_folder_states

    try:
        with open(config_file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        relative_folder_states = config_data.get("folder_states", {})
        for rel_path_str, state in relative_folder_states.items():
            if state not in [S_CHECKED, S_UNCHECKED]:
                schedule_log_message(f"Invalid folder state '{state}' in config for '{rel_path_str}'. Skipping.", LOG_WARNING)
                continue
            try:
                # Attempt to resolve path relative to project_root first
                abs_path = project_root.joinpath(rel_path_str).resolve()
                loaded_abs_folder_states[str(abs_path)] = state
            except Exception: # If joinpath/resolve fails (e.g. rel_path_str was already absolute or invalid)
                try:
                    # Try interpreting rel_path_str as a potentially absolute path stored previously
                    potential_abs_path = Path(rel_path_str)
                    if potential_abs_path.is_absolute() and potential_abs_path.exists():
                        loaded_abs_folder_states[str(potential_abs_path)] = state
                    else:
                        schedule_log_message(f"Could not resolve folder path from config: '{rel_path_str}' for project '{project_root.name}'.", LOG_WARNING)
                except Exception as e_path_conv:
                    schedule_log_message(f"Error processing path from config '{rel_path_str}': {e_path_conv}", LOG_WARNING)

        loaded_exclusions = config_data.get("dynamic_file_exclusions", [])
        dynamic_global_excluded_filenames.update(loaded_exclusions)

        schedule_log_message(f"Project config loaded from {config_file_path.name}", LOG_INFO)
    except (IOError, json.JSONDecodeError) as e:
        schedule_log_message(f"Failed to load/parse project config {config_file_path}: {e}", LOG_ERROR)
        dynamic_global_excluded_filenames.clear() # Ensure clean state on error
        return {} # Return empty if loading failed critically
    return loaded_abs_folder_states

# --- 🌳 Folder Treeview Functions ---

def refresh_folder_tree_threaded(tree: ttk.Treeview, selected_root_path: Path):
    """
    Clears the tree, shows a 'Loading...' message, and starts a background
    thread to scan the directory, preventing the GUI from freezing.
    """
    # 1. IMMEDIATE FEEDBACK: Clear the tree and show a loading message.
    for i in tree.get_children():
        tree.delete(i)

    if not selected_root_path or not selected_root_path.is_dir():
        tree.insert("", "end", text="Error: Invalid project root path specified.", tags=('error_node',))
        return

    loading_iid = "loading_node"
    tree.insert("", "end", iid=loading_iid, text="⏳ Scanning project folder, please wait...", open=True)
    if app_state.get('root'):
        app_state['root'].update_idletasks() # Force the UI to update now

    # 2. LAUNCH BACKGROUND SCAN: Start the slow work on another thread.
    worker_thread = threading.Thread(
        target=_worker_build_tree_data,
        args=(tree, selected_root_path, loading_iid),
        daemon=True
    )
    worker_thread.start()

def _worker_build_tree_data(tree: ttk.Treeview, project_root: Path, loading_node_id: str):
    """
    [WORKER THREAD] Scans the filesystem and builds a thread-safe data structure
    representing the tree. Includes a timeout to handle very large directories.
    """
    start_time = time.time()
    tree_data = []
    folder_tree_item_states.clear()

    def ask_user_to_continue_safely() -> bool:
        """
        Posts a request to the main GUI thread to show a messagebox and waits for the result.
        Returns True if the user clicks 'Yes', False otherwise.
        """
        def _show_messagebox_and_get_result():
            root = app_state.get('root')
            try:
                user_wants_to_continue = messagebox.askyesno(
                    "Directory Scan Taking Long",
                    f"The directory scan has run for over {MAX_SCAN_TIME_SECONDS} seconds.\n"
                    "This can happen with very large projects or slow network drives.\n\n"
                    "Do you want to continue scanning?",
                    parent=root
                )
                scan_timeout_result_queue.put(user_wants_to_continue)
            except Exception as e:
                print(f"Error in messagebox callback: {e}")
                scan_timeout_result_queue.put(False)

        gui_queue.put(_show_messagebox_and_get_result)
        return scan_timeout_result_queue.get()

    try:
        persisted_states = load_project_config(project_root)

        def _scan_recursive(current_path: Path, parent_iid: str):
            nonlocal start_time
            if time.time() - start_time > MAX_SCAN_TIME_SECONDS:
                schedule_log_message(f"Scan timeout of {MAX_SCAN_TIME_SECONDS}s exceeded. Asking user...", LOG_WARNING)
                if not ask_user_to_continue_safely():
                    raise TimeoutError("User chose to abort the scan.")
                else:
                    schedule_log_message("User chose to continue. Resetting scan timer.", LOG_INFO)
                    start_time = time.time()

            try:
                dirs_to_process = sorted(
                    [item for item in current_path.iterdir() if item.is_dir()],
                    key=lambda x: x.name.lower()
                )
                for p in dirs_to_process:
                    path_str = str(p.resolve())
                    relative_path_str = str(p.relative_to(project_root))
                    initial_state = persisted_states.get(path_str, persisted_states.get(relative_path_str, S_CHECKED))
                    if p.name in EXCLUDED_FOLDERS and path_str not in persisted_states and relative_path_str not in persisted_states:
                        initial_state = S_UNCHECKED
                    folder_tree_item_states[path_str] = initial_state
                    folder_size_str = f" {format_display_size(get_folder_size_bytes(p))}"
                    tree_data.append({
                        "parent": parent_iid, "iid": path_str,
                        "text": f"{p.name}{folder_size_str}", "open": False
                    })
                    _scan_recursive(p, path_str)
            except (PermissionError, FileNotFoundError):
                 tree_data.append({
                    "parent": parent_iid, "iid": f"error_{current_path.name}_{parent_iid}",
                    "text": f"🚫 Error reading {current_path.name}", "open": False
                 })

        root_path_str = str(project_root.resolve())
        root_state = persisted_states.get(root_path_str, persisted_states.get(".", S_CHECKED))
        folder_tree_item_states[root_path_str] = root_state
        root_size_str = f" {format_display_size(get_folder_size_bytes(project_root))}"
        tree_data.append({
            "parent": "", "iid": root_path_str,
            "text": f"{project_root.name} (Project Root){root_size_str}", "open": True
        })
        _scan_recursive(project_root, root_path_str)

    except TimeoutError:
        schedule_log_message("Scan aborted by user due to timeout.", LOG_WARNING)
        tree_data.append({
            "parent": "", "iid": "timeout_error",
            "text": "⚠️ Scan Aborted by User (Timeout)", "open": True
        })
    except Exception as e:
        schedule_log_message(f"Critical error during directory scan: {e}", LOG_CRITICAL)
        tree_data = [{
            "parent": "", "iid": "scan_error",
            "text": f"CRITICAL: Failed to scan directory. {e}", "open": True
        }]

    def _populate_tree_on_main_thread():
        try:
            if tree.exists(loading_node_id):
                tree.delete(loading_node_id)
            for item_data in tree_data:
                try:
                    tree.insert(
                        item_data["parent"], "end", iid=item_data["iid"],
                        text=item_data["text"], open=item_data["open"]
                    )
                except tk.TclError:
                    pass
            root_path_str = str(project_root.resolve())
            if tree.exists(root_path_str):
                 refresh_tree_visuals(tree, root_path_str)
            schedule_log_message(f"Folder tree refreshed for: {project_root.name}", LOG_INFO)
        except Exception as e:
            schedule_log_message(f"Error populating tree from background thread: {e}", LOG_CRITICAL)

    gui_queue.put(_populate_tree_on_main_thread)

def refresh_tree_visuals(tree: ttk.Treeview, root_item_id: str):
    """
    Recursively updates the visual representation (glyphs) of tree items
    based on their current explicit and effective selection states.

    Args:
        tree: The ttk.Treeview widget.
        root_item_id: The IID of the root item from which to start refreshing.
    """
    def _update_node_visual_recursive(item_id_to_update, parent_effectively_unchecked):
        if not tree.exists(item_id_to_update) or 'error_node' in tree.item(item_id_to_update, 'tags'):
            return

        item_explicit_state = folder_tree_item_states.get(item_id_to_update, S_UNCHECKED) # Default to unchecked if not in map
        current_visual_glyph = ""
        node_is_effectively_unchecked_for_children = False # Will this node cause its children to be unchecked?

        if parent_effectively_unchecked or item_explicit_state == S_UNCHECKED:
            current_visual_glyph = GLYPH_UNCHECKED
            node_is_effectively_unchecked_for_children = True
        else: # Parent is checked AND this item is explicitly checked
            node_is_effectively_unchecked_for_children = False
            children = tree.get_children(item_id_to_update)
            if not children: # Leaf node that is effectively checked
                current_visual_glyph = GLYPH_CHECKED
            else:
                # Determine if all children are checked, some, or none (among those tracked)
                num_children_explicitly_checked = 0
                num_relevant_children = 0 # Count children that have an entry in folder_tree_item_states
                for child_id in children:
                    if child_id in folder_tree_item_states: # Only consider children we are tracking states for
                        num_relevant_children +=1
                        if folder_tree_item_states.get(child_id) == S_CHECKED:
                            num_children_explicitly_checked += 1

                if num_relevant_children == 0: # No trackable children (e.g. all are error nodes or similar)
                    current_visual_glyph = GLYPH_CHECKED # Treat as checked if it has no relevant children to uncheck it
                elif num_children_explicitly_checked == num_relevant_children:
                    current_visual_glyph = GLYPH_CHECKED # All relevant children are checked
                elif num_children_explicitly_checked == 0 and num_relevant_children > 0: # All relevant children are unchecked
                    current_visual_glyph = GLYPH_TRISTATE # Parent of all unchecked (was GLYPH_UNCHECKED, now TRISTATE for better visual)
                else: # Some checked, some unchecked (or some not tracked but at least one checked)
                    current_visual_glyph = GLYPH_TRISTATE

        # Reconstruct item text to include new glyph but preserve original name and size
        item_path = Path(item_id_to_update)
        name_component = item_path.name
        selected_root_str_var = app_state.get("selected_root_var")
        if selected_root_str_var:
            selected_root_str = selected_root_str_var.get()
            # Check if this is the root item of the tree
            if item_id_to_update == selected_root_str and tree.parent(item_id_to_update) == "":
                name_component = f"{item_path.name} (Project Root)"

        current_text_in_tree = tree.item(item_id_to_update, "text")
        size_suffix_to_preserve = ""
        # Heuristic to find existing size suffix like " (1.2 MB)" or " (size?)"
        last_open_paren_idx = current_text_in_tree.rfind(" (")
        if last_open_paren_idx != -1 and current_text_in_tree.endswith(")"):
            potential_size_content = current_text_in_tree[last_open_paren_idx+1:-1] # content inside parens
            is_a_size_indicator = False
            if potential_size_content == "size?":
                is_a_size_indicator = True
            else: # Check for "number UNIT" pattern
                parts = potential_size_content.split(" ")
                if len(parts) == 2 and parts[1] in ["B", "KB", "MB", "GB"]:
                    try:
                        float(parts[0]) # Check if first part is a number
                        is_a_size_indicator = True
                    except ValueError:
                        pass # Not a number
            if is_a_size_indicator:
                size_suffix_to_preserve = current_text_in_tree[last_open_paren_idx:]

        tree.item(item_id_to_update, text=f"{current_visual_glyph} {name_component}{size_suffix_to_preserve}")

        for child_id in tree.get_children(item_id_to_update):
            _update_node_visual_recursive(child_id, node_is_effectively_unchecked_for_children)

    if tree.exists(root_item_id): # Start recursion from the specified root item
        _update_node_visual_recursive(root_item_id, False) # Root item's parent is considered effectively checked

def on_tree_item_click(event):
    """Handles clicks on items in the folder Treeview to toggle their selection state."""
    tree = event.widget
    element_clicked = tree.identify_element(event.x, event.y)
    item_id = tree.identify_row(event.y) # Get the IID of the clicked row

    if not item_id or 'indicator' in element_clicked : # Click was on expand/collapse indicator, not item text
        return

    if item_id not in folder_tree_item_states:
        schedule_log_message(f"Clicked item '{Path(item_id).name}' not in state tracking. This might be an error node.", LOG_WARNING)
        return

    # Toggle the explicit state of the clicked item
    current_explicit_state = folder_tree_item_states[item_id]
    new_explicit_state = S_CHECKED if current_explicit_state == S_UNCHECKED else S_UNCHECKED
    folder_tree_item_states[item_id] = new_explicit_state

    # Refresh visuals starting from the project root to update all dependent glyphs
    project_root_iid_var = app_state.get('selected_root_var')
    if project_root_iid_var:
        project_root_iid_from_state = project_root_iid_var.get()
        if project_root_iid_from_state and tree.exists(project_root_iid_from_state):
            refresh_tree_visuals(tree, project_root_iid_from_state)
        else:
            current_tree_roots = tree.get_children("")
            schedule_log_message(
                f"Visual refresh issue in on_tree_item_click: "
                f"Expected root IID from app_state '{project_root_iid_from_state}' "
                f"was not found in tree. Current actual tree root(s): {current_tree_roots}.",
                LOG_WARNING
            )
            for top_level_item_iid in current_tree_roots:
                if tree.exists(top_level_item_iid):
                    refresh_tree_visuals(tree, top_level_item_iid)
    else:
        schedule_log_message("app_state['selected_root_var'] key not found for visual refresh.", LOG_CRITICAL)


# --- Effective Selection Logic ---
def is_path_effectively_selected(path_to_check: Path, project_root: Path) -> bool:
    """
    Determines if a given path is effectively selected based on the explicit
    selection states of itself and its ancestors in the folder_tree_item_states.

    A path is effectively selected if it and all its parent directories up to the
    project root are explicitly marked as 'checked'.

    Args:
        path_to_check: The Path object to check.
        project_root: The Path object of the current project root.

    Returns:
        True if the path is effectively selected, False otherwise.
    """
    current_path = path_to_check
    if project_root is None or not project_root.is_dir():
        return False # Cannot determine selection without a valid project root

    try: # Resolve paths to ensure consistent comparisons
        current_path = current_path.resolve()
        project_root = project_root.resolve()
    except Exception: # Path resolution failed (e.g. symlink loop, non-existent component)
        return False

    if current_path != project_root:
        try:
            current_path.relative_to(project_root)
        except ValueError: # path_to_check is not under project_root
            return False

    p = current_path
    while True:
        path_str = str(p)
        explicit_state = folder_tree_item_states.get(path_str)

        if explicit_state == S_UNCHECKED:
            return False # An uncheck anywhere in the chain means not selected

        if explicit_state is None and p != project_root:
            return False

        if p == project_root:
            return folder_tree_item_states.get(str(project_root), S_CHECKED) == S_CHECKED

        if p.parent == p: # Reached filesystem root
            break
        p = p.parent

    return False

# --- Filename Exclusion UI and Logic (Popup based) ---
def _populate_popup_exclusions_frame(scrollable_frame: tk.Frame, canvas: tk.Canvas) -> None:
    """Helper to populate the scrollable frame in the 'Manage Dynamic Exclusions' popup."""
    global popup_exclusion_checkbox_vars
    if not scrollable_frame or not canvas:
        return

    for widget in scrollable_frame.winfo_children(): # Clear previous content
        widget.destroy()
    popup_exclusion_checkbox_vars.clear()

    bg_color = scrollable_frame.cget("bg")
    fg_color = "#d0d0d0" # Light gray for text
    font_spec = (app_state.get("default_ui_font", "Arial"), 9)

    if not dynamic_global_excluded_filenames:
        no_exclusions_label = tk.Label(scrollable_frame, text="No dynamic filename exclusions set.",
                                     bg=bg_color, fg=fg_color, font=font_spec)
        no_exclusions_label.pack(pady=10, padx=5, anchor="w")
    else:
        sorted_exclusions = sorted(list(dynamic_global_excluded_filenames))
        for i, exclusion_text in enumerate(sorted_exclusions):
            var = tk.IntVar(value=0) # Checkboxes for removal selection, initially unchecked
            cb = tk.Checkbutton(scrollable_frame, text=exclusion_text, variable=var,
                                bg=bg_color, fg=fg_color, selectcolor="#2b2b2b", # Darker bg for checkmark area
                                activebackground="#3c3c3c", activeforeground="white",
                                font=font_spec, anchor="w",
                                highlightthickness=0, borderwidth=0)
            cb.grid(row=i, column=0, sticky="ew", padx=2, pady=1)
            scrollable_frame.grid_columnconfigure(0, weight=1) # Make checkbox text expand
            popup_exclusion_checkbox_vars[exclusion_text] = var

    scrollable_frame.update_idletasks() # Ensure frame size is calculated
    canvas.configure(scrollregion=canvas.bbox("all")) # Update scrollregion
    canvas.event_generate("<Configure>") # Force canvas update if needed

def manage_dynamic_exclusions_popup() -> None:
    """Creates and shows the popup window for managing dynamic filename exclusions."""
    global popup_exclusion_checkbox_vars # Accessed by helper and actions
    if not app_state.get('root'):
        schedule_log_message("Main window not ready for popup.", LOG_WARNING)
        return

    popup = tk.Toplevel(app_state['root'])
    popup.title("Manage Dynamic Exclusions")
    popup.geometry("660x400") # Initial size
    popup.configure(bg="#2b2b2b") # Dark background
    popup.minsize(400, 250)

    content_frame = tk.Frame(popup, bg="#2b2b2b", padx=10, pady=10)
    content_frame.pack(fill=tk.BOTH, expand=True)

    header_label = tk.Label(content_frame, text="Manage Dynamically Excluded Filename Patterns:",
                            bg="#2b2b2b", fg="white", font=(app_state.get("default_ui_font", "Arial"), 10, "bold"))
    header_label.pack(pady=(0, 10), anchor="w")

    # --- Scrollable area for exclusions ---
    canvas = tk.Canvas(content_frame, bg="#1e1e1e", highlightthickness=0) # Slightly darker for list bg
    scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg="#1e1e1e") # Frame inside canvas

    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    def _on_canvas_resize(event): # Adjust scrollable frame width to canvas width
        canvas.itemconfig(canvas_window, width=event.width)
    canvas.bind("<Configure>", _on_canvas_resize)

    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    # --- End scrollable area ---

    _populate_popup_exclusions_frame(scrollable_frame, canvas) # Initial population

    # --- Action buttons at the bottom ---
    action_button_frame = tk.Frame(content_frame, bg="#2b2b2b")
    action_button_frame.pack(fill=tk.X, pady=(10,0), side=tk.BOTTOM)

    def _remove_checked_from_popup():
        global dynamic_global_excluded_filenames # We are modifying this global
        removed_any = False
        to_remove = []
        for exclusion_text, var in popup_exclusion_checkbox_vars.items():
            if var.get() == 1: # If checkbox is checked
                to_remove.append(exclusion_text)

        if not to_remove:
            messagebox.showinfo("No Selection", "No exclusions checked for removal.", parent=popup)
            return

        actual_removed_count = 0
        for item in to_remove:
            if item in dynamic_global_excluded_filenames:
                dynamic_global_excluded_filenames.remove(item)
                schedule_log_message(f"Dynamically excluded filename pattern removed via popup: '{item}'", LOG_INFO)
                removed_any = True
                actual_removed_count += 1

        if removed_any:
            # Save the updated exclusions to project config
            project_root_path_str = app_state['selected_root_var'].get()
            if project_root_path_str:
                save_project_config(Path(project_root_path_str))

            _populate_popup_exclusions_frame(scrollable_frame, canvas) # Refresh the list in the popup
            messagebox.showinfo("Success", f"Removed {actual_removed_count} exclusion(s).", parent=popup)
        elif to_remove : # Items were checked but not found in the set (e.g. list out of sync somehow)
             messagebox.showwarning("Not Found", "Selected items were not found in current exclusion set. The list may be out of sync.", parent=popup)


    remove_button = tk.Button(action_button_frame, text="Remove Checked Items",
                              command=_remove_checked_from_popup,
                              bg="#c23621", fg="white", activebackground="#a02c1a", # Reddish for remove
                              relief=tk.FLAT, padx=10, width=20)
    remove_button.pack(side=tk.LEFT, padx=(0,10))

    close_button = tk.Button(action_button_frame, text="Close", command=popup.destroy,
                             bg="#4a4a5a", fg="white", activebackground="#5a5a6a", # Neutral
                             relief=tk.FLAT, padx=10, width=10)
    close_button.pack(side=tk.RIGHT)
    # --- End action buttons ---

    popup.transient(app_state['root']) # Keep popup on top of main window
    try: # Attempt to center the popup relative to the main window
        root_x = app_state['root'].winfo_x()
        root_y = app_state['root'].winfo_y()
        root_width = app_state['root'].winfo_width()
        root_height = app_state['root'].winfo_height()

        popup.update_idletasks() # Ensure popup dimensions are calculated
        popup_width = popup.winfo_width()
        popup_height = popup.winfo_height()

        position_x = root_x + (root_width // 2) - (popup_width // 2)
        position_y = root_y + (root_height // 2) - (popup_height // 2)

        if popup_width > 1 and popup_height > 1: # Check if dimensions are valid
             popup.geometry(f"{popup_width}x{popup_height}+{position_x}+{position_y}")
        else: # Fallback if dimensions are not yet calculated, use initial geometry again
             popup.geometry(f"660x400+{position_x}+{position_y}") # Recenter with default size

    except Exception as e_center:
        print(f"CONSOLE: Error centering dynamic exclusions popup: {e_center}") # Non-critical

    popup.grab_set() # Make the popup modal
    app_state['root'].wait_window(popup) # Wait for popup to be closed

def add_excluded_filename(entry_widget: tk.Entry) -> None:
    """Adds a filename/pattern from the entry widget to the dynamic global exclusions."""
    filename_pattern = entry_widget.get().strip()
    if filename_pattern:
        if filename_pattern not in dynamic_global_excluded_filenames:
            dynamic_global_excluded_filenames.add(filename_pattern)
            entry_widget.delete(0, tk.END) # Clear entry after adding
            schedule_log_message(f"Added dynamic filename exclusion: '{filename_pattern}'. Manage via 'Manage Dynamic Exclusions' popup.", LOG_INFO)

            # Save config after adding
            project_root_path_str = app_state.get('selected_root_var', tk.StringVar()).get()
            if project_root_path_str:
                save_project_config(Path(project_root_path_str))
        else:
            schedule_log_message(f"Filename exclusion '{filename_pattern}' is already in the dynamic list.", LOG_INFO)
    else:
        schedule_log_message(f"Filename exclusion entry is empty. Nothing added.", LOG_WARNING)

def should_exclude_file(filename: str) -> bool:
    """
    Checks if a given filename matches any of the predefined or dynamic exclusion patterns.

    Args:
        filename: The name of the file (not the full path).

    Returns:
        True if the file should be excluded, False otherwise.
    """
    all_exclusion_patterns = PREDEFINED_EXCLUDED_FILENAMES.union(dynamic_global_excluded_filenames)
    for pattern in all_exclusion_patterns:
        if not pattern: # Skip empty patterns if any
            continue
        if pattern.startswith("*."): # Wildcard extension match (e.g., "*.log")
            if filename.endswith(pattern[1:]):
                return True
        else: # Exact match
            if pattern == filename:
                return True
    return False

# --- Conda Related Functions ---
def _get_conda_executable_path() -> str | None:
    """
    Tries to find the conda executable path.
    Checks environment variable, 'where'/'which', and finally 'conda --version'.

    Returns:
        The path to the conda executable as a string, "conda" if callable generally,
        or None if not found.
    """
    try:
        # 1. Check CONDA_EXE environment variable
        conda_exe_env_var = os.environ.get('CONDA_EXE')
        if conda_exe_env_var and Path(conda_exe_env_var).is_file():
            return conda_exe_env_var

        # 2. Try 'where' on Windows or 'which' on other systems
        cmd = ["where", "conda"] if platform.system() == "Windows" else ["which", "conda"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, shell=False, timeout=3)
        output = proc.stdout.strip()
        if output:
            for line in output.splitlines():
                if Path(line).is_file() or "conda.bat" in line.lower() or "conda.exe" in line.lower():
                    return line
            if Path(output.splitlines()[0]).exists():
                 return output.splitlines()[0]

    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        try:
            use_shell_for_version_check = (platform.system() == "Windows")
            subprocess.run(["conda", "--version"], capture_output=True, text=True, check=True, shell=use_shell_for_version_check, timeout=3)
            return "conda"
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None

    return "conda"

def get_conda_environments(conda_executable: str) -> dict:
    """
    Lists available Conda environments using the provided conda executable.

    Args:
        conda_executable: The path to the conda executable or "conda".

    Returns:
        A dictionary with "names": list_of_env_names and "paths": {name: path_str}.
        Returns error indications in "names" if issues occur.
    """
    environments = {"names": [], "paths": {}}
    if not conda_executable:
        return {"names": ["No Conda Executable Provided"], "paths": {}}

    try:
        cmd_list = [conda_executable, "env", "list", "--json"]
        use_shell = (platform.system() == "Windows" and conda_executable.lower() == "conda")

        result = subprocess.run(cmd_list, capture_output=True, text=True, check=True, shell=use_shell, timeout=10)
        data = json.loads(result.stdout)

        envs_paths_list = data.get("envs", data.get("environments", []))
        active_env_path = os.environ.get("CONDA_PREFIX")
        root_conda_prefix = data.get("conda_prefix", data.get("root_prefix", os.environ.get("CONDA_ROOT_PREFIX")))

        processed_paths = set()
        for env_path_str in envs_paths_list:
            if env_path_str in processed_paths:
                continue
            processed_paths.add(env_path_str)

            env_path_obj = Path(env_path_str)
            env_name = "base" if env_path_str == root_conda_prefix else env_path_obj.name

            if env_path_str == active_env_path and not env_name.endswith(" (active)"):
                env_name = f"{env_name} (active)"

            base_name_without_active = env_name.replace(" (active)", "").strip()
            if "(active)" in env_name and base_name_without_active in environments["paths"]:
                 if base_name_without_active in environments["names"]:
                     environments["names"].remove(base_name_without_active)
                 environments["paths"].pop(base_name_without_active, None)

            if env_name not in environments["paths"]:
                 environments["names"].append(env_name)
                 environments["paths"][env_name] = env_path_str

        if root_conda_prefix and root_conda_prefix not in environments["paths"].values():
            base_name_to_add = "base (active)" if root_conda_prefix == active_env_path else "base"
            if base_name_to_add not in environments["paths"]:
                 environments["names"].append(base_name_to_add)
                 environments["paths"][base_name_to_add] = root_conda_prefix

        def sort_key_conda_envs(name):
            if "(active)" in name and name.startswith("base"): return "000"
            if name == "base": return "001"
            if "(active)" in name: return f"002_{name}"
            return f"100_{name}"

        environments["names"] = sorted(list(set(environments["names"])), key=sort_key_conda_envs)
        return environments

    except FileNotFoundError:
        return {"names": ["Conda Not Found"], "paths": {}}
    except subprocess.CalledProcessError as e:
        return {"names": ["Error Listing Conda"], "paths": {}}
    except (json.JSONDecodeError, KeyError, subprocess.TimeoutExpired) as e:
        return {"names": [f"Error Parsing Conda List: {type(e).__name__}"], "paths": {}}
    except Exception as e:
        return {"names": ["Unexpected Conda Error"], "paths": {}}

def load_conda_environments_into_app_state() -> None:
    """
    [WORKER THREAD] Fetches Conda environments and [MAIN THREAD] schedules a GUI update.
    """
    conda_exe = app_state.get("conda_executable")

    if not conda_exe:
        environments_data = {"names": ["No Conda Available"], "paths": {}}
    else:
        # This part runs in the background thread. It gets the data.
        raw_conda_envs = get_conda_environments(conda_exe) # This can be slow!

        valid_names = [name for name in raw_conda_envs.get("names", []) if name]

        error_indicators = ["No Conda Available", "Conda Not Found", "Error Listing Conda"]
        if not valid_names or any(indicator in valid_names for indicator in error_indicators):
            environments_data = {"names": ["No Conda Available"], "paths": {}}
            if valid_names and valid_names != ["No Conda Available"]:
                schedule_log_message(f"Conda env list could not be populated: {valid_names[0]}", LOG_WARNING)
        else:
            environments_data = {
                "names": ["Default (Active/None)"] + valid_names,
                "paths": raw_conda_envs.get("paths", {})
            }

    def _update_conda_combobox_on_main_thread():
        # Update the application state with the data we found.
        app_state["conda_env_names_list"] = environments_data["names"]
        app_state["conda_env_paths_map"] = environments_data["paths"]

        cb = app_state.get("conda_combobox")
        selected_var = app_state.get("selected_conda_env_var")

        if cb and selected_var:
            current_options = app_state["conda_env_names_list"]
            cb['values'] = current_options

            if current_options:
                selected_var.set(current_options[0])

            if current_options == ["No Conda Available"] or current_options == ["Checking Conda..."]:
                cb.config(state="disabled")
            else:
                cb.config(state="readonly")

            schedule_log_message("Conda environment list has been updated in the UI.", LOG_DEBUG)

    gui_queue.put(_update_conda_combobox_on_main_thread)


# --- 🧪 Core Action Implementations ---
def build_folder_tree_impl():
    """Generates a textual representation of the selected project folder tree and saves it to a file."""
    schedule_log_message("Starting: Build Folder Tree...", LOG_INFO)
    selected_root_path_str = app_state['selected_root_var'].get()
    if not selected_root_path_str:
        schedule_log_message("Project root not selected. Cannot build folder tree.", LOG_ERROR)
        return
    selected_root_path = Path(selected_root_path_str)
    if not selected_root_path.is_dir():
        schedule_log_message(f"Invalid project root path for tree: {selected_root_path}", LOG_ERROR)
        return

    output_dir = get_log_output_dir(selected_root_path, LOG_SUBDIR_TREE)
    if not output_dir:
        return
    output_file_path = output_dir / apply_timestamp("project_tree.txt")

    tree_lines = [
        f"Project Root: {selected_root_path}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Global Default Folder Exclusions: {', '.join(sorted(list(EXCLUDED_FOLDERS)))}",
        f"Predefined Filename Exclusions: {', '.join(sorted(list(PREDEFINED_EXCLUDED_FILENAMES)))}",
        f"Dynamic Filename Exclusions: {', '.join(sorted(list(dynamic_global_excluded_filenames))) if dynamic_global_excluded_filenames else 'None'}\n"
    ]

    def _generate_tree_recursive(current_dir: Path, prefix: str = ""):
        try:
            items_in_fs = sorted(
                list(current_dir.iterdir()),
                key=lambda x: (x.is_file(), x.name.lower())
            )
        except (PermissionError, FileNotFoundError):
            tree_lines.append(f"{prefix}└── 🚫 [Access Denied: {current_dir.name}]")
            return

        for i, item in enumerate(items_in_fs):
            is_last = (i == len(items_in_fs) - 1)
            connector = "└── " if is_last else "├── "

            if item.is_dir():
                is_eff_selected = is_path_effectively_selected(item, selected_root_path)
                log_glyph = GLYPH_CHECKED if is_eff_selected else GLYPH_UNCHECKED
                tree_lines.append(f"{prefix}{connector}{log_glyph} {item.name}/")
                if is_eff_selected:
                    _generate_tree_recursive(item, prefix + ("    " if is_last else "│   "))
            else: # It's a file
                if should_exclude_file(item.name):
                    continue
                if is_path_effectively_selected(item.parent, selected_root_path):
                    binary_indicator = " (Binary)" if is_binary(item) else ""
                    tree_lines.append(f"{prefix}{connector}📄 {item.name}{binary_indicator}")

    root_eff_selected = is_path_effectively_selected(selected_root_path, selected_root_path)
    root_log_glyph = GLYPH_CHECKED if root_eff_selected else GLYPH_UNCHECKED
    tree_lines.append(f"{root_log_glyph} {selected_root_path.name}/ (Project Root)")

    if root_eff_selected:
        _generate_tree_recursive(selected_root_path, "  ")

    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(tree_lines))
        relative_log_path = output_file_path.relative_to(selected_root_path.parent) if selected_root_path.parent != selected_root_path else output_file_path
        schedule_log_message(f"Project tree map saved to {relative_log_path}", LOG_INFO)
    except (IOError, ValueError) as e:
        schedule_log_message(f"Error saving project tree map: {e}", LOG_ERROR)

    schedule_log_message("Finished: Build Folder Tree.", LOG_INFO)


def dump_files_impl():
    """Dumps the content of selected, non-binary files into a single text file."""
    schedule_log_message("Starting: Dump Source Files...", LOG_INFO)
    selected_root_path_str = app_state['selected_root_var'].get()
    if not selected_root_path_str:
        schedule_log_message("Project root not selected. Cannot dump files.", LOG_ERROR)
        return
    selected_root_path = Path(selected_root_path_str)
    if not selected_root_path.is_dir():
        schedule_log_message(f"Invalid project root path for file dump: {selected_root_path}", LOG_ERROR)
        return

    output_dir = get_log_output_dir(selected_root_path, LOG_SUBDIR_DUMP)
    if not output_dir:
        return
    output_file_path = output_dir / apply_timestamp("project_file_dump.txt")

    dump_content = [
        f"File Dump from Project: {selected_root_path}\n",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    ]
    files_dumped_count = 0
    max_dump_file_size = 1 * 1024 * 1024  # 1 MB limit per file content

    for root_str, dir_names_orig, file_names in os.walk(selected_root_path, topdown=True):
        current_scan_dir = Path(root_str)

        dir_names_orig[:] = [
            d_name for d_name in dir_names_orig
            if (current_scan_dir / d_name).name not in EXCLUDED_FOLDERS and \
               is_path_effectively_selected(current_scan_dir / d_name, selected_root_path)
        ]

        if not is_path_effectively_selected(current_scan_dir, selected_root_path):
            continue

        for file_name in file_names:
            file_path = current_scan_dir / file_name
            if should_exclude_file(file_name):
                continue

            relative_file_path = file_path.relative_to(selected_root_path)
            file_header = f"\n{'-'*20} FILE: {relative_file_path} {'-'* (max(0, 60 - len(str(relative_file_path))))}\n"
            omitted_footer = f"\n{'-'*80}\n"

            try:
                if file_path.stat().st_size > max_dump_file_size:
                    dump_content.extend([file_header, f"[CONTENT OMITTED: File size > {max_dump_file_size // (1024*1024)}MB]\n", omitted_footer])
                    continue

                if is_binary(file_path):
                    dump_content.extend([file_header, "[CONTENT OMITTED: Detected as binary]\n", omitted_footer])
                    continue

                dump_content.append(file_header)
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                dump_content.append(content)
                dump_content.append(omitted_footer)
                files_dumped_count += 1
            except Exception as e:
                dump_content.extend([file_header, f"[CONTENT OMITTED: Error during processing - {e}]\n", omitted_footer])

    if files_dumped_count > 0:
        try:
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write("".join(dump_content))
            relative_log_path = output_file_path.relative_to(selected_root_path.parent) if selected_root_path.parent != selected_root_path else output_file_path
            schedule_log_message(f"{files_dumped_count} file sections processed, saved to {relative_log_path}", LOG_INFO)
        except (IOError, ValueError) as e:
            schedule_log_message(f"Error saving file dump: {e}", LOG_ERROR)
    else:
        schedule_log_message("No text files were selected or found to dump.", LOG_INFO)

    schedule_log_message("Finished: Dump Source Files.", LOG_INFO)


def _execute_conda_commands(commands: dict, audit_text_list: list, conda_executable: str):
    """ Helper function to execute a dictionary of Conda commands. """
    for desc, cmd_list_stub in commands.items():
        audit_text_list.append(f"\n--- {desc} ---\n")
        actual_cmd = [conda_executable] + cmd_list_stub
        try:
            use_shell = (platform.system() == "Windows" and conda_executable.lower() == "conda")
            result = subprocess.run(
                actual_cmd, text=True, capture_output=True, check=False,
                shell=use_shell, timeout=45
            )
            if result.stdout: audit_text_list.append(result.stdout)
            if result.stderr: audit_text_list.append(f"Stderr:\n{result.stderr}")
        except Exception as e:
            audit_text_list.append(f"An unexpected error occurred: {e}\n")


def audit_conda_impl():
    """Audits Conda environment information based on UI selection and saves it to a file."""
    schedule_log_message("Starting: Audit Conda Environment...", LOG_INFO)
    selected_root_path_str = app_state['selected_root_var'].get()
    if not selected_root_path_str:
        schedule_log_message("Project root not selected.", LOG_ERROR)
        return
    selected_root_path = Path(selected_root_path_str)

    output_dir = get_log_output_dir(selected_root_path, LOG_SUBDIR_CONDA)
    if not output_dir: return
    output_file_path = output_dir / apply_timestamp("conda_audit.txt")

    conda_executable = app_state.get("conda_executable")
    selected_env_name = app_state.get("selected_conda_env_var", tk.StringVar()).get()

    audit_text = [f"Conda Environment Audit - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"]
    audit_text.append(f"Selected UI Option: '{selected_env_name}'\n")
    audit_text.append(f"Using Conda: '{conda_executable or 'Not Found'}'\n")

    commands_to_run = {}
    if not conda_executable or selected_env_name == "No Conda Available":
        audit_text.append("Conda not available or configured.\n")
    elif selected_env_name == "Default (Active/None)" or not selected_env_name:
        commands_to_run = {
            "Conda Info": ["info"], "Conda Environments": ["env", "list"],
            "Active Env Packages": ["list"]
        }
    else:
        env_name_for_cmd = selected_env_name.replace(" (active)", "").strip()
        commands_to_run = {
            "Conda Info": ["info"], "Conda Environments": ["env", "list"],
            f"Packages in '{env_name_for_cmd}'": ["list", "-n", env_name_for_cmd]
        }

    if commands_to_run and conda_executable:
        _execute_conda_commands(commands_to_run, audit_text, conda_executable)

    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write("".join(audit_text))
        relative_log_path = output_file_path.relative_to(selected_root_path.parent) if selected_root_path.parent != selected_root_path else output_file_path
        schedule_log_message(f"Conda audit report saved to {relative_log_path}", LOG_INFO)
    except (IOError, ValueError) as e:
        schedule_log_message(f"Failed to save Conda audit report: {e}", LOG_ERROR)

    schedule_log_message("Finished: Audit Conda Environment.", LOG_INFO)

def audit_system_impl():
    """Audits general system information and current Python environment, saving to a file."""
    schedule_log_message("Starting: Audit System Information...", LOG_INFO)
    selected_root_path_str = app_state['selected_root_var'].get()
    selected_root_path = Path(selected_root_path_str) if selected_root_path_str else APP_DIR

    output_dir = get_log_output_dir(selected_root_path, LOG_SUBDIR_SYSTEM)
    if not output_dir: return
    output_file_path = output_dir / apply_timestamp("system_audit.txt")

    info = [
        f"System Audit - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Platform: {platform.system()} {platform.release()} ({platform.machine()})",
        f"Hostname: {platform.node()}",
        f"Processor: {platform.processor() or 'N/A'}",
        "\n--- Python Environment (This Script) ---\n",
        f"Python Version: {platform.python_version()}",
        f"Python Executable: {sys.executable}",
    ]

    info.append("\n--- pip freeze ---\n")
    try:
        pip_cmd = [sys.executable, "-m", "pip", "freeze"]
        result = subprocess.run(pip_cmd, text=True, capture_output=True, check=True)
        info.append(result.stdout)
    except Exception as e:
        info.append(f"Could not run 'pip freeze': {e}\n")

    try:
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(info))
        relative_log_path = output_file_path.relative_to(selected_root_path.parent) if selected_root_path.parent != selected_root_path else output_file_path
        schedule_log_message(f"System audit report saved to {relative_log_path}", LOG_INFO)
    except (IOError, ValueError) as e:
        schedule_log_message(f"Failed to save system audit report: {e}", LOG_ERROR)

    schedule_log_message("Finished: Audit System Information.", LOG_INFO)


def backup_project_impl():
    """Creates a tar.gz backup of the selected files and folders in the project."""
    schedule_log_message("Starting: Backup Project...", LOG_INFO)
    selected_root_path_str = app_state['selected_root_var'].get()
    if not selected_root_path_str:
        schedule_log_message("Project root not selected.", LOG_ERROR)
        return
    selected_root_path = Path(selected_root_path_str)
    if not selected_root_path.is_dir():
        schedule_log_message(f"Invalid project root path for backup: {selected_root_path}", LOG_ERROR)
        return

    output_dir = get_log_output_dir(selected_root_path, LOG_SUBDIR_BACKUP)
    if not output_dir: return

    backup_filename_base = f"{selected_root_path.name}_backup"
    backup_file_path = output_dir / apply_timestamp(f"{backup_filename_base}.tar.gz")

    files_added_count = 0
    try:
        with tarfile.open(backup_file_path, "w:gz") as tar:
            if not is_path_effectively_selected(selected_root_path, selected_root_path):
                schedule_log_message("Project root not selected. Backup will be empty.", LOG_INFO)
            else:
                for root_str, dir_names_orig, file_names in os.walk(selected_root_path, topdown=True):
                    current_scan_dir = Path(root_str)
                    dir_names_orig[:] = [d for d in dir_names_orig if is_path_effectively_selected(current_scan_dir / d, selected_root_path)]
                    if not is_path_effectively_selected(current_scan_dir, selected_root_path): continue

                    for file_name in file_names:
                        if should_exclude_file(file_name): continue
                        file_path = current_scan_dir / file_name
                        arcname = file_path.relative_to(selected_root_path)
                        tar.add(file_path, arcname=arcname)
                        files_added_count += 1

        if files_added_count > 0:
            relative_log_path = backup_file_path.relative_to(selected_root_path.parent) if selected_root_path.parent != selected_root_path else backup_file_path
            schedule_log_message(f"Project backup created: {relative_log_path} ({files_added_count} files).", LOG_INFO)
        else:
            schedule_log_message("No files were added to the backup.", LOG_WARNING)
            if backup_file_path.exists() and backup_file_path.stat().st_size < 100:
                os.remove(backup_file_path)
                schedule_log_message(f"Removed empty backup file: {backup_file_path.name}", LOG_INFO)

    except (IOError, tarfile.TarError, FileNotFoundError, ValueError) as e:
        schedule_log_message(f"Error creating project backup: {e}", LOG_ERROR)

    schedule_log_message("Finished: Backup Project.", LOG_INFO)


def save_app_log_impl():
    """Saves the content of the in-app log display to a session log file."""
    schedule_log_message("Starting: Save App Session Log...", LOG_INFO)
    selected_root_path_str = app_state.get('selected_root_var', tk.StringVar()).get()
    selected_root_path = Path(selected_root_path_str) if selected_root_path_str and Path(selected_root_path_str).is_dir() else APP_DIR

    output_dir = get_log_output_dir(selected_root_path, LOG_SUBDIR_SESSION)
    if not output_dir: return
    output_file_path = output_dir / apply_timestamp("projectMAPPER_session_log.txt")

    log_box = app_state.get('log_box')
    if not log_box: return

    try:
        log_content = log_box.get("1.0", tk.END)
        if not log_content.strip():
            schedule_log_message("App Log is empty. Nothing to save.", LOG_INFO)
            return
        with open(output_file_path, "w", encoding="utf-8") as f:
            f.write(log_content)
        relative_log_path = output_file_path.relative_to(selected_root_path.parent) if selected_root_path.parent != selected_root_path else output_file_path
        schedule_log_message(f"App session log saved to {relative_log_path}", LOG_INFO)

    except (tk.TclError, IOError, ValueError) as e:
        schedule_log_message(f"Error saving app session log: {e}", LOG_ERROR)

    schedule_log_message("Finished: Save App Session Log.", LOG_INFO)


def open_main_log_directory():
    """Opens the main '_logs' directory of the current project in the system's file explorer."""
    schedule_log_message("Attempting to open main Log Directory...", LOG_INFO)
    selected_root_path_str = app_state.get('selected_root_var', tk.StringVar()).get()
    main_log_dir_to_open = None

    if selected_root_path_str and Path(selected_root_path_str).is_dir():
        main_log_dir_to_open = get_log_output_dir(Path(selected_root_path_str), sub_dir_key=None, ensure_exists=True)
    else:
        fallback_log_dir = APP_DIR / "_projectMAPPER_fallback_logs"
        if fallback_log_dir.is_dir():
            main_log_dir_to_open = fallback_log_dir
        else:
            schedule_log_message("No project root and no fallback log directory found.", LOG_ERROR)
            return

    if not main_log_dir_to_open or not main_log_dir_to_open.is_dir():
        schedule_log_message("Could not access a valid main log directory.", LOG_ERROR)
        return

    try:
        if platform.system() == "Windows": os.startfile(str(main_log_dir_to_open))
        elif platform.system() == "Darwin": subprocess.run(["open", str(main_log_dir_to_open)])
        else: subprocess.run(["xdg-open", str(main_log_dir_to_open)])
    except Exception as e:
        schedule_log_message(f"Error opening log directory {main_log_dir_to_open}: {e}", LOG_ERROR)

# --- Threading & GUI Update Utilities ---
def run_threaded_action(target_function_impl, save_config_after=False):
    """
    Runs a target function in a separate daemon thread to prevent GUI freezing.
    """
    def thread_target_wrapper():
        try:
            target_function_impl()
            if save_config_after:
                project_root_path_str = app_state.get('selected_root_var', tk.StringVar()).get()
                if project_root_path_str and Path(project_root_path_str).is_dir():
                    save_project_config(Path(project_root_path_str))
        except Exception as e:
            error_msg = f"CRITICAL THREAD ERROR in {target_function_impl.__name__}: {e}"
            schedule_log_message(error_msg, LOG_CRITICAL)
            import traceback
            schedule_log_message(traceback.format_exc(), LOG_DEBUG)

    action_thread = threading.Thread(target=thread_target_wrapper, daemon=True)
    action_thread.start()

def process_gui_queue():
    """Processes callbacks from the gui_queue to update Tkinter UI elements from threads."""
    while not gui_queue.empty():
        try:
            callback = gui_queue.get_nowait()
            callback()
        except queue.Empty:
            pass
        except Exception as e:
            print(f"CONSOLE DEBUG: Error during GUI queue callback processing: {e}")
    if app_state.get('root') and app_state['root'].winfo_exists():
        app_state['root'].after(100, process_gui_queue)

# --- Initial Dependency Checks ---
def check_initial_dependencies_and_load_conda() -> None:
    """
    Performs initial checks (like Conda availability) on startup.
    Loads Conda environments into app_state for the UI.
    """
    app_state["conda_executable"] = _get_conda_executable_path()

    if app_state["conda_executable"]:
        schedule_log_message(f"Using Conda executable found at/as: {app_state['conda_executable']}", LOG_INFO)
        app_state['conda_initially_found_basic'] = True
    else:
        schedule_log_message("Conda executable not found. Conda features will be unavailable.", LOG_WARNING)
        app_state['conda_initially_found_basic'] = False

    load_conda_environments_into_app_state()

# ==============================================================================
# --- Main Application Setup & GUI ---
# ==============================================================================
def main() -> None:
    """Sets up and runs the main ProjectMAPPER Tkinter application."""

    root = tk.Tk()
    app_state['root'] = root
    app_state["selected_conda_env_var"] = tk.StringVar()
    app_state["selected_conda_env_var"].set("Checking Conda...")

    # --- UI Styling ---
    style = ttk.Style()
    try:
        if "clam" in style.theme_names(): style.theme_use("clam")
    except tk.TclError:
        pass # Ignore theme errors on some systems

    default_ui_font_family = "Arial"
    if "Segoe UI" in tkFont.families(): default_ui_font_family = "Segoe UI"
    app_state["default_ui_font"] = default_ui_font_family
    label_font = (default_ui_font_family, 10)
    button_font = (default_ui_font_family, 10, "bold")
    entry_font = (default_ui_font_family, 10)
    tree_font = (default_ui_font_family, 11)

    root.title(f"Project Mapper v{SCRIPT_VERSION}")
    root.configure(bg="#1e1e2f")
    root.geometry("1200x900")

    style.configure("Treeview", background="#252526", foreground="lightgray", fieldbackground="#252526",
                    font=tree_font, rowheight=tkFont.Font(font=tree_font).metrics("linespace") + 8)
    style.map("Treeview", background=[('selected', '#007ACC')])
    style.configure("Treeview.Heading", background="#333333", foreground="white", font=(default_ui_font_family, 10, 'bold'))

    # --- Control Bar ---
    control_bar_frame = tk.Frame(root, bg="#1e1e2f", padx=10) 
    control_bar_frame.pack(fill=tk.X, pady=(8, 4)) 

    tk.Label(control_bar_frame, text="Project Root:", bg="#1e1e2f", fg="white", font=label_font).pack(side=tk.LEFT)
    current_project_root_var = tk.StringVar()
    app_state['selected_root_var'] = current_project_root_var
    initial_dir_to_set = DEFAULT_ROOT_DIR if DEFAULT_ROOT_DIR.is_dir() else Path.cwd()
    current_project_root_var.set(str(initial_dir_to_set))

    project_path_entry = tk.Entry(control_bar_frame, textvariable=current_project_root_var,
                                  bg="#2a2a3f", fg="lightblue", relief=tk.FLAT, font=entry_font, insertbackground="white")
    project_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
    app_state['project_path_entry'] = project_path_entry

    def validate_and_refresh_project_root(event=None):
        path_str = current_project_root_var.get()
        entry_widget = app_state['project_path_entry']
        path_obj = Path(path_str) if path_str else None
        tree_widget = app_state['folder_tree']

        if path_obj and path_obj.is_dir():
            entry_widget.config(fg=app_state['project_path_entry_normal_fg'])
            if tree_widget:
                refresh_folder_tree_threaded(tree_widget, path_obj)
            save_project_config(path_obj)
        else:
            entry_widget.config(fg=app_state['project_path_entry_error_fg'])
            schedule_log_message(f"Invalid project root: '{path_str}'.", LOG_ERROR)
            if tree_widget:
                for i in tree_widget.get_children(): tree_widget.delete(i)
                tree_widget.insert("", "end", text="Invalid project root path specified.", tags=('error_node',))

    project_path_entry.bind("<Return>", validate_and_refresh_project_root)
    project_path_entry.bind("<FocusOut>", validate_and_refresh_project_root)

    def _on_choose_project_directory():
        new_dir = filedialog.askdirectory(initialdir=current_project_root_var.get(), title="Select Project Root")
        if new_dir:
            current_project_root_var.set(new_dir)
            validate_and_refresh_project_root()

    choose_dir_button = tk.Button(control_bar_frame, text="Choose...", command=_on_choose_project_directory,
                                  bg="#4a4a5a", fg="white", activebackground="#5a5a6a",
                                  relief=tk.FLAT, font=button_font, padx=10)
    choose_dir_button.pack(side=tk.RIGHT)

    # --- Main Paned Window ---
    main_paned_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL, style="Horizontal.TPanedwindow")
    main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

    # --- Left Panel ---
    left_panel_base_frame = tk.Frame(main_paned_window, bg="#1e1e2f")
    folder_tree_container = tk.Frame(left_panel_base_frame, bg="#252526")
    folder_tree_container.pack(fill=tk.BOTH, expand=True)

    folder_tree = ttk.Treeview(folder_tree_container, show="tree", selectmode="none")
    folder_tree_yscroll = ttk.Scrollbar(folder_tree_container, orient="vertical", command=folder_tree.yview)
    folder_tree_xscroll = ttk.Scrollbar(folder_tree_container, orient="horizontal", command=folder_tree.xview)
    folder_tree.configure(yscrollcommand=folder_tree_yscroll.set, xscrollcommand=folder_tree_xscroll.set)
    folder_tree_yscroll.pack(side=tk.RIGHT, fill=tk.Y)
    folder_tree_xscroll.pack(side=tk.BOTTOM, fill=tk.X)
    folder_tree.pack(fill=tk.BOTH, expand=True)
    app_state['folder_tree'] = folder_tree
    folder_tree.bind("<ButtonRelease-1>", on_tree_item_click)

    # ... (Exclusion input frame setup remains the same)
    global_file_exclusions_frame = tk.Frame(left_panel_base_frame, bg="#252526", pady=5)
    global_file_exclusions_frame.pack(side=tk.BOTTOM, fill=tk.X)
    tk.Label(global_file_exclusions_frame, text="Add Dynamic Filename Exclusion:", bg="#252526", fg="lightgray").pack(padx=5)
    input_frame = tk.Frame(global_file_exclusions_frame, bg="#252526")
    input_frame.pack(fill=tk.X, padx=5, pady=(2,0))
    filename_exclusion_entry = tk.Entry(input_frame, bg="#3a3a4a", fg="lightblue", relief=tk.FLAT)
    filename_exclusion_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,4))
    filename_exclusion_entry.bind("<Return>", lambda e, entry=filename_exclusion_entry: add_excluded_filename(entry))
    tk.Button(input_frame, text="Add", command=lambda e=filename_exclusion_entry: add_excluded_filename(e),
              bg="#007ACC", fg="white", relief=tk.FLAT).pack(side=tk.LEFT)

    main_paned_window.add(left_panel_base_frame, weight=1)

    # --- Right Panel ---
    right_panel_frame = tk.Frame(main_paned_window, bg="#1e1e2f")
    action_buttons_frame = tk.Frame(right_panel_frame, bg="#1e1e2f")
    action_buttons_frame.pack(fill=tk.X, padx=5, pady=5)

    # Action Buttons
    main_action_font = (default_ui_font_family, 14, "bold")
    buttons = [
        ("Map Project Tree", lambda: run_threaded_action(build_folder_tree_impl, True)),
        ("Dump Source Files", lambda: run_threaded_action(dump_files_impl, True)),
        ("Audit System Info", lambda: run_threaded_action(audit_system_impl)),
        ("Backup Project", lambda: run_threaded_action(backup_project_impl, True)),
    ]
    for i, (text, cmd) in enumerate(buttons):
        b = tk.Button(action_buttons_frame, text=text, command=cmd, bg="#007ACC", fg="white", font=main_action_font, relief=tk.FLAT, pady=6)
        b.grid(row=i//2, column=i%2, padx=5, pady=3, sticky="ew")
        action_buttons_frame.grid_columnconfigure(i%2, weight=1)

    # Conda Audit Section
    conda_audit_frame = tk.Frame(action_buttons_frame, bg="#1e1e2f")
    conda_audit_frame.grid(row=len(buttons)//2, column=0, columnspan=2, sticky='ew', pady=3)
    conda_audit_frame.grid_columnconfigure(0, weight=1)

    conda_env_combobox = ttk.Combobox(conda_audit_frame, textvariable=app_state["selected_conda_env_var"],
                                      values=["Checking Conda..."], state="disabled", font=entry_font)
    conda_env_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
    app_state["conda_combobox"] = conda_env_combobox

    tk.Button(conda_audit_frame, text="Audit Conda", command=lambda: run_threaded_action(audit_conda_impl),
              bg="#007ACC", fg="white", font=(default_ui_font_family, 11, "bold"), relief=tk.FLAT).pack(side=tk.RIGHT, padx=5)

    # Utility Buttons
    utility_frame = tk.Frame(right_panel_frame, bg="#1e1e2f")
    utility_frame.pack(fill=tk.X, padx=5, pady=(5,0))
    util_buttons = [
        ("Save App Log", lambda: run_threaded_action(save_app_log_impl)),
        ("Open Log Dir", open_main_log_directory),
        ("Manage Exclusions", manage_dynamic_exclusions_popup),
    ]
    for i, (text, cmd) in enumerate(util_buttons):
        b = tk.Button(utility_frame, text=text, command=cmd, bg="#4a4a5a", fg="white", relief=tk.FLAT, pady=4)
        b.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        utility_frame.grid_columnconfigure(i, weight=1)


    # Log Output
    log_output_scrolledtext = scrolledtext.ScrolledText(right_panel_frame, bg="#151521", fg="#E0E0E0",
                                                        relief=tk.FLAT, state=tk.DISABLED, wrap=tk.WORD,
                                                        font=("Courier New", 10))
    log_output_scrolledtext.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    app_state['log_box'] = log_output_scrolledtext
    main_paned_window.add(right_panel_frame, weight=2)

    # --- Status Bar ---
    status_bar_variable = tk.StringVar(value="[INITIALIZING] Application starting...")
    app_state['status_var'] = status_bar_variable
    tk.Label(root, textvariable=status_bar_variable, bg="#111111", fg="#90EE90", anchor="w", padx=10).pack(fill=tk.X, side=tk.BOTTOM)

    # --- Startup Tasks ---
    def start_background_tasks():
        conda_check_thread = threading.Thread(target=check_initial_dependencies_and_load_conda, daemon=True)
        conda_check_thread.start()
        schedule_log_message("Started background check for Conda environments...", LOG_DEBUG)

    root.after(100, lambda: validate_and_refresh_project_root())
    root.after(200, start_background_tasks)
    root.after(300, lambda: schedule_log_message(f"Project Mapper v{SCRIPT_VERSION} loaded. Ready.", LOG_INFO))

    process_gui_queue()
    root.mainloop()

if __name__ == "__main__":
    main()