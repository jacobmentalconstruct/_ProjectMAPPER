# ==============================================================================
# ProjectMapper Snapshot Compiler
# Tk application shell; shared state, scanning, writes, and tools live in packages.
# ==============================================================================

# === [SECTION: IMPORTS] BEGIN ===
import sys
import os
import platform
import subprocess
import threading
import queue
import traceback
import copy
import weakref
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import tkinter.font as tkFont
if __package__:
    from .tree_view import TreeProjection
    from .tools import (PatchError, validate_target, PatcherWindow, TextEditorWindow,
                        TextToucherWindow, ProjectPatcherWindow, BackupsWindow, HistoryWindow)
    from .core import format_diagnostics, scan_project_tree
else:
    from tree_view import TreeProjection
    from tools import (PatchError, validate_target, PatcherWindow, TextEditorWindow,
                       TextToucherWindow, ProjectPatcherWindow, BackupsWindow, HistoryWindow)
    from core import format_diagnostics, scan_project_tree
# === [SECTION: IMPORTS] END ===


if __package__:
    from .core.config import *
else:
    from core.config import *





MAX_LOG_LINES = 2000  # the main log keeps only recent lines; History keeps operations


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
    "linked": "#7652A3",
    "linked_hover": "#8C65BA",
    "danger": "#B75A4D",
    "danger_hover": "#CB6B5E",
    "checkbox_checked": "#C56F3D",
    "checkbox_border": "#728195",
    "log_text": "#E1E7EE",
    "log_accent": "#89D6A0",
    # Diff highlighting on tree_bg; each is at least 7:1 contrast (WCAG AAA).
    "diff_header": "#9DB7D5",
    "diff_hunk": "#C4A5EA",
    "diff_add": "#8FD6A8",
    "diff_remove": "#F0A096",
}
# === [SECTION: THEME] END ===


# === [SECTION: PYTHONW_SAFETY] BEGIN ===
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
# === [SECTION: PYTHONW_SAFETY] END ===


if __package__:
    from .core.helpers import *
else:
    from core.helpers import *


if __package__:
    from .core.exports import *
else:
    from core.exports import *


if __package__:
    from .core.snapshots import *
else:
    from core.snapshots import *


if __package__:
    from .core.exclusions import *
else:
    from core.exclusions import *

















# Enough height for the path row, several tree rows, all action rows and a few log lines.
MIN_WINDOW_HEIGHT = 560


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
class ExclusionsPopup:
    SOURCE_LABELS = {
        "hardcoded_folder": "Built-in · folder",
        "predefined_filename": "Built-in · filename",
        "dynamic_user_pattern": "Custom · filename",
        "gitignore_dirname": ".gitignore · folder",
        "gitignore_file_pattern": ".gitignore · filename",
        "gitignore_path_pattern": ".gitignore · path",
    }

    def __init__(self, app):
        self.app = app
        self.selected = set()
        self.project_root = None
        self.top = tk.Toplevel(app.root)
        self.top.title("Manage Exclusions")
        self.top.configure(bg=THEME["panel_bg"])
        self.top.geometry("800x560")
        self.top.minsize(690, 420)
        self.top.transient(app.root)
        self.top.bind("<Escape>", lambda _event: self.top.destroy())

        tk.Label(self.top, text="Manage exclusions", bg=THEME["panel_bg"],
                 fg=THEME["text"], font=("Arial", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(self.top, text="Exclude checked: hide matching files/folders from the mapper.\n"
                 "Exclude unchecked: allow matches, unless another rule excludes them.\n"
                 "Select: choose rows for batch actions only. Patterns use wildcards (*.log), not regex.\n"
                 "Changes apply immediately for this session; .gitignore stays unchanged.",
                 bg=THEME["panel_bg"], fg=THEME["muted_text"], justify=tk.LEFT).pack(anchor="w", padx=16)
        self.project_label = tk.Label(self.top, bg=THEME["panel_bg"], fg=THEME["muted_text"], anchor="w")
        self.project_label.pack(fill=tk.X, padx=16, pady=(6, 0))
        self._checkbutton(self.top, app.widgets["respect_exclusions"], app.apply_exclusion_settings,
                          "Apply exclusion rules (checked = hide matches)").pack(anchor="w", padx=12, pady=6)

        add_row = tk.Frame(self.top, bg=THEME["panel_bg"])
        add_row.pack(fill=tk.X, padx=16, pady=(0, 10))
        tk.Label(add_row, text="Hide filenames matching:", bg=THEME["panel_bg"], fg=THEME["text"]).pack(side=tk.LEFT)
        self.entry = tk.Entry(add_row, bg=THEME["field_bg"], fg=THEME["text"], insertbackground=THEME["text"])
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.entry.bind("<Return>", lambda _event: self.add_pattern())
        app._make_button(add_row, "Add", self.add_pattern, THEME["accent"], THEME["accent_hover"]).pack(side=tk.RIGHT)

        list_frame = tk.Frame(self.top, bg=THEME["tree_bg"])
        self.canvas = tk.Canvas(list_frame, bg=THEME["tree_bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.rows_frame = tk.Frame(self.canvas, bg=THEME["tree_bg"])
        self.rows_window = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.columnconfigure(2, weight=1)
        self.rows_frame.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.rows_window, width=event.width))
        self.top.bind("<MouseWheel>", self._scroll)
        self.top.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-1, "units"))
        self.top.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(1, "units"))

        self.status = tk.Label(self.top, bg=THEME["panel_bg"], fg=THEME["muted_text"], anchor="w")
        actions = tk.Frame(self.top, bg=THEME["panel_bg"])
        actions.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 12))
        self.batch_buttons = []
        for label, command, color in (
            ("Select All", lambda: self.select_all(True), "panel_alt_bg"),
            ("Deselect All", lambda: self.select_all(False), "panel_alt_bg"),
            ("Exclude Selected", lambda: self.set_selected_enabled(True), "secondary"),
            ("Allow Selected", lambda: self.set_selected_enabled(False), "secondary"),
            ("Delete Selected", self.delete_selected, "danger"),
        ):
            button = app._make_button(actions, label, command, THEME[color], THEME["field_bg_alt"])
            button.pack(side=tk.LEFT, padx=3)
            if label.endswith("Selected"):
                self.batch_buttons.append(button)
        self.status.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=8)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16)
        self.refresh()

    def _checkbutton(self, parent, variable, command, text="", background=None):
        bg = background or THEME["panel_bg"]
        return tk.Checkbutton(parent, text=text, variable=variable, command=command,
                              bg=bg, fg=THEME["text"], selectcolor=THEME["tree_bg"],
                              activebackground=bg, activeforeground=THEME["text"])

    def _scroll(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def refresh(self):
        policy = self.app.exclusion_policy
        if self.project_root != policy.gitignore_root:
            self.selected.clear()
            self.project_root = policy.gitignore_root
        self.project_label.config(text=f"Project: {self.app.selected_root}")
        self.rules = [rule for rule in policy.collect_rules() if rule["rule_type"] != "toggle"]
        keys = {policy.rule_key(rule["source"], rule["pattern"]) for rule in self.rules}
        self.selected.intersection_update(keys)
        y_position = self.canvas.yview()[0]
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self.selection_vars = {}
        for column, title in enumerate(("Select", "Exclude (hide)", "Matching pattern", "Source / match type")):
            tk.Label(self.rows_frame, text=title, bg=THEME["heading_bg"], fg=THEME["heading_text"],
                     anchor="w" if column > 1 else "center", padx=10, pady=7).grid(row=0, column=column, sticky="nsew")
        for index, rule in enumerate(self.rules, 1):
            key = policy.rule_key(rule["source"], rule["pattern"])
            bg = THEME["tree_bg"] if index % 2 else THEME["panel_bg"]
            selected = tk.BooleanVar(value=key in self.selected)
            enabled = tk.BooleanVar(value=bool(rule["active"]))
            self.selection_vars[key] = selected
            self._checkbutton(self.rows_frame, selected,
                              lambda k=key, v=selected: self.select_row(k, v.get()), background=bg).grid(row=index, column=0, sticky="nsew")
            self._checkbutton(self.rows_frame, enabled,
                              lambda r=rule, v=enabled: self.toggle_rule(r, v.get()), background=bg).grid(row=index, column=1, sticky="nsew")
            tk.Label(self.rows_frame, text=rule["pattern"], bg=bg, fg=THEME["text"], anchor="w",
                     padx=10, pady=5, wraplength=330, justify=tk.LEFT).grid(row=index, column=2, sticky="nsew")
            tk.Label(self.rows_frame, text=self.SOURCE_LABELS[rule["source"]], bg=bg,
                     fg=THEME["muted_text"], anchor="w", padx=10).grid(row=index, column=3, sticky="nsew")
        if not self.rules:
            tk.Label(self.rows_frame, text="No exclusion rules. Add a filename pattern above.",
                     bg=THEME["tree_bg"], fg=THEME["muted_text"], pady=24).grid(row=1, column=0, columnspan=4)
        self.rows_frame.update_idletasks()
        self.canvas.yview_moveto(y_position)
        self.update_status()

    def update_status(self):
        enabled = sum(rule["active"] for rule in self.rules)
        paused = " · Exclusions OFF: matches are allowed" if not self.app.exclusion_policy.respect_exclusions else ""
        self.status.config(text=f"{len(self.rules)} rules · {enabled} checked to exclude · {len(self.selected)} selected{paused}")
        for button in self.batch_buttons:
            button.config(state=tk.NORMAL if self.selected else tk.DISABLED)

    def select_row(self, key, selected):
        if selected:
            self.selected.add(key)
        else:
            self.selected.discard(key)
        self.update_status()

    def select_all(self, selected):
        self.selected = set(self.selection_vars) if selected else set()
        for variable in self.selection_vars.values():
            variable.set(selected)
        self.update_status()

    def toggle_rule(self, rule, enabled):
        self.app.action("exclusions.update", {"operation": "enable", "source": rule["source"], "pattern": rule["pattern"], "enabled": enabled})
        self.app.exclusions_changed()

    def set_selected_enabled(self, enabled):
        policy = self.app.exclusion_policy
        for rule in self.rules:
            if policy.rule_key(rule["source"], rule["pattern"]) in self.selected:
                self.app.action("exclusions.update", {"operation": "enable", "source": rule["source"], "pattern": rule["pattern"], "enabled": enabled})
        self.app.exclusions_changed()

    def delete_selected(self):
        policy = self.app.exclusion_policy
        count = len(self.selected)
        for rule in self.rules:
            if policy.rule_key(rule["source"], rule["pattern"]) in self.selected:
                self.app.action("exclusions.update", {"operation": "delete", "source": rule["source"], "pattern": rule["pattern"]})
        self.selected.clear()
        self.app.log_message(f"Deleted {count} exclusion rules for this session.")
        self.app.exclusions_changed()

    def add_pattern(self):
        self.app.add_exclusion_from_entry(self.entry)


if __package__:
    from .application.controller import create_application
    from .application.desktop import perform
    from .application.errors import describe
else:
    from application.controller import create_application
    from application.desktop import perform
    from application.errors import describe


class ProjectMapperApp:
    @property
    def selected_root(self):
        return self.project_state.root if hasattr(self, "project_state") else getattr(self, "_selected_root", None)
    @selected_root.setter
    def selected_root(self, value):
        if hasattr(self, "project_state"):
            self.project_state.root = Path(value) if value else None
        else:
            self._selected_root = Path(value) if value else None
    def _state_property(name):
        def get(self):
            state = getattr(self, "project_state", None)
            return getattr(state, name) if state is not None else getattr(self, "_" + name, None)
        def set_(self, value):
            state = getattr(self, "project_state", None)
            if state is not None: setattr(state, name, value)
            else: setattr(self, "_" + name, value)
        return property(get, set_)
    scan_revision = _state_property("scan_revision")
    applied_scan_revision = _state_property("applied_scan_revision")
    latest_source_mtime = _state_property("latest_source_mtime")
    latest_snapshot_path = _state_property("snapshot_path")
    transformed_paths = _state_property("transformed_paths")
    running_tasks = _state_property("active_operations")
    def _model_property(name, owner="controller"):
        def get(self):
            model = getattr(self, owner, None)
            return getattr(model, name) if model is not None else getattr(self, "_" + name, {})
        def set_(self, value):
            model = getattr(self, owner, None)
            if model is not None: setattr(model, name, value)
            else: setattr(self, "_" + name, value)
        return property(get, set_)
    folder_item_states = _model_property("selection")
    tree_rows = _model_property("rows")
    scan_skipped_paths = _model_property("skipped")

    def __init__(self, root: tk.Tk, initial_root=None):
        self.root = root
        self.initial_root = Path(initial_root or Path.cwd()).resolve()
        self.theme = THEME
        self.gui_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.widgets = {}
        self.current_progress_popup = None
        self.controller, self.approve_action = create_application(self.initial_root)
        self.controller.scan_fn = lambda root, policy, stop: scan_project_tree(root, policy, stop)
        self.project_state = self.controller.state
        self.action_operations = set()
        self.desktop_operations = set()
        self.editor_windows = weakref.WeakSet()
        self.syncing_controls = False
        self.controller.dispatcher.subscribe(lambda event: self.gui_queue.put(lambda: self.on_action_event(event)))
        # Hidden failures (decision D): one concise log line; the traceback stays in History.
        self.controller.history.subscribe(
            lambda record: self.gui_queue.put(lambda: self._announce_problem(record))
            if record["category"] == "internal" else None)
        self.root.report_callback_exception = self._report_callback_exception
        self.root.bind("<Destroy>", self._destroy_actions, add="+")
        self.latest_snapshot_path = None
        self.latest_source_mtime = 0.0
        self.state_lock = self.controller.lock
        self.folder_item_states = {}
        self.tree_rows = []
        self.scan_skipped_paths = []
        self.exclusion_policy = self.controller.policy
        self.exclusions_popup = None
        self.scan_revision = 0
        self.applied_scan_revision = -1
        self.scan_pending = False
        self.scan_after_id = None
        self.scan_use_popup = False
        self.exclusions_dirty = False
        self.transformed_paths = self.project_state.transformed_paths
        self.icon_imgs = {}
        self.tree_projection = None
        self._create_tree_icons()

        self._setup_styles()
        self._setup_ui()
        self.process_gui_queue()
        self._activity_blinker()
        self.log_message("Snapshot Compiler loaded. Choose a project root, curate the tree, then compile a SQLite snapshot.")
        self.root.after(250, self.request_rescan_tree_silent)

    def action(self, name, payload=None, **options):
        return perform(self, name, payload, **options)

    def _destroy_actions(self, event):
        if event.widget is self.root:
            self.controller.close()

    def on_action_event(self, event):
        if event.type == "progress":
            # Progress is counted in History; the log is not flooded with one line per update.
            message = event.payload.get("message", "Working")
            self.widgets["status_var"].set(message)
            if self.current_progress_popup:
                self.current_progress_popup.update_text(message)
        if event.type == "succeeded" and event.payload.get("paths"):
            for editor in tuple(self.editor_windows):
                if editor.top.winfo_exists():
                    editor.check_source()
            self.request_rescan_tree_silent()
        if event.type == "succeeded" and event.operation_id not in self.desktop_operations:
            if event.action == "project.set_root":
                self.widgets["selected_root_var"].set(str(self.selected_root))
                self.populate_tree([])
                self.request_rescan_tree_silent()
            elif event.action == "project.scan":
                if event.payload.get("revision") == self.scan_revision:
                    self.populate_tree(self.tree_rows)
                    self.scan_pending = False
            elif event.action == "selection.set":
                self.refresh_tree_visuals()
            elif event.action == "exclusions.update":
                self.widgets["respect_exclusions"].set(self.exclusion_policy.respect_exclusions)
                self.refresh_exclusions_popup()
                self.request_rescan_tree_silent()
            elif event.action == "capture.configure":
                self.syncing_controls = True
                try:
                    self.widgets["include_binary_blobs"].set(self.controller.include_binary)
                finally:
                    self.syncing_controls = False
        if event.type in ("failed", "recovery_required"):
            self.log_message(describe(event.payload.get("error") or {"code": event.type}), "ERROR")
        if event.type == "recovery_required":
            self.log_message("Open Backups… to review recovery and pre-restore generations.", "WARNING")

    def _report_callback_exception(self, exc_type, exc, tb):
        """Tk-wide: button and event callbacks in every window of this interpreter."""
        trace = "".join(traceback.format_exception(exc_type, exc, tb))
        self.controller.history.record_problem("ui_callback", f"{exc_type.__name__}: {exc}", trace)

    def _announce_problem(self, record):
        try:
            source = record["action"].split(".", 1)[1]
            self.log_message(f"Internal problem ({source}): {record['error']['message']} — see History", "ERROR")
        except Exception:
            pass  # announcing must never raise back into the queue that reports failures

    def run_diagnostics(self):
        report = self.action("application.diagnostics")
        text = format_diagnostics(report)
        self.log_message(text, "INFO" if report["ok"] else "ERROR")
        messagebox.showinfo("Diagnostics", text, parent=self.root) if report["ok"] else messagebox.showwarning("Diagnostics", text, parent=self.root)
        return report

    def mark_project_dirty(self, reason, paths=()):
        self.action("project.dirty", {"reason": reason, "paths": [str(p) for p in paths]})
        self.transformed_paths = self.project_state.transformed_paths
        self.latest_snapshot_path = None

    def report_error(self, title, exc):
        self.log_message(f"{title}: {exc}", "ERROR")
        messagebox.showerror(title, str(exc), parent=self.root)

    def _create_tree_icons(self):
        img_unchecked = tk.PhotoImage(master=self.root, width=14, height=14)
        img_unchecked.put((THEME["checkbox_border"],), to=(0, 0, 14, 1))
        img_unchecked.put((THEME["checkbox_border"],), to=(0, 13, 14, 14))
        img_unchecked.put((THEME["checkbox_border"],), to=(0, 0, 1, 14))
        img_unchecked.put((THEME["checkbox_border"],), to=(13, 0, 14, 14))
        self.icon_imgs[S_UNCHECKED] = img_unchecked

        img_checked = tk.PhotoImage(master=self.root, width=14, height=14)
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
        self.widgets["selected_root_var"] = tk.StringVar(value=str(self.initial_root))
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
        self.widgets["folder_tree"].column("#0", width=420, minwidth=200)  # stretches with the window
        self.widgets["folder_tree"].column("nav_up", width=34, anchor="center", stretch=False)
        self.widgets["folder_tree"].column("nav_down", width=34, anchor="center", stretch=False)
        self.widgets["folder_tree"].column("size", width=120, anchor="e", stretch=False)
        self.widgets["folder_tree"].insert("", "end", text="Tree scanner pending", values=("", "", ""))

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.widgets["folder_tree"].yview)
        vsb.bind("<ButtonPress-1>", lambda event: self.tree_projection._user_navigation(event)
                 if self.tree_projection is not None else None)
        self.widgets["folder_tree"].configure(yscrollcommand=vsb.set)
        self.widgets["folder_tree"].pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.widgets["folder_tree"].bind("<ButtonRelease-1>", self.on_tree_item_click)
        self.widgets["folder_tree"].bind("<ButtonRelease-3>", self.on_file_context_menu)
        self.widgets["folder_tree"].bind("<Shift-F10>", self.on_file_context_menu)
        self.widgets["folder_tree"].bind("<<TreeviewOpen>>", self.on_tree_open)
        paned.add(tree_frame, weight=3)

        action_frame = tk.Frame(paned, bg=THEME["panel_bg"])
        # Four short rows instead of two long ones, so the window can be narrower than
        # 1200 px without clipping; the minimum size is measured from them below.
        btn_row = tk.Frame(action_frame, bg=THEME["panel_bg"])
        btn_row.pack(fill=tk.X, padx=5, pady=(6, 2))
        tool_row = tk.Frame(action_frame, bg=THEME["panel_bg"])
        tool_row.pack(fill=tk.X, padx=5, pady=2)

        self._make_button(btn_row, "Compile Snapshot", self.compile_snapshot_placeholder, THEME["accent"], THEME["accent_hover"], bold=True).pack(side=tk.LEFT, padx=4)
        self._make_button(btn_row, "Export Tree MD", self.export_tree_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
        self._make_button(btn_row, "Export Filedump MD", self.export_filedump_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
        self._make_button(btn_row, "Export Tree+Dump MD", self.export_combined_markdown, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.LEFT, padx=4)
        self._make_button(tool_row, "Open Output Folder", self.open_output_folder, THEME["success"], THEME["success_hover"]).pack(side=tk.LEFT, padx=4)
        vendor_button = self._make_button(tool_row, "Export Vendor App", self.export_vendor_app, THEME["secondary"], THEME["secondary_hover"])
        if SOURCE_ROOT is None:  # Installed package: there is no source checkout to vendor.
            vendor_button.configure(state=tk.DISABLED)
        vendor_button.pack(side=tk.LEFT, padx=4)
        self.widgets["vendor_export_button"] = vendor_button
        self._make_button(tool_row, "Diagnostics", self.run_diagnostics, THEME["panel_alt_bg"], THEME["field_bg_alt"]).pack(side=tk.RIGHT, padx=4)
        self.widgets["backups_button"] = self._make_button(tool_row, "Backups…", self.open_backups,
                                                           THEME["panel_alt_bg"], THEME["field_bg_alt"])
        self.widgets["backups_button"].pack(side=tk.RIGHT, padx=4)

        option_row = tk.Frame(action_frame, bg=THEME["panel_bg"])
        option_row.pack(fill=tk.X, padx=5, pady=2)
        control_row = tk.Frame(action_frame, bg=THEME["panel_bg"])
        control_row.pack(fill=tk.X, padx=5, pady=2)
        self.widgets["respect_exclusions"] = tk.BooleanVar(value=True)
        tk.Checkbutton(
            option_row,
            text="Apply exclusions (hide matches)",
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
            option_row,
            text="Tree in filedump export",
            variable=self.widgets["include_tree_in_filedump"],
            bg=THEME["panel_bg"],
            fg=THEME["text"],
            selectcolor=THEME["tree_bg"],
            activebackground=THEME["panel_bg"],
            activeforeground=THEME["text"],
        ).pack(side=tk.LEFT, padx=6)
        self.widgets["include_binary_blobs"] = tk.BooleanVar(value=False)
        self.widgets["include_binary_blobs"].trace_add("write", lambda *_: None if self.syncing_controls else self.action("capture.configure", {"include_binary": bool(self.widgets["include_binary_blobs"].get())}))
        tk.Checkbutton(
            option_row,
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
        self._make_button(control_row, "Add", self.add_exclusion_from_entry, THEME["accent"], THEME["accent_hover"]).pack(side=tk.RIGHT, padx=2)
        self.widgets["exclusion_entry"] = tk.Entry(
            control_row,
            bg=THEME["field_bg_alt"],
            fg=THEME["field_text"],
            insertbackground=THEME["field_text"],
            width=22,
            relief=tk.FLAT,
        )
        self.widgets["exclusion_entry"].pack(side=tk.RIGHT, padx=4)
        # Packed right to left: reads "Hide pattern: [entry] Add".
        tk.Label(control_row, text="Hide pattern:", bg=THEME["panel_bg"], fg=THEME["muted_text"]).pack(side=tk.RIGHT, padx=4)
        self._make_button(control_row, "Exclusions", self.manage_exclusions_popup, THEME["success"], THEME["success_hover"]).pack(side=tk.RIGHT, padx=2)
        self._make_button(control_row, "Rescan", self.request_rescan_tree, THEME["secondary"], THEME["secondary_hover"]).pack(side=tk.RIGHT, padx=2)

        log_header = tk.Frame(action_frame, bg=THEME["panel_bg"])
        log_header.pack(fill=tk.X, padx=5, pady=(4, 0))
        tk.Label(log_header, text="LOG (recent lines; operations are kept in History)", bg=THEME["panel_bg"],
                 fg=THEME["muted_text"], font=("Arial", 9)).pack(side=tk.LEFT)
        self.widgets["history_button"] = self._make_button(log_header, "History…", self.open_history,
                                                           THEME["panel_alt_bg"], THEME["field_bg_alt"])
        self.widgets["history_button"].pack(side=tk.RIGHT)

        self.widgets["log_box"] = scrolledtext.ScrolledText(
            action_frame,
            bg=THEME["log_bg"],
            fg=THEME["log_text"],
            insertbackground=THEME["log_text"],
            font=("Consolas", 9),
            state=tk.DISABLED,
            height=5,  # a starting height; the tree gets the room and the pane divider can be dragged
            width=60,  # a base width only; the log fills the window
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
        # Packed before the pane so a short window shrinks the pane, never the status bar.
        self.widgets["status_bar"].pack(fill=tk.X, side=tk.BOTTOM, before=paned)
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), MIN_WINDOW_HEIGHT)

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
    def on_file_context_menu(self, event):
        tree = self.widgets["folder_tree"]
        keyboard = getattr(event, "keysym", "") == "F10"
        iid = tree.focus() if keyboard else tree.identify_row(event.y)
        if iid.startswith(TreeProjection.PLACEHOLDER):
            return "break"
        # Context selection must not toggle capture checkboxes.
        if iid:
            tree.selection_set(iid)
            tree.focus(iid)
        else:
            tree.selection_remove(*tree.selection())
            tree.focus("")
        # Empty space targets the current project root, never a previously selected row.
        path = Path(iid) if iid else self.selected_root
        previous_menu = getattr(self, "file_context_menu", None)
        if previous_menu is not None:
            previous_menu.destroy()
        menu = self.file_context_menu = tk.Menu(tree, tearoff=False)
        allowed = bool(iid) and path.is_file()
        label = "Tokenizing Patcher…" if allowed else "Tokenizing Patcher… (select a file)"
        try:
            validate_target(path)
        except PatchError:
            allowed = False
        menu.add_command(label=label, command=lambda: self.open_tokenizing_patcher(path),
                         state="normal" if allowed else "disabled")
        menu.add_command(label="Open Text Editor…", command=lambda: self.open_text_editor(path),
                         state="normal" if allowed else "disabled")
        folder = path
        can_create = folder.is_dir()
        try:
            validate_target(folder)
        except PatchError:
            can_create = False
        menu.add_command(label="New Text File…", command=lambda: self.open_text_toucher(folder),
                         state="normal" if can_create else "disabled")
        menu.add_separator()
        menu.add_command(label="Delete File…", command=lambda: self.delete_file(path),
                         state="normal" if allowed else "disabled")
        menu.add_separator()
        can_project_patch = folder.is_dir()
        try:
            validate_target(folder)
        except PatchError:
            can_project_patch = False
        menu.add_command(label="Project Patcher…", command=lambda: self.open_project_patcher(folder),
                         state="normal" if can_project_patch else "disabled")
        try:
            menu.tk_popup(tree.winfo_rootx() + 40 if keyboard else event.x_root,
                          tree.winfo_rooty() + 40 if keyboard else event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def open_tokenizing_patcher(self, path):
        try:
            return PatcherWindow(self, path)
        except (OSError, PatchError) as exc:
            self.report_error("Cannot open patcher", exc)
            return None

    def open_text_toucher(self, folder):
        try:
            return TextToucherWindow(self, folder)
        except (OSError, PatchError) as exc:
            self.report_error("Cannot create file", exc)
            return None

    def open_text_editor(self, path):
        try:
            return TextEditorWindow(self, path)
        except (OSError, PatchError) as exc:
            self.report_error("Cannot open text editor", exc)
            return None

    def open_backups(self):
        """One Backups window at a time; raise the existing one."""
        existing = getattr(self, "backups_window", None)
        if existing is not None and existing.top.winfo_exists():
            existing.top.deiconify()
            existing.top.lift()
            existing.refresh()
            return existing
        self.backups_window = BackupsWindow(self)
        return self.backups_window

    def open_history(self):
        """One History window at a time; raise the existing one."""
        existing = getattr(self, "history_window", None)
        if existing is not None and existing.top.winfo_exists():
            existing.top.deiconify()
            existing.top.lift()
            existing.refresh()
            return existing
        self.history_window = HistoryWindow(self)
        return self.history_window

    def open_project_patcher(self, folder):
        try:
            return ProjectPatcherWindow(self, folder)
        except (OSError, PatchError) as exc:
            self.report_error("Cannot open project patcher", exc)
            return None

    def delete_file(self, path):
        if self.running_tasks or self.scan_pending:
            self.log_message("Wait for the current scan or compile to finish before deleting a file.", "WARNING")
            return
        try:
            self.action("file.delete", {"path": str(path)}, approval_guard=lambda: not self.running_tasks and not self.scan_pending)
        except (OSError, PatchError) as exc:
            self.report_error("Could not delete file", exc)
            return
        self.file_transformed(path, action="Deleted")

    def file_transformed(self, path, action="Saved"):
        self.log_message(f"{action} file: {path}. Compile a new snapshot before exporting.")
        self.request_rescan_tree_silent()

    def request_rescan_tree(self):
        self._queue_tree_scan(use_popup=True)

    def request_rescan_tree_silent(self):
        self._queue_tree_scan(use_popup=False)

    def _queue_tree_scan(self, use_popup=False):
        self.controller.reserve_scan()
        self.scan_pending = True
        self.scan_use_popup = self.scan_use_popup or use_popup
        self.refresh_exclusions_popup()
        if self.scan_after_id is not None:
            self.root.after_cancel(self.scan_after_id)
        self.scan_after_id = self.root.after(150, self._start_pending_scan)

    def _start_pending_scan(self):
        self.scan_after_id = None
        if self.running_tasks:
            self.scan_after_id = self.root.after(150, self._start_pending_scan)
            return
        root = self.selected_root
        revision = self.scan_revision
        policy = copy.deepcopy(self.exclusion_policy)
        use_popup = self.scan_use_popup
        self.scan_use_popup = False
        self.run_threaded_action(lambda: self._scan_tree_impl(root, policy, revision), "scan_tree", use_popup=use_popup)

    def _scan_tree_impl(self, root, policy, revision):
        root = root if root and root.is_dir() else None
        if root is None:
            self.schedule_log_message("Cannot scan: no valid project root.", "ERROR")
            self.gui_queue.put(lambda: self._finish_tree_scan(revision))
            return
        self.schedule_log_message(f"Scanning project tree: {root}")
        try:
            result = self.action("project.scan", {"revision": revision})
            rows = [dict(r, path=Path(r["path"]), parent=Path(r["parent"]) if r["parent"] else None) for r in result["rows"]]
            skipped = result["skipped"]
        except Exception:
            self.gui_queue.put(lambda: self._finish_tree_scan(revision))
            raise
        if self.stop_event.is_set():
            self.schedule_log_message("Tree scan cancelled.", "WARNING")
            self.gui_queue.put(lambda: self._finish_tree_scan(revision))
            return
        self.gui_queue.put(lambda: self._apply_tree_scan(root, revision, rows, skipped))

    def _finish_tree_scan(self, revision):
        if revision == self.scan_revision:
            self.scan_pending = False

    def _apply_tree_scan(self, root, revision, rows, skipped):
        # Rapid edits may finish while an older scan is still running.
        if revision != self.scan_revision or root != self.selected_root:
            return
        self.populate_tree(rows)
        self.scan_pending = False
        self.log_message(f"Scan complete: {len(rows)} visible entries, {len(skipped)} skipped entries.")

    def populate_tree(self, rows: list[dict]):
        tree = self.widgets["folder_tree"]
        if self.tree_projection is None:
            self.tree_projection = TreeProjection(tree, self._insert_tree_row)
        self.tree_projection.replace(rows)

    def _insert_tree_row(self, row):
        tree = self.widgets["folder_tree"]
        iid = str(row["path"])
        parent = "" if row["parent"] is None else str(row["parent"])
        state = self.folder_item_states.get(iid, S_UNCHECKED)
        prefix = "📁" if row["entry_type"] == "dir" else "📄"
        size_text = "" if row["size_bytes"] is None else format_display_size(row["size_bytes"])
        is_dir = row["entry_type"] == "dir"
        tree.insert(parent, "end", iid=iid, text=f"{prefix} {row['name']}",
                    image=self.icon_imgs.get(state, self.icon_imgs[S_UNCHECKED]),
                    values=("↑" if is_dir else "", "↓" if is_dir else "", size_text),
                    open=False)

    def on_tree_open(self, event):
        if self.tree_projection is not None:
            self.tree_projection.expand(event.widget.focus())

    def refresh_tree_visuals(self, start_iid: str | None = None):
        tree = self.widgets["folder_tree"]
        pending = [start_iid] if start_iid else list(tree.get_children())
        while pending:
            iid = pending.pop()
            if iid.startswith("__lazy__:") or not tree.exists(iid):
                continue
            state = self.folder_item_states.get(iid, S_UNCHECKED)
            tree.item(iid, image=self.icon_imgs.get(state, self.icon_imgs[S_UNCHECKED]))
            pending.extend(tree.get_children(iid))

    def on_tree_item_click(self, event):
        tree = event.widget
        iid = tree.identify_row(event.y)
        if not iid:
            return

        column = tree.identify_column(event.x)
        element = tree.identify("element", event.x, event.y) or ""
        if "indicator" in element:
            return
        path = Path(iid)
        if iid.startswith("__lazy__:"):
            return

        if column == "#1" and path.is_dir():
            self.navigate_tree_to_path(path.parent)
            return

        if column == "#2" and path.is_dir():
            self.navigate_tree_to_path(path)
            return

        if column == "#0" or "image" in element:
            self.toggle_tree_item(iid)

    def toggle_tree_item(self, iid: str):
        current = self.folder_item_states.get(iid, S_UNCHECKED)
        new_state = S_CHECKED if current != S_CHECKED else S_UNCHECKED
        self._set_tree_state_recursive(iid, new_state)
        self.refresh_tree_visuals(iid)

    def _set_tree_state_recursive(self, iid: str, state: str):
        self.action("selection.set", {"path": iid, "state": state})

    def set_global_selection(self, state: str):
        tree = self.widgets.get("folder_tree")
        if tree is None:
            return
        self.action("selection.set", {"state": state})
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
        self.action("exclusions.update", {"operation": "respect", "respect": bool(var.get()) if var else True})
        self.log_message(f"Respect exclusions: {self.exclusion_policy.respect_exclusions}")
        self.exclusions_changed()

    def add_exclusion_from_entry(self, entry=None):
        if entry is None:
            entry = self.widgets.get("exclusion_entry")
        if entry is None:
            return
        value = entry.get().strip()
        if not value:
            return
        self.action("exclusions.update", {"operation": "add", "pattern": value})
        entry.delete(0, tk.END)
        self.log_message(f"Added exclusion pattern: {value}")
        self.exclusions_changed()

    def exclusions_changed(self):
        self.exclusions_dirty = True
        self.mark_project_dirty("exclusions_changed")
        self.request_rescan_tree_silent()

    def refresh_exclusions_popup(self):
        if self.exclusions_popup and self.exclusions_popup.top.winfo_exists():
            self.exclusions_popup.refresh()

    def manage_exclusions_popup(self):
        if self.exclusions_popup and self.exclusions_popup.top.winfo_exists():
            self.exclusions_popup.top.deiconify()
            self.exclusions_popup.top.lift()
            self.exclusions_popup.top.focus_set()
            return
        self.action("exclusions.inspect")
        self.exclusions_popup = ExclusionsPopup(self)
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
        self.action("project.set_root", {"path": str(target)})
        self.populate_tree([])
        self.exclusions_dirty = False
        self.latest_source_mtime = 0.0
        self.transformed_paths = self.project_state.transformed_paths
        self.latest_snapshot_path = None
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
            self.report_error("Invalid Project Root", f"Not a directory:\n{candidate}")
            return
        self.action("project.set_root", {"path": str(candidate.resolve())})
        self.populate_tree([])
        self.exclusions_dirty = False
        self.latest_source_mtime = 0.0
        self.transformed_paths = self.project_state.transformed_paths
        self.latest_snapshot_path = None
        self.log_message(f"Project root set: {self.selected_root}")
        self.request_rescan_tree()

    def get_output_dir(self) -> Path:
        return Path(self.action("output.location")["path"])

    def compile_snapshot_placeholder(self):
        if self.scan_pending or "scan_tree" in self.running_tasks or self.applied_scan_revision != self.scan_revision:
            self.log_message("A current project tree is required. Finish a rescan before compiling.", "WARNING")
            return
        policy = copy.deepcopy(self.exclusion_policy)
        root = self.selected_root
        revision = self.scan_revision
        include_binary_blobs = bool(self.widgets["include_binary_blobs"].get())
        self.mark_project_dirty("compile_required")
        capture_revision = self.project_state.capture_revision
        self.run_threaded_action(
            lambda: self._compile_snapshot_impl(policy, root, revision, include_binary_blobs, capture_revision),
            "compile_snapshot", use_popup=True)

    def _compile_snapshot_impl(self, policy, root, revision, include_binary_blobs, capture_revision=None):
        result = self.action("snapshot.compile")
        self.schedule_log_message(f"Snapshot compiled: {result['path']}")
        self.gui_queue.put(lambda: setattr(self, "exclusions_dirty", False))

    def _accept_compiled_snapshot(self, snapshot_path, root, revision, capture_revision=None):
        if root == self.selected_root and revision == self.scan_revision:
            if not self.project_state.mark_snapshot(snapshot_path, revision, capture_revision):
                return
            self.latest_snapshot_path = snapshot_path
            self.exclusions_dirty = False
            self.transformed_paths = self.project_state.transformed_paths
            self.log_message(f"Latest snapshot set: {snapshot_path}")

    def _require_latest_snapshot(self):
        try:
            return Path(self.action("snapshot.require")["path"])
        except (OSError, PatchError) as exc:
            self.log_message(str(exc), "WARNING")
            return None

    def export_snapshot_output(self, output_name, suffix, content_override=None):
        include_tree = output_name == "project_filedump_markdown" and bool(self.widgets["include_tree_in_filedump"].get())
        def export():
            result = self.action("snapshot.export", {"output": output_name, "suffix": suffix, "include_tree": include_tree})
            self.schedule_log_message(f"Exported: {result['path']}")
        self.run_threaded_action(export, "export_snapshot", use_popup=True)

    def export_tree_markdown(self):
        self.export_snapshot_output("project_tree_markdown", TREE_MD_SUFFIX)

    def export_filedump_markdown(self):
        self.export_snapshot_output("project_filedump_markdown", FILEDUMP_MD_SUFFIX)

    def export_combined_markdown(self):
        self.export_snapshot_output("project_tree_and_filedump_markdown", COMBINED_MD_SUFFIX)

    def export_manifest_markdown(self):
        self.export_snapshot_output("snapshot_manifest_markdown", MANIFEST_MD_SUFFIX)

    def export_vendor_app(self):
        self.run_threaded_action(self._export_vendor_app_impl, "vendor_export", use_popup=True)

    def _export_vendor_app_impl(self):
        result = self.action("vendor.export")
        self.schedule_log_message(
            f"Vendor export ready: {result['export_dir']} ({result['included_count']} files, {result['skipped_count']} skipped)"
        )
        if result.get("zip_path"):
            self.schedule_log_message(f"Vendor zip ready: {result['zip_path']}")

    def pending_projection_notice(self):
        self.log_message("Projection export is available after compiling a snapshot DB.", "WARNING")

    def open_output_folder(self):
        out_dir = Path(self.action("output.location")["path"])
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
        for operation in tuple(self.action_operations):
            self.controller.dispatcher.cancel(operation)
        self.log_message("Stop signal sent to active task.", "WARNING")

    def run_threaded_action(self, target_function, task_id: str, use_popup=False):
        if task_id in self.running_tasks:
            self.log_message(f"Task already running: {task_id}", "WARNING")
            return

        if use_popup:
            self.current_progress_popup = ProgressPopup(self.root, title=f"Working: {task_id}", on_cancel=self.cancel_current_operations)

        self.running_tasks.add(task_id)
        self.project_state.operation_started(task_id)
        self.stop_event.clear()

        def runner():
            try:
                target_function()
            except PatchError as exc:
                # A routine action failure; the operation itself is already in History.
                self.schedule_log_message(f"{task_id}: {exc}", "ERROR")
            except Exception as exc:
                self.controller.history.record_problem("worker", f"{task_id} failed: {exc}", traceback.format_exc())
            finally:
                self.running_tasks.discard(task_id)
                self.project_state.operation_finished(task_id)
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
            excess = int(log_box.index("end-1c").split(".")[0]) - 1 - MAX_LOG_LINES
            if excess > 0:
                log_box.delete("1.0", f"{excess + 1}.0")
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
            except Exception as exc:
                self.controller.history.record_problem("ui_queue", f"{type(exc).__name__}: {exc}",
                                                       traceback.format_exc())
        self.root.after(100, self.process_gui_queue)
# === [SECTION: THREADING_AND_LOGGING] END ===


# === [SECTION: ENTRYPOINT] BEGIN ===
def run_gui(initial_root=None):
    root = tk.Tk()
    ProjectMapperApp(root, initial_root)
    root.mainloop()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="projectmapper", description=APP_NAME)
    parser.add_argument("root", nargs="?", type=Path,
                        help="project folder to open (default: the current directory)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    args = parser.parse_args(argv)
    if args.root is not None and not args.root.is_dir():
        parser.error(f"not a folder: {args.root}")
    run_gui(args.root)


if __name__ == "__main__":
    main()
# === [SECTION: ENTRYPOINT] END ===



