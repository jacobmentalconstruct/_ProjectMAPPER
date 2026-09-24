"""History window: what happened this session, and what needs attention.

Presentation only. Records come from the read-only ``history.query`` action; live
changes arrive through ``OperationHistory.subscribe`` and are debounced into one
refresh, so a busy operation's progress cannot thrash the list.
"""

from datetime import datetime
import tkinter as tk
from tkinter import ttk

try:
    from ..application.errors import label as error_label
except ImportError:
    from application.errors import label as error_label
from .patcher import PatchError
from .ui_base import ToolWindowMixin

CATEGORIES = ("All", "internal", "project", "selection", "exclusions", "capture", "snapshot", "text", "file",
              "patch", "project_patch", "backup", "output", "vendor", "application", "state")
OUTCOMES = ("All", "failed", "recovery_required", "cancelled", "succeeded", "running", "awaiting_approval")
REFRESH_DELAY_MS = 250


def clock(iso):
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%H:%M:%S")
    except (TypeError, ValueError):
        return "—"


def duration(ms):
    return "—" if ms is None else f"{ms / 1000:.2f} s"


def target(record):
    if record["paths"]:
        name = record["paths"][0].replace("\\", "/").rsplit("/", 1)[-1]
        return name + (f" (+{len(record['paths']) - 1})" if len(record["paths"]) > 1 else "")
    return "" if record["count"] is None else f"{record['count']} item(s)"


class HistoryWindow(ToolWindowMixin):
    def __init__(self, app):
        self.app = app
        self.colors = app.theme
        self.records = {}
        self.refresh_pending = None
        self.top = tk.Toplevel(app.root)
        self.configure_tool_window("History", "1100x700", (760, 520))
        self.setup_review_styles()
        self.build_ui()
        self.unsubscribe = app.controller.history.subscribe(
            lambda _record: app.gui_queue.put(self.schedule_refresh))
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        # However the window goes away, stop listening (Destroy also fires for children).
        self.top.bind("<Destroy>", lambda event: self.unsubscribe() if event.widget is self.top else None, add="+")
        self.top.bind("<F5>", lambda _event: (self.refresh(), "break")[1])
        self.refresh()

    # --- layout ------------------------------------------------------------

    def build_ui(self):
        colors = self.colors
        toolbar = self.frame(self.top)
        toolbar.pack(fill="x", padx=12, pady=8)
        self.category = tk.StringVar(self.top, "All")
        self.outcome = tk.StringVar(self.top, "All")
        self.text = tk.StringVar(self.top, "")
        self.label(toolbar, panel=True, text="Category").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.category, values=CATEGORIES, state="readonly", width=13,
                     style="Review.TCombobox").pack(side="left", padx=(4, 10))
        self.label(toolbar, panel=True, text="Outcome").pack(side="left")
        ttk.Combobox(toolbar, textvariable=self.outcome, values=OUTCOMES, state="readonly", width=17,
                     style="Review.TCombobox").pack(side="left", padx=(4, 10))
        self.label(toolbar, panel=True, text="Contains").pack(side="left")
        tk.Entry(toolbar, textvariable=self.text, width=18, bg=colors["field_bg"], fg=colors["field_text"],
                 insertbackground=colors["text"], relief="flat", font=("Arial", 10)).pack(side="left", padx=(4, 6))
        self.button(toolbar, "Clear", self.clear_filters).pack(side="left")
        self.button(toolbar, "Refresh", self.refresh).pack(side="right")
        for variable in (self.category, self.outcome, self.text):
            variable.trace_add("write", lambda *_: self.schedule_refresh())

        self.status = tk.StringVar(self.top, "")
        self.status_label = tk.Label(self.top, textvariable=self.status, bg=colors["status_bg"],
                                     fg=colors["status_text"], anchor="w", padx=10, pady=8)
        self.status_label.pack(side="bottom", fill="x", padx=12, pady=(0, 10))

        panes = ttk.Panedwindow(self.top, orient="vertical", style="Review.TPanedwindow")
        panes.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        upper = self.frame(panes)
        panes.add(upper, weight=3)
        self.operation_list = ttk.Treeview(upper, columns=("action", "origin", "status", "duration", "target"),
                                           selectmode="browse")
        for column, text, width in (("#0", "Time", 80), ("action", "Action", 190), ("origin", "Origin", 80),
                                    ("status", "Status", 130), ("duration", "Duration", 76),
                                    ("target", "Target", 200)):
            self.operation_list.heading(column, text=text, anchor="w")
            self.operation_list.column(column, width=width, minwidth=50, stretch=column == "target", anchor="w")
        self.operation_list.tag_configure("problem", foreground=colors["diff_remove"])
        self.operation_list.tag_configure("attention", foreground=colors["diff_hunk"])
        self.operation_list.tag_configure("quiet", foreground=colors["muted_text"])
        self.operation_list.pack(fill="both", expand=True, padx=4, pady=4)
        self.operation_list.bind("<<TreeviewSelect>>", lambda _event: self.show_details())

        lower = self.frame(panes)
        panes.add(lower, weight=2)
        actions = self.frame(lower)
        actions.pack(fill="x", padx=4, pady=(4, 2))
        self.label(actions, panel=True, text="DETAILS").pack(side="left")
        self.backups_button = self.button(actions, "Open Backups…", self.open_backups, "secondary")
        self.backups_button.pack(side="right")
        self.set_button_enabled(self.backups_button, False, "secondary")
        self.details = self.editor(lower)
        self.details.pack(fill="both", expand=True, padx=4, pady=(0, 4))

    # --- data --------------------------------------------------------------

    def filters(self):
        payload = {"limit": 500}
        if self.category.get() != "All":
            payload["category"] = self.category.get()
        if self.outcome.get() != "All":
            payload["outcome"] = self.outcome.get()
        if self.text.get().strip():
            payload["text"] = self.text.get().strip()
        return payload

    def schedule_refresh(self):
        if self.refresh_pending is None and self.top.winfo_exists():
            self.refresh_pending = self.top.after(REFRESH_DELAY_MS, self.refresh)

    def refresh(self):
        if self.refresh_pending is not None:
            self.top.after_cancel(self.refresh_pending)
            self.refresh_pending = None
        if not self.top.winfo_exists():
            return
        selected = self.operation_list.selection()
        try:
            operations = self.app.action("history.query", self.filters())["operations"]
        except (OSError, PatchError) as exc:
            self.status.set(f"Could not read history: {exc}")
            return
        self.records = {record["id"]: record for record in operations}
        self.operation_list.delete(*self.operation_list.get_children())
        for record in operations:
            status = record["status"].replace("_", " ")
            if record["approval"] in ("approved", "denied"):
                status += f" ({record['approval']})"
            tags = ("problem",) if record["status"] == "failed" else \
                ("attention",) if record["status"] in ("recovery_required", "awaiting_approval") else \
                ("quiet",) if record["status"] == "cancelled" else ()
            self.operation_list.insert("", "end", iid=record["id"], text=clock(record["accepted_at"]),
                                       values=(record["action"], record["origin"], status,
                                               duration(record["duration_ms"]), target(record)), tags=tags)
        attention = sum(r["status"] in ("failed", "recovery_required") for r in operations)
        self.status.set(f"{len(operations)} operation(s) shown" +
                        (f"; {attention} need attention." if attention else ".") +
                        " Session only; newest first.")
        if selected and selected[0] in self.records:
            self.operation_list.selection_set(selected[0])
            self.operation_list.see(selected[0])
        self.show_details()

    def clear_filters(self):
        self.category.set("All")
        self.outcome.set("All")
        self.text.set("")
        self.refresh()

    def selected(self):
        chosen = self.operation_list.selection()
        return self.records.get(chosen[0]) if chosen else None

    def show_details(self):
        record = self.selected()
        if record is None:
            self.show_text(self.details, "Select an operation to see its details.")
            self.set_button_enabled(self.backups_button, False, "secondary")
            return
        lines = [f"{record['action']}  ·  {record['status'].replace('_', ' ')}  ·  origin {record['origin']}",
                 f"Operation {record['id']}",
                 f"Accepted {record['accepted_at'] or '—'}   finished {record['finished_at'] or '—'}   "
                 f"duration {duration(record['duration_ms'])}"]
        if record["error"]:
            lines += ["", f"{error_label(record['error']['code'])} ({record['error']['code']})",
                      record["error"]["message"]]
        if record["approval"]:
            lines += ["", f"Approval: {record['approval']} — {record['approval_title'] or ''}"]
        if record["progress_count"]:
            lines += ["", f"Progress updates: {record['progress_count']}; last: {record['last_progress']}"]
        if record["count"] is not None:
            lines += ["", f"Count: {record['count']}"]
        if record["paths"]:
            lines += ["", "Paths:"] + [f"  {path}" for path in record["paths"]]
        if record["generations"]:
            lines += ["", "Backup generations named:"] + [f"  {name}" for name in record["generations"]]
        if record["detail"]:
            lines += ["", "Details (traceback):", record["detail"]]
        self.show_text(self.details, "\n".join(lines))
        self.set_button_enabled(self.backups_button, bool(record["generations"]), "secondary")

    def open_backups(self):
        if self.selected() and self.selected()["generations"]:
            self.app.open_backups()

    def close(self):
        self.unsubscribe()
        if self.refresh_pending is not None:
            self.top.after_cancel(self.refresh_pending)
        self.top.destroy()
