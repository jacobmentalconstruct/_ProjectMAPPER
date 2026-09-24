"""Backups window: inspect, compare, restore and clean up managed backup generations.

Presentation only. Every read and write goes through the backup.* actions; restore and
clean-up reach the trusted approval dialog through the desktop adapter.
"""

from datetime import datetime
import tkinter as tk
from tkinter import ttk

from .patcher import PatchError
from .ui_base import ToolWindowMixin

VIEW_CURRENT, VIEW_DIFF, VIEW_BACKUP = range(3)


def human_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def local_time(iso):
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return iso or "—"


class BackupsWindow(ToolWindowMixin):
    def __init__(self, app):
        self.app = app
        self.colors = app.theme
        self.generations = {}
        self.file_plan = None
        self.top = tk.Toplevel(app.root)
        self.configure_tool_window("Backups", "1180x760", (760, 520))
        self.setup_review_styles()
        self.build_ui()
        self.top.bind("<F5>", lambda _event: (self.refresh(), "break")[1])
        self.refresh()

    # --- layout ------------------------------------------------------------

    def build_ui(self):
        colors = self.colors
        toolbar = self.frame(self.top)
        toolbar.pack(fill="x", padx=12, pady=8)
        self.button(toolbar, "Refresh", self.refresh).pack(side="left")
        self.delete_button = self.button(toolbar, "Delete Selected…", self.delete_selected, "danger")
        self.delete_button.pack(side="right")
        self.cleanup_button = self.button(toolbar, "Clean Up…", self.clean_up, "secondary")
        self.cleanup_button.pack(side="right", padx=6)
        self.keep = tk.StringVar(self.top, "10")
        tk.Spinbox(toolbar, from_=0, to=999, width=4, textvariable=self.keep, bg=colors["field_bg"],
                   fg=colors["field_text"], insertbackground=colors["text"], buttonbackground=colors["panel_alt_bg"],
                   relief="flat", font=("Arial", 10)).pack(side="right", padx=(4, 6))
        self.label(toolbar, panel=True, text="keep newest").pack(side="right")
        self.cleanup_scope = tk.StringVar(self.top, "project")
        for value, text in (("user", "User store"), ("project", "Project store")):
            tk.Radiobutton(toolbar, text=text, value=value, variable=self.cleanup_scope, bg=colors["panel_bg"],
                           fg=colors["text"], selectcolor=colors["tree_bg"], activebackground=colors["panel_bg"],
                           activeforeground=colors["text"], font=("Arial", 10)).pack(side="right", padx=2)

        self.status = tk.StringVar(self.top, "")
        self.status_label = tk.Label(self.top, textvariable=self.status, bg=colors["status_bg"],
                                     fg=colors["status_text"], anchor="w", justify="left", wraplength=720,
                                     padx=10, pady=8)
        self.status_label.pack(side="bottom", fill="x", padx=12, pady=(0, 10))

        panes = ttk.Panedwindow(self.top, orient="horizontal", style="Review.TPanedwindow")
        panes.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        left = self.frame(panes)
        panes.add(left, weight=2)
        self.label(left, panel=True, text="GENERATIONS (newest first, F5 refreshes)").pack(anchor="w", padx=6, pady=(6, 4))
        self.generation_list = ttk.Treeview(left, columns=("scope", "kind", "files", "size", "status"),
                                            selectmode="browse")
        for column, text, width in (("#0", "Created", 150), ("scope", "Scope", 64), ("kind", "Kind", 80),
                                    ("files", "Files", 44), ("size", "Size", 64), ("status", "Status", 80)):
            self.generation_list.heading(column, text=text, anchor="w")
            self.generation_list.column(column, width=width, minwidth=40, stretch=column == "#0", anchor="w")
        self.generation_list.tag_configure("problem", foreground=colors["diff_remove"])
        self.generation_list.tag_configure("recovery", foreground=colors["diff_hunk"])
        self.generation_list.pack(fill="both", expand=True, padx=4, pady=(0, 6))
        self.generation_list.bind("<<TreeviewSelect>>", self.on_generation_selected)

        right = self.frame(panes)
        panes.add(right, weight=3)
        self.detail = tk.StringVar(self.top, "Select a generation.")
        self.label(right, panel=True, textvariable=self.detail, fg=colors["text"], anchor="w",
                   justify="left", wraplength=420).pack(fill="x", padx=6, pady=(6, 4))
        self.file_list = ttk.Treeview(right, columns=("state",), height=4, selectmode="browse")
        self.file_list.heading("#0", text="File", anchor="w")
        self.file_list.heading("state", text="Compared with current", anchor="w")
        self.file_list.column("#0", width=260, stretch=True, anchor="w")
        self.file_list.column("state", width=170, stretch=False, anchor="w")
        self.file_list.pack(fill="x", padx=4, pady=(0, 4))
        self.file_list.bind("<<TreeviewSelect>>", self.on_file_selected)
        actions = self.frame(right)
        actions.pack(fill="x", padx=4, pady=(0, 4))
        self.restore_file_button = self.button(actions, "Restore File…", self.restore_file, "accent")
        self.restore_file_button.pack(side="left")
        self.restore_all_button = self.button(actions, "Restore All Files…", self.restore_all, "accent")
        self.restore_all_button.pack(side="left", padx=6)
        self.views = ttk.Notebook(right, style="Review.TNotebook")
        self.views.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.current_box = self.add_view(self.views, "Current")
        self.diff_box = self.add_view(self.views, "Diff")
        self.backup_box = self.add_view(self.views, "Backup")
        for box in (self.current_box, self.diff_box, self.backup_box):
            box.configure(width=40)
        self.set_actions()

    # --- state -------------------------------------------------------------

    def selected_generation(self):
        selected = self.generation_list.selection()
        return self.generations.get(selected[0]) if selected else None

    def set_actions(self, generation=None, file_ready=False):
        usable = generation is not None and generation["status"] == "ok"
        self.set_button_enabled(self.restore_file_button, usable and file_ready, "accent")
        self.set_button_enabled(self.restore_all_button, usable, "accent")
        self.set_button_enabled(self.delete_button, usable, "danger")

    def clear_views(self, message=""):
        self.file_plan = None
        for box in (self.current_box, self.backup_box):
            self.show_text(box, "")
        self.show_text(self.diff_box, message)

    def refresh(self, keep_id=None):
        keep_id = keep_id or (self.selected_generation() or {}).get("key")
        try:
            listed = self.app.action("backup.list", {})["generations"]
        except (OSError, PatchError) as exc:
            self.status.set(f"Could not list backups: {exc}")
            return
        self.generations = {}
        self.generation_list.delete(*self.generation_list.get_children())
        self.file_list.delete(*self.file_list.get_children())
        self.clear_views()
        listed.sort(key=lambda g: g["id"], reverse=True)  # ids start with the UTC creation stamp
        for generation in listed:
            key = f"{generation['scope']}:{generation['id']}"
            generation["key"] = key
            self.generations[key] = generation
            tags = ("problem",) if generation["status"] != "ok" else ("recovery",) if generation["kind"] == "recovery" else ()
            self.generation_list.insert("", "end", iid=key, text=local_time(generation["created_at"]) if
                                        generation["created_at"] else generation["id"][:15],
                                        values=(generation["scope"], generation["kind"] or "—", len(generation["files"]),
                                                human_size(generation["size"]), generation["status"]), tags=tags)
        self.detail.set("Select a generation." if listed else "No backups yet.")
        self.set_actions()
        problems = sum(g["status"] != "ok" for g in listed)
        self.status.set(f"{len(listed)} generation(s)" + (f"; {problems} incomplete or corrupt (never restored or "
                                                           "deleted automatically)." if problems else "."))
        if keep_id in self.generations:
            self.generation_list.selection_set(keep_id)
            self.generation_list.see(keep_id)
            self.on_generation_selected()

    def on_generation_selected(self, _event=None):
        generation = self.selected_generation()
        self.file_list.delete(*self.file_list.get_children())
        self.clear_views()
        if generation is None:
            self.set_actions()
            return
        self.detail.set(f"{generation['id']}  ·  {generation['scope']} store  ·  {generation['kind'] or 'unknown kind'}"
                        f"  ·  {generation['action'] or '—'}")
        if generation["status"] != "ok":
            self.clear_views(f"This generation is {generation['status']}.\n\n{generation['problem']}\n\n"
                             "It is never restored or deleted by ProjectMapper.")
            self.set_actions(generation)
            return
        for index, item in enumerate(generation["files"]):
            self.file_list.insert("", "end", iid=str(index), text=item["target"], values=("…",))
        self.set_actions(generation)
        if generation["files"]:
            self.file_list.selection_set("0")
            self.on_file_selected()

    def on_file_selected(self, _event=None):
        generation, selected = self.selected_generation(), self.file_list.selection()
        if generation is None or not selected:
            return
        target = generation["files"][int(selected[0])]["target"]
        self.file_plan = None
        try:
            data = self.app.action("backup.preview", {"scope": generation["scope"], "generation": generation["id"],
                                                      "targets": [target]})
        except (OSError, PatchError) as exc:
            self.clear_views(f"Preview failed: {exc}")
            self.set_actions(generation)
            return
        (item,) = data["files"]
        state = "missing now" if not item["current_exists"] else "identical" if item["identical"] else "differs"
        self.file_list.set(selected[0], "state", state)
        self.show_text(self.current_box, item["current_text"] if item["current_text"] is not None else
                       "(file does not exist)" if not item["current_exists"] else "(not UTF-8 text)")
        self.show_diff(self.diff_box, item["diff"])
        self.show_text(self.backup_box, item["backup_text"] if item["backup_text"] is not None else "(not UTF-8 text)")
        self.views.select(VIEW_DIFF)
        self.file_plan = data["plan_id"]
        self.set_actions(generation, file_ready=True)

    # --- actions -----------------------------------------------------------

    def restore(self, plan_id):
        generation = self.selected_generation()
        try:
            result = self.app.action("backup.restore", {"plan_id": plan_id}, parent=self.top)
        except (OSError, PatchError) as exc:
            self.refresh(generation and generation["key"])
            self.status.set(f"Restore did not complete: {exc}")
            return False
        self.refresh(generation and generation["key"])
        saved = f" Previous contents saved as {result['pre_restore']}." if result.get("pre_restore") else ""
        self.status.set(f"Restored {result['count']} file(s).{saved}")
        self.app.log_message(f"Restored {result['count']} file(s) from backup {generation['id']}.{saved}")
        return True

    def restore_file(self):
        if self.file_plan:
            self.restore(self.file_plan)

    def restore_all(self):
        generation = self.selected_generation()
        if generation is None or generation["status"] != "ok":
            return
        try:
            data = self.app.action("backup.preview", {"scope": generation["scope"], "generation": generation["id"]})
        except (OSError, PatchError) as exc:
            self.status.set(f"Preview failed: {exc}")
            return
        self.restore(data["plan_id"])

    def prune(self, scope, keep, include=()):
        try:
            data = self.app.action("backup.prune_preview", {"scope": scope, "keep": keep, "include": list(include)})
        except (OSError, PatchError) as exc:
            self.status.set(f"Clean-up preview failed: {exc}")
            return
        if not data["candidates"]:
            skipped = f" {len(data['not_eligible'])} incomplete or corrupt generation(s) are never deleted." \
                if data["not_eligible"] else ""
            self.status.set(f"Nothing to clean up in the {scope} store.{skipped}")
            return
        try:
            result = self.app.action("backup.prune", {"plan_id": data["plan_id"]}, parent=self.top)
        except (OSError, PatchError) as exc:
            self.refresh()
            self.status.set(f"Clean-up did not complete: {exc}")
            return
        self.refresh()
        self.status.set(f"Deleted {result['count']} generation(s) ({human_size(data['bytes'])}) from the {scope} store.")

    def clean_up(self):
        try:
            keep = int(self.keep.get())
            if keep < 0:
                raise ValueError
        except ValueError:
            self.status.set("Keep newest must be a whole number, 0 or more.")
            return
        self.prune(self.cleanup_scope.get(), keep)

    def delete_selected(self):
        generation = self.selected_generation()
        if generation is not None and generation["status"] == "ok":
            # Explicit selection is the only way a recovery generation is ever removed.
            self.prune(generation["scope"], 10 ** 6, include=[generation["id"]])
