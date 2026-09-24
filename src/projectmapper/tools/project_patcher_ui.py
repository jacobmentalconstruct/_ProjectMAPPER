"""Dark-theme review and approval window for project patch manifests."""

import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from ..core.diff import DiffFile, diff_line_kinds, diff_summary, unified_diff_text
except ImportError:
    from core.diff import DiffFile, diff_line_kinds, diff_summary, unified_diff_text
from .patcher import PatchError
from .project_patcher import SKELETON_MANIFEST
from .ui_base import ToolWindowMixin


SKELETON = json.dumps(SKELETON_MANIFEST, indent=2)
STATUS_LABELS = {"changed": "changed", "no_change": "no change", "error": "error"}
VIEW_SOURCE, VIEW_DIFF, VIEW_RESULT = range(3)


class ProjectPatcherWindow(ToolWindowMixin):
    def __init__(self, app, root):
        self.app = app
        self.colors = app.theme
        self.root_path = root
        self.session = None
        self.results = None
        self.validated_inputs = None
        self.actions_linked = False
        self.manifest_dirty = False
        self.review = []
        self.file_index = None
        self.hunk_index = None
        self.hunks = []
        self.top = tk.Toplevel(app.root)
        self.configure_tool_window(f"Project Patcher — {root.name}", "1180x760", (720, 500))
        self.setup_review_styles()
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()
        self.bind_keys()

    def build_ui(self):
        toolbar = self.frame(self.top)
        toolbar.pack(fill="x", padx=12, pady=8)
        self.button(toolbar, "Copy Schema", self.copy_schema).pack(side="right")
        self.button(toolbar, "Load Patch JSON", self.load_patch, "secondary").pack(side="right", padx=6)
        self.button(toolbar, "Add File…", self.add_file, "secondary").pack(side="right", padx=6)
        self.force_indent = tk.BooleanVar(self.top, False)
        self.backup = tk.BooleanVar(self.top, False)
        self.checkbutton(toolbar, "Force patch indentation", self.force_indent,
                         self.invalidate).pack(side="left", padx=(4, 12))
        self.label(self.top, text=f"Project root: {self.root_path}").pack(fill="x", padx=14)

        # Status and actions are packed before the panes so a small window never hides them.
        self.status = tk.StringVar(self.top, "Add files or paste a manifest, then validate the complete patch.")
        self.status_label = tk.Label(self.top, textvariable=self.status, bg=self.colors["status_bg"],
                                     fg=self.colors["status_text"], anchor="w", justify="left",
                                     wraplength=680, padx=10, pady=8)
        self.status_label.pack(side="bottom", fill="x", padx=12, pady=(0, 10))
        footer = self.frame(self.top)
        footer.pack(side="bottom", fill="x", padx=12, pady=6)
        self.action_group = self.frame(footer)
        self.action_group.configure(padx=4, pady=4)
        self.action_group.pack(side="left")
        self.validate_button = self.button(self.action_group, "Validate / Preview",
                                           lambda: self.run_action("validate"), "success")
        self.validate_button.pack(side="left")
        self.link_button = self.button(self.action_group, "&", self.toggle_action_link)
        self.link_button.configure(width=3, padx=2)
        self.link_button.pack(side="left", padx=3)
        self.apply_button = self.button(self.action_group, "Apply Project Patch",
                                        lambda: self.run_action("apply"), "accent", state="disabled")
        self.apply_button.pack(side="left")
        self.set_button_enabled(self.apply_button, False, "accent")
        # Backups are an apply option, so the choice sits beside Apply.
        self.checkbutton(footer, "Keep backups", self.backup).pack(side="left", padx=12)

        panes = ttk.Panedwindow(self.top, orient="horizontal", style="Review.TPanedwindow")
        panes.pack(fill="both", expand=True, padx=12, pady=(4, 6))
        left = self.frame(panes)
        self.label(left, text="PROJECT PATCH MANIFEST", panel=True).pack(anchor="w", padx=8, pady=(6, 4))
        self.manifest_box = self.editor(left, True)
        self.manifest_box.configure(width=40)  # Requested width; the pane still stretches.
        self.manifest_box.pack(fill="both", expand=True)
        self.manifest_box.insert("1.0", SKELETON)
        self.manifest_box.edit_modified(False)
        self.manifest_box.bind("<<Modified>>", self.changed)
        panes.add(left, weight=2)

        right = self.frame(panes)
        panes.add(right, weight=3)
        header = self.frame(right)
        header.pack(fill="x", padx=4, pady=(6, 0))
        self.position = tk.StringVar(self.top, "No review yet")
        self.position_label = self.label(header, panel=True, textvariable=self.position, fg=self.colors["text"])
        self.position_label.pack(side="left")
        self.label(header, panel=True, text="Alt+↑/↓ · F8 · Ctrl+Enter").pack(side="right")
        self.file_list = ttk.Treeview(right, columns=("status", "add", "del", "hunks"), height=4,
                                      selectmode="browse")
        for column, text, width in (("#0", "File", 220), ("status", "Status", 150), ("add", "+", 48),
                                    ("del", "−", 48), ("hunks", "Hunks", 56)):
            self.file_list.heading(column, text=text, anchor="w")
            self.file_list.column(column, width=width, minwidth=40, stretch=column == "#0", anchor="w")
        self.file_list.tag_configure("error", foreground=self.colors["diff_remove"])
        self.file_list.pack(fill="x", padx=4, pady=(6, 4))
        self.file_list.bind("<<TreeviewSelect>>", self.on_file_selected)

        nav = self.frame(right)
        nav.pack(fill="x", padx=4, pady=(0, 4))
        self.prev_file_button = self.button(nav, "◀ File", lambda: self.step_file(-1), state="disabled")
        self.next_file_button = self.button(nav, "File ▶", lambda: self.step_file(1), state="disabled")
        self.prev_hunk_button = self.button(nav, "◀ Hunk", lambda: self.step_hunk(-1), state="disabled")
        self.next_hunk_button = self.button(nav, "Hunk ▶", lambda: self.step_hunk(1), state="disabled")
        for button in (self.prev_file_button, self.next_file_button, self.prev_hunk_button, self.next_hunk_button):
            button.pack(side="left", padx=(0, 4))

        self.views = ttk.Notebook(right, style="Review.TNotebook")
        self.views.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.source_box = self.add_view(self.views, "Source")
        self.diff_box = self.add_view(self.views, "Diff")
        self.result_box = self.add_view(self.views, "Result")
        for box in (self.source_box, self.diff_box, self.result_box):
            box.configure(width=40)
            box.tag_configure("current_hunk", background=self.colors["heading_bg"])

    def bind_keys(self):
        def bound(action):
            return lambda _event: (action(), "break")[1]
        for sequence, action in (("<Alt-Down>", lambda: self.step_file(1)), ("<Alt-Up>", lambda: self.step_file(-1)),
                                 ("<F8>", lambda: self.step_hunk(1)), ("<Shift-F8>", lambda: self.step_hunk(-1)),
                                 ("<Control-Return>", self.validate)):
            self.top.bind(sequence, bound(action))
        # The manifest's own Return binding would otherwise insert a newline first.
        self.manifest_box.bind("<Control-Return>", bound(self.validate))

    # --- Review list and navigation (presentation only) ---

    def clear_review(self):
        self.review, self.hunks = [], []
        self.file_index = self.hunk_index = None
        self.file_list.delete(*self.file_list.get_children())
        for box in (self.source_box, self.diff_box, self.result_box):
            self.show_text(box, "")
        self.update_navigation()

    def show_review(self, outcomes):
        self.clear_review()
        self.review = list(outcomes)
        for index, item in enumerate(self.review):
            flags = [flag for flag, key in (("empty result", "empty_result"), ("final newline", "final_newline_changed"))
                     if item.get(key)]
            status = " · ".join([STATUS_LABELS[item["status"]], *flags])
            error = item["status"] == "error"
            self.file_list.insert("", "end", iid=str(index), text=item["relative_path"],
                                  values=(status, "" if error else f"+{item['additions']}",
                                          "" if error else f"-{item['deletions']}", item["hunk_count"]),
                                  tags=("error",) if error else ())
        if self.review:
            first = next((i for i, item in enumerate(self.review) if item["status"] == "error"),
                         next((i for i, item in enumerate(self.review) if item["status"] == "changed"), 0))
            self.select_file(first)

    def on_file_selected(self, _event=None):
        selected = self.file_list.selection()
        if selected and int(selected[0]) != self.file_index:
            self.show_file(int(selected[0]))

    def select_file(self, index):
        self.show_file(index)
        self.file_list.selection_set(str(index))
        self.file_list.focus(str(index))
        self.file_list.see(str(index))

    def show_file(self, index):
        item = self.review[index]
        self.file_index = index
        if item["status"] == "error":
            self.hunks = []
            self.show_text(self.source_box, "")
            self.show_text(self.diff_box, f"Validation error\n\n{item['error']}")
            self.show_text(self.result_box, "")
            self.views.select(VIEW_DIFF)
        else:
            text = unified_diff_text([DiffFile(item["relative_path"], item["original"], item["patched"])])
            if item.get("final_newline_changed"):
                text += "\n\n(The final newline changes; line diffs do not show it.)"
            self.show_diff(self.diff_box, text)
            self.show_text(self.source_box, item["original"])
            self.show_text(self.result_box, item["patched"])
            starts = [number for number, kind in enumerate(diff_line_kinds(text), 1) if kind == "hunk"]
            ends = starts[1:] + [len(text.split("\n")) + 1]
            self.hunks = [dict(ranges, diff_start=start, diff_end=end)
                          for ranges, start, end in zip(item["diff_hunks"], starts, ends)]
        self.hunk_index = 0 if self.hunks else None
        self.focus_hunk()

    def focus_hunk(self):
        for box in (self.source_box, self.diff_box, self.result_box):
            box.tag_remove("current_hunk", "1.0", "end")
        if self.hunk_index is not None:
            hunk = self.hunks[self.hunk_index]
            for box, start, end in ((self.diff_box, hunk["diff_start"], hunk["diff_end"]),
                                    (self.source_box, hunk["original_start"] + 1, hunk["original_end"] + 1),
                                    (self.result_box, hunk["patched_start"] + 1, hunk["patched_end"] + 1)):
                box.tag_add("current_hunk", f"{start}.0", f"{end}.0")
                box.see(f"{end}.0")
                box.see(f"{start}.0")
        self.update_navigation()

    def step_file(self, offset):
        if self.file_index is not None and 0 <= self.file_index + offset < len(self.review):
            self.select_file(self.file_index + offset)

    def step_hunk(self, offset):
        if self.hunk_index is not None and 0 <= self.hunk_index + offset < len(self.hunks):
            self.hunk_index += offset
            self.focus_hunk()

    def update_navigation(self):
        def enable(button, allowed):
            button.configure(state="normal" if allowed else "disabled")
        files, hunks = len(self.review), len(self.hunks)
        has_file = self.file_index is not None
        enable(self.prev_file_button, has_file and self.file_index > 0)
        enable(self.next_file_button, has_file and self.file_index < files - 1)
        enable(self.prev_hunk_button, self.hunk_index is not None and self.hunk_index > 0)
        enable(self.next_hunk_button, self.hunk_index is not None and self.hunk_index < hunks - 1)
        if not has_file:
            self.position.set("No review yet")
            return
        item = self.review[self.file_index]
        detail = ("validation error" if item["status"] == "error" else
                  f"Hunk {self.hunk_index + 1}/{hunks}" if hunks else "no line changes")
        self.position.set(f"File {self.file_index + 1}/{files} · {detail}")

    # --- Manifest editing and actions ---

    def copy_schema(self):
        self.top.clipboard_clear()
        self.top.clipboard_append(self.app.action("patch.schema", {"project": True})["text"])
        self.status.set("Example project patch copied.")

    def add_file(self):
        selected = filedialog.askopenfilename(parent=self.top, initialdir=self.root_path,
                                              filetypes=(("Text files", "*.txt *.py *.md *.json *.js *.ts *.css *.html"),
                                                         ("All files", "*.*")))
        if not selected:
            return
        try:
            result = self.app.action("project_patch.add_entry", {"root": str(self.root_path),
                "path": selected, "manifest": self.inputs()[0]})
            self.manifest_box.delete("1.0", "end")
            self.manifest_box.insert("1.0", result["text"])
            self.manifest_box.edit_modified(False)
            self.manifest_dirty = True
            self.invalidate()
            self.status.set("Added project patch entry. Edit its hunks, then validate.")
        except (OSError, ValueError, PatchError) as exc:
            self.status.set(f"Could not add file: {exc}")

    def changed(self, _event=None):
        if self.manifest_box.edit_modified():
            self.manifest_box.edit_modified(False)
            self.manifest_dirty = True
            self.invalidate()

    def inputs(self):
        return self.manifest_box.get("1.0", "end-1c"), self.force_indent.get()

    def toggle_action_link(self):
        self.actions_linked = not self.actions_linked
        self.refresh_action_group()
        self.status.set("Linked: either button validates and applies the project patch."
                        if self.actions_linked else
                        "Unlinked: Validate / Preview and Apply Project Patch work separately.")

    def refresh_action_group(self):
        colors = self.colors
        self.action_group.configure(bg=colors["linked"] if self.actions_linked else colors["panel_bg"])
        for button, normal in ((self.validate_button, "success"), (self.apply_button, "accent")):
            color = "linked" if self.actions_linked else normal
            button.configure(bg=colors[color], activebackground=colors[color + "_hover"])
        self.link_button.configure(bg=colors["linked_hover"] if self.actions_linked else colors["panel_alt_bg"],
                                   activebackground=colors["linked"] if self.actions_linked else colors["field_bg_alt"],
                                   relief="sunken" if self.actions_linked else "raised")
        can_apply = self.results is not None
        self.set_button_enabled(self.apply_button, self.actions_linked or can_apply,
                                "linked" if self.actions_linked else "accent")

    def run_action(self, action):
        if self.actions_linked:
            if self.validate():
                self.apply()
        elif action == "validate":
            self.validate()
        else:
            self.apply()

    def invalidate(self):
        self.validated_inputs = None
        self.session = None
        self.results = None
        self.refresh_action_group()
        self.clear_review()
        self.status.set("Project patch changed. Validate again before applying.")

    def load_patch(self):
        path = filedialog.askopenfilename(parent=self.top, filetypes=(("JSON patch", "*.json"), ("All files", "*.*")))
        if not path:
            return
        try:
            text = self.app.action("patch.load", {"path": path})["text"]
        except (OSError, UnicodeError, PatchError) as exc:
            self.status.set(f"Could not load patch: {exc}")
            return
        self.manifest_box.delete("1.0", "end")
        self.manifest_box.insert("1.0", text)
        self.manifest_box.edit_modified(False)
        self.manifest_dirty = True
        self.invalidate()
        self.status.set(f"Loaded project patch: {path}")

    def validate(self):
        self.invalidate()
        try:
            plan = self.app.action("project_patch.validate", {
                "root": str(self.root_path), "manifest": self.inputs()[0],
                "force_indent": self.force_indent.get()})
        except (PatchError, OSError) as exc:
            self.status.set(f"Validation failed: {exc}")
            return False
        self.show_review(plan["files"])
        if not plan["valid"]:
            errors = plan["errors"]
            self.status.set(f"Validation failed for {len(errors)} of {len(plan['files'])} file(s): "
                            + "; ".join(errors))
            return False
        self.session = plan["plan_id"]
        self.results = plan["files"]
        self.validated_inputs = self.inputs()
        self.refresh_action_group()
        summary = diff_summary(DiffFile(item["relative_path"], item["original"], item["patched"])
                               for item in self.results)
        self.status.set(f"Validated {len(self.results)} file(s): +{summary['additions']} / -{summary['deletions']}. "
                        "Review each file, then approve the apply step.")
        return True

    def apply(self):
        if self.session is None or self.results is None:
            return
        if self.validated_inputs != self.inputs():
            self.invalidate()
            return
        reviewed = self.validated_inputs
        plan_id = self.session
        backup = self.backup.get()
        if self.inputs() != reviewed or self.backup.get() != backup:
            self.invalidate()
            return
        if self.app.running_tasks or self.app.scan_pending:
            self.status.set("Wait for the current scan or compile to finish before applying.")
            return
        try:
            result = self.app.action("project_patch.apply", {
                "plan_id": plan_id, "backup": backup}, parent=self.top,
                approval_guard=lambda: self.session == plan_id and self.inputs() == reviewed and self.backup.get() == backup)
            count = len(result.get("paths", []))
        except (OSError, PatchError) as exc:
            self.status.set(f"Apply failed: {exc}")
            self.set_button_enabled(self.apply_button, False, "accent")
            return
        self.app.log_message(f"Applied project patch to {count} file(s). Compile a new snapshot before exporting.")
        self.app.request_rescan_tree_silent()
        self.session = None
        self.results = None
        self.manifest_dirty = False
        self.refresh_action_group()
        self.clear_review()
        self.status.set(f"Applied {count} file(s); the project tree is refreshing.")

    def close(self):
        if self.manifest_dirty and not messagebox.askyesno(
                "Discard project patch?", "Close without applying this project patch?",
                parent=self.top, default="no"):
            return
        self.top.destroy()
