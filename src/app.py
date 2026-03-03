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
    ".db", ".sqlite", ".mdb", ".accdb", ".dat", ".idx", ".pickle", ".joblib",
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
        self.top.configure(bg="#252526")
        self.top.transient(parent)
        self.top.grab_set()
        
        self.top.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        self.on_cancel = on_cancel
        self.is_cancelled = False

        # UI Elements
        lbl = tk.Label(self.top, text=f"{title}...", fg="white", bg="#252526", font=("Arial", 12, "bold"))
        lbl.pack(pady=10)

        self.log_display = scrolledtext.ScrolledText(self.top, height=10, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
        self.log_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_frame = tk.Frame(self.top, bg="#252526")
        btn_frame.pack(fill=tk.X, pady=10)

        self.cancel_btn = tk.Button(btn_frame, text="CANCEL OPERATION", bg="#c23621", fg="white", 
                                    font=("Arial", 10, "bold"), command=self.trigger_cancel)
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
        img_u.put(("#808080",), to=(0, 0, 14, 1))    # Top border
        img_u.put(("#808080",), to=(0, 13, 14, 14))  # Bottom border
        img_u.put(("#808080",), to=(0, 0, 1, 14))    # Left border
        img_u.put(("#808080",), to=(13, 0, 14, 14))  # Right border
        self.icon_imgs[S_UNCHECKED] = img_u

        # 2. Checked Icon (Blue Fill, White Checkmarkish shape)
        img_c = tk.PhotoImage(width=14, height=14)
        img_c.put(("#007ACC",), to=(0, 0, 14, 14))   # Blue Background
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
        img_f.put(("#808080",), to=(4, 4, 10, 5))
        img_f.put(("#808080",), to=(4, 7, 10, 8))
        img_f.put(("#808080",), to=(4, 10, 8, 11))
        self.icon_imgs["file"] = img_f

    # --- UI Setup ---
    def _setup_styles(self):
        style = ttk.Style()
        if "clam" in style.theme_names(): style.theme_use("clam")
        
        self.default_ui_font = "Arial"
        if "DejaVu Sans" in tkFont.families(): self.default_ui_font = "DejaVu Sans"

        tree_font = tkFont.Font(family=self.default_ui_font, size=11)
        
        self.widgets['tree_bg_normal'] = "#252526"
        self.widgets['tree_bg_disabled'] = "#3a3a3a"
        
        style.configure("Treeview", background=self.widgets['tree_bg_normal'], 
                        foreground="lightgray", fieldbackground=self.widgets['tree_bg_normal'],
                        borderwidth=0, font=tree_font, rowheight=24)
        style.map("Treeview", background=[('selected', '#007ACC')], foreground=[('selected', 'white')])
        style.configure("Treeview.Heading", background="#333333", foreground="white", relief=tk.FLAT)
        
        style.configure('TCombobox', fieldbackground='#2a2a3f', background='#4a4a5a', foreground='white')

    def _setup_ui(self):
        self.root.title("Project Mapper - Systems Thinker Edition")
        self.root.configure(bg="#1e1e2f")
        self.root.geometry("1200x850")

        # 1. Top Bar
        top_frame = tk.Frame(self.root, bg="#1e1e2f")
        top_frame.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(top_frame, text="Project Root:", bg="#1e1e2f", fg="white").pack(side=tk.LEFT)
        
        self.widgets['selected_root_var'] = tk.StringVar(value=str(DEFAULT_ROOT_DIR))
        self.widgets['project_path_entry'] = tk.Entry(top_frame, textvariable=self.widgets['selected_root_var'], 
                                                      bg="#2a2a3f", fg="lightblue", width=60)
        self.widgets['project_path_entry'].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.widgets['project_path_entry'].bind("<Return>", self._on_project_root_commit)

        tk.Button(top_frame, text="Choose...", command=self._on_choose_project_directory, bg="#4a4a5a", fg="white").pack(side=tk.RIGHT)
        tk.Button(top_frame, text="↑", command=self._on_click_up_dir, bg="#4a4a5a", fg="white").pack(side=tk.RIGHT, padx=5)

        # 2. Main Split (Changed to VERTICAL for pythonw layout stability)
        paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Top Pane: Tree
        left_frame = tk.Frame(paned, bg="#1e1e2f")
        self.widgets['folder_tree'] = ttk.Treeview(left_frame, show="tree", columns=("size"), selectmode="none")
        self.widgets['folder_tree'].column("#0", width=800)
        self.widgets['folder_tree'].column("size", width=100, anchor="e")
        self.widgets['folder_tree'].heading("size", text="Size")
        
        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=self.widgets['folder_tree'].yview)
        self.widgets['folder_tree'].configure(yscrollcommand=vsb.set)
        
        self.widgets['folder_tree'].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.widgets['folder_tree'].bind("<ButtonRelease-1>", self.on_tree_item_click)
        
        paned.add(left_frame, weight=3) # Give tree more initial weight

        # Bottom Pane: Actions & Logs
        right_frame = tk.Frame(paned, bg="#1e1e2f")
        
        # Action Buttons Grid
        btn_grid = tk.Frame(right_frame, bg="#1e1e2f")
        btn_grid.pack(fill=tk.X, pady=5)
        
        self.widgets['buttons'] = {}
        actions = [
            ("Map Project Tree", self.build_folder_tree_impl, True),
            ("Dump Source Files", self.dump_files_impl, True),
            ("Backup Project (Zip)", self.backup_project_impl, True),
            ("Audit System Info", self.audit_system_impl, False)
        ]

        for idx, (lbl, func, save) in enumerate(actions):
            r, c = divmod(idx, 4) # Spread buttons horizontally
            b = tk.Button(btn_grid, text=lbl, bg="#007ACC", fg="white", font=("Arial", 11, "bold"), pady=8)
            task_id = lbl.split()[0].lower()
            b.config(command=lambda f=func, t=task_id, s=save: self.run_threaded_action(f, task_id=t, save_config_after=s, use_popup=True))
            b.grid(row=r, column=c, sticky="ew", padx=5, pady=5)
            btn_grid.columnconfigure(c, weight=1)
            self.widgets['buttons'][task_id] = b

        # Controls & Utility Section
        util_frame = tk.Frame(right_frame, bg="#1e1e2f")
        util_frame.pack(fill=tk.X, pady=5)

        # -- Timestamp Checkbox --
        self.widgets['use_timestamps'] = tk.BooleanVar(value=False)
        ts_chk = tk.Checkbutton(util_frame, text="Append Timestamps to Filenames", variable=self.widgets['use_timestamps'],
                                bg="#1e1e2f", fg="white", selectcolor="#252526", activebackground="#1e1e2f")
        ts_chk.pack(side=tk.LEFT, padx=10)

        # -- Exclusion / .gitignore Toggle (default ON) --
        self.widgets['respect_exclusions'] = tk.BooleanVar(value=True)
        excl_chk = tk.Checkbutton(
            util_frame,
            text="Respect .gitignore + exclusions",
            variable=self.widgets['respect_exclusions'],
            bg="#1e1e2f",
            fg="white",
            selectcolor="#252526",
            activebackground="#1e1e2f"
        )
        excl_chk.pack(side=tk.LEFT, padx=10)

        # -- Conda --
        tk.Label(util_frame, text="| Env:", bg="#1e1e2f", fg="gray").pack(side=tk.LEFT)
        self.widgets['conda_env_var'] = tk.StringVar()
        self.widgets['conda_env_combo'] = ttk.Combobox(util_frame, textvariable=self.widgets['conda_env_var'], state="readonly", width=15)
        self.widgets['conda_env_combo'].pack(side=tk.LEFT, padx=5)
        tk.Button(util_frame, text="Audit", bg="#4a4a5a", fg="white", font=("Arial", 8),
                  command=lambda: self.run_threaded_action(self.audit_conda_impl, task_id='audit_conda', use_popup=True)).pack(side=tk.LEFT)

        # -- Utility --
        tk.Button(util_frame, text="Open Logs", command=self.open_main_log_directory, bg="#4a4a5a", fg="white").pack(side=tk.RIGHT, padx=5)
        tk.Button(util_frame, text="Exclusions", command=self.manage_dynamic_exclusions_popup, bg="#007a7a", fg="white").pack(side=tk.RIGHT, padx=5)
        tk.Button(util_frame, text="All", command=lambda: self.set_global_selection(S_CHECKED), bg="#4a4a5a", fg="white", width=4).pack(side=tk.RIGHT, padx=2)
        tk.Button(util_frame, text="None", command=lambda: self.set_global_selection(S_UNCHECKED), bg="#4a4a5a", fg="white", width=4).pack(side=tk.RIGHT, padx=2)
        
        # -- Quick Add Exclusion --
        tk.Button(util_frame, text="Add", command=lambda: self.add_excluded_filename(self.exc_entry), bg="#007ACC", fg="white", font=("Arial", 8)).pack(side=tk.RIGHT, padx=5)
        self.exc_entry = tk.Entry(util_frame, bg="#3a3a4a", fg="white", width=15)
        self.exc_entry.pack(side=tk.RIGHT, padx=5)
        tk.Label(util_frame, text="Excl. Pattern:", bg="#1e1e2f", fg="gray").pack(side=tk.RIGHT)

        # Log Box
        self.widgets['log_box'] = scrolledtext.ScrolledText(right_frame, bg="#151521", fg="#E0E0E0", font=("Consolas", 9), state=tk.DISABLED, height=10)
        self.widgets['log_box'].pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        paned.add(right_frame, weight=1)

        # Status Bar
        self.widgets['status_var'] = tk.StringVar(value="Ready.")
        self.widgets['status_bar'] = tk.Label(self.root, textvariable=self.widgets['status_var'], bg="#111111", fg="#90EE90", anchor="w")
        self.widgets['status_bar'].pack(fill=tk.X, side=tk.BOTTOM)

    # --- Threading & Activity Logic ---
    def _activity_blinker(self):
        if self.running_tasks:
            current_color = self.widgets['status_bar'].cget("bg")
            next_color = "#333333" if current_color == "#111111" else "#111111"
            self.widgets['status_bar'].config(bg=next_color)
            task_names = ", ".join(self.running_tasks)
            self.widgets['status_var'].set(f"[ACTIVE] Processing: {task_names}")
        else:
            self.widgets['status_bar'].config(bg="#111111")
            
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
            tree.insert(d['parent'], "end", iid=d['iid'], text=d['text'], open=d.get('open', False))
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
            
            # Recursion only needed for folders (files have no children)
            if tree.get_children(iid):
                for child in tree.get_children(iid): _refresh(child)
        
        if start_node: _refresh(start_node)
        else:
            root = self._get_current_project_path()
            if root: _refresh(str(root.resolve()))

    def on_tree_item_click(self, event):
        tree = event.widget
        
        # Identify specific element. 
        # Note: element name varies by theme (e.g., "image", "Treeitem.image", etc.)
        element = tree.identify("element", event.x, event.y)
        iid = tree.identify_row(event.y)
        
        if not iid: return

        # ROBUST FIX: Check if "image" is part of the element name
        if "image" in element:
            with self.state_lock:
                curr = self.folder_item_states.get(iid, S_UNCHECKED)
                new = S_CHECKED if curr != S_CHECKED else S_UNCHECKED
                self.folder_item_states[iid] = new
            self.refresh_tree_visuals(iid)

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
        lb = tk.Listbox(top)
        lb.pack(fill=tk.BOTH, expand=True)
        for x in self.dynamic_global_excluded_filenames: lb.insert(tk.END, x)
        def _rem():
            sel = lb.curselection()
            if not sel: return
            val = lb.get(sel[0])
            self.dynamic_global_excluded_filenames.remove(val)
            top.destroy()
            self.manage_dynamic_exclusions_popup()
        tk.Button(top, text="Remove Selected", command=_rem).pack()

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


