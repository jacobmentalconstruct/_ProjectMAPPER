"""Dark-theme review and approval window for project patch manifests."""

import json
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

try:
    from ..core.diff import DiffFile, diff_summary
except ImportError:
    from core.diff import DiffFile, diff_summary
from .patcher import PatchError
from .ui_base import ToolWindowMixin


SCHEMA = json.dumps({"version": 1, "description": "Project patch", "files": [{
    "path": "src/example.py",
    "sha256": "optional-original-file-hash",
    "hunks": [{"description": "Describe the change", "search_block": "old", "replace_block": "new", "use_patch_indent": False}]
}]}, indent=2)


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
        self.top = tk.Toplevel(app.root)
        self.configure_tool_window(f"Project Patcher — {root.name}", "1050x720", (720, 500))
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()

    def build_ui(self):
        toolbar = self.frame(self.top)
        toolbar.pack(fill="x", padx=12, pady=8)
        tk.Label(toolbar, text=f"Project root: {self.root_path}", bg=self.colors["panel_bg"],
                 fg=self.colors["muted_text"], anchor="w").pack(side="left", fill="x", expand=True, padx=8)
        self.button(toolbar, "Copy Schema", self.copy_schema).pack(side="right")
        self.button(toolbar, "Load Patch JSON", self.load_patch, "secondary").pack(side="right", padx=6)
        self.button(toolbar, "Add File…", self.add_file, "secondary").pack(side="right", padx=6)
        self.force_indent = tk.BooleanVar(self.top, False)
        self.backup = tk.BooleanVar(self.top, False)
        self.checkbutton(toolbar, "Force patch indentation", self.force_indent,
                         self.invalidate).pack(side="left", padx=12)
        self.checkbutton(toolbar, "Keep .bak backups", self.backup).pack(side="left", padx=4)
        body = self.frame(self.top)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        self.manifest_box = self.editor(body, True)
        self.manifest_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.diff_box = self.editor(body, False)
        self.diff_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.manifest_box.insert("1.0", SCHEMA)
        self.manifest_box.edit_modified(False)
        self.manifest_box.bind("<<Modified>>", self.changed)
        footer = self.frame(self.top)
        footer.pack(fill="x", padx=12, pady=6)
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
        self.status = tk.StringVar(self.top, "Validate the complete manifest before applying anything.")
        tk.Label(self.top, textvariable=self.status, bg=self.colors["status_bg"], fg=self.colors["status_text"],
                 anchor="w", padx=10, pady=8).pack(fill="x", padx=12, pady=(0, 10))

    def copy_schema(self):
        self.top.clipboard_clear()
        self.top.clipboard_append(self.app.action("patch.schema", {"project": True})["text"])
        self.status.set("Project patch schema copied.")

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
        self.apply_button.configure(state="normal" if self.actions_linked or can_apply else "disabled")

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
        self.diff_box.configure(state="normal")
        self.diff_box.delete("1.0", "end")
        self.diff_box.configure(state="disabled")
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
            self.session = plan["plan_id"]
            self.results = plan["files"]
            self.validated_inputs = self.inputs()
            self.diff_box.configure(state="normal")
            self.diff_box.delete("1.0", "end")
            self.diff_box.insert("1.0", plan["diff"])
            self.diff_box.configure(state="disabled")
            self.refresh_action_group()
            summary = diff_summary(DiffFile(item["relative_path"], item["original"], item["patched"])
                                   for item in self.results)
            self.status.set(f"Validated {len(self.results)} file(s): +{summary['additions']} / -{summary['deletions']}. Review the full diff, then approve the apply step.")
            return True
        except (PatchError, OSError) as exc:
            self.status.set(f"Validation failed: {exc}")
            return False

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
            paths = [Path(path) for path in result.get("paths", [])]
        except (OSError, PatchError) as exc:
            self.status.set(f"Apply failed: {exc}")
            self.apply_button.configure(state="disabled")
            return
        self.app.log_message(f"Applied project patch to {len(paths)} file(s). Compile a new snapshot before exporting.")
        self.app.request_rescan_tree_silent()
        self.session = None
        self.results = None
        self.manifest_dirty = False
        self.refresh_action_group()
        self.status.set(f"Applied {len(paths)} file(s); the project tree is refreshing.")

    def close(self):
        if self.manifest_dirty and not messagebox.askyesno(
                "Discard project patch?", "Close without applying this project patch?",
                parent=self.top, default="no"):
            return
        self.top.destroy()
