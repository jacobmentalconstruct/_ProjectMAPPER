"""Tokenizing patcher window, owned by the ProjectMapper Tk application."""

import difflib
import hashlib
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .ui_base import ToolWindowMixin
try:
    from ..application.desktop import Session
except ImportError:
    from application.desktop import Session
try:
    from ..core.diff import DiffFile, diff_summary
except ImportError:
    from core.diff import DiffFile, diff_summary

if __package__:
    from .patcher import PatchError
else:
    from patcher import PatchError


SCHEMA = json.dumps({"hunks": [{
    "description": "Describe the change",
    "search_block": "exact text to find\n(can span multiple lines)",
    "replace_block": "replacement text\n(same or different length)",
    "use_patch_indent": False,
}]}, indent=2)


class PatcherWindow(ToolWindowMixin):
    def __init__(self, app, path):
        self.session = Session(app, path)
        self.app = app
        self.colors = app.theme
        self.preview = None
        self.result = None
        self.validated_inputs = None
        self.actions_linked = False
        self.top = tk.Toplevel(app.root)
        self.configure_tool_window(f"Tokenizing Patcher — {self.session.path.name}", "1100x780", (760, 550))
        self.setup_review_styles()
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.path_label = self.label(self.top, text=str(self.session.path), wraplength=1000)
        self.path_label.pack(fill="x", padx=12, pady=8)
        toolbar = self.frame(self.top)
        toolbar.pack(fill="x", padx=12)
        self.button(toolbar, "Reload Target", self.reload).pack(side="left")
        self.button(toolbar, "Load Patch JSON", self.load_patch, "secondary").pack(side="left", padx=6)
        self.button(toolbar, "Copy Schema", self.copy_schema).pack(side="left")
        self.force_indent = tk.BooleanVar(self.top, False)
        self.checkbutton(toolbar, "Force patch indentation", self.force_indent,
                         self.invalidate).pack(side="left", padx=12)
        panes = ttk.Panedwindow(self.top, orient="horizontal", style="Review.TPanedwindow")
        panes.pack(fill="both", expand=True, padx=12, pady=10)
        self.views = ttk.Notebook(panes, style="Review.TNotebook")
        panes.add(self.views, weight=1)
        self.source_box = self.add_view(self.views, "Source")
        self.diff_box = self.add_view(self.views, "Diff preview")
        self.result_box = self.add_view(self.views, "Result")
        right = self.frame(panes)
        panes.add(right, weight=1)
        self.label(right, text="JSON PATCH", panel=True).pack(anchor="w", padx=8, pady=(6, 2))
        self.label(right, text="All hunks target the original source", panel=True).pack(anchor="w", padx=8, pady=(0, 6))
        self.patch_box = self.editor(right, editable=True)
        self.patch_box.pack(fill="both", expand=True)
        self.patch_box.insert("1.0", SCHEMA)
        self.patch_box.edit_modified(False)
        self.patch_box.bind("<<Modified>>", self.patch_changed)
        footer = self.frame(self.top)
        footer.pack(side="bottom", fill="x", padx=12, pady=5, before=panes)
        self.action_group = self.frame(footer)
        self.action_group.configure(padx=4, pady=4)
        self.action_group.pack(side="left")
        self.validate_button = self.button(self.action_group, "Validate / Preview",
                                           lambda: self.run_action("validate"), "success")
        self.validate_button.pack(side="left")
        self.link_button = self.button(self.action_group, "&", self.toggle_action_link)
        self.link_button.configure(width=3, padx=2)
        self.link_button.pack(side="left", padx=3)
        self.apply_button = self.button(self.action_group, "Apply to Result",
                                        lambda: self.run_action("apply"), "secondary", state="disabled")
        self.apply_button.pack(side="left")
        self.set_button_enabled(self.apply_button, False, "secondary")
        self.save_button = self.button(footer, "Save Result", self.save, "accent", state="disabled")
        self.save_button.pack(side="right")
        self.set_button_enabled(self.save_button, False, "accent")
        self.version = tk.BooleanVar(self.top, False)
        self.backup = tk.BooleanVar(self.top, False)
        options = self.frame(self.top)
        options.pack(side="bottom", fill="x", padx=12, pady=(0, 5), before=panes)
        self.checkbutton(options, "Save as version", self.version).pack(side="left", padx=(0, 4))
        self.checkbutton(options, "Keep .bak backup", self.backup).pack(side="left", padx=(10, 4))
        self.suffix = tk.StringVar(self.top, "_v1.0")
        tk.Entry(options, textvariable=self.suffix, width=14,
                 bg=self.colors["field_bg"], fg=self.colors["field_text"],
                 insertbackground=self.colors["text"], selectbackground=self.colors["selection"],
                 selectforeground=self.colors["text"], relief="flat", font=("Arial", 10)).pack(side="left", pady=5)
        self.status = tk.StringVar(self.top, "Paste a patch, validate it, then apply and save the result.")
        tk.Label(self.top, textvariable=self.status, wraplength=700, anchor="w", justify="left",
                 bg=self.colors["status_bg"], fg=self.colors["status_text"],
                 font=("Arial", 10), padx=10, pady=8).pack(
            side="bottom", fill="x", padx=12, pady=10, before=footer)
        self.show_text(self.source_box, self.session.source)

    def inputs(self):
        return self.patch_box.get("1.0", "end-1c"), self.force_indent.get()

    def toggle_action_link(self):
        self.actions_linked = not self.actions_linked
        self.refresh_action_group()
        self.status.set(
            "Linked: either button validates and applies to Result. Save Result still writes to disk."
            if self.actions_linked else "Unlinked: Validate / Preview and Apply to Result work separately.")

    def refresh_action_group(self):
        colors = self.colors
        self.action_group.configure(bg=colors["linked"] if self.actions_linked else colors["panel_bg"])
        for button, normal in ((self.validate_button, "success"), (self.apply_button, "secondary")):
            color = "linked" if self.actions_linked else normal
            button.configure(bg=colors[color], activebackground=colors[color + "_hover"])
        self.link_button.configure(
            bg=colors["linked_hover"] if self.actions_linked else colors["panel_alt_bg"],
            activebackground=colors["linked"] if self.actions_linked else colors["field_bg_alt"],
            relief="sunken" if self.actions_linked else "raised")
        can_apply = self.preview is not None and self.validated_inputs == self.inputs()
        self.set_button_enabled(self.apply_button, self.actions_linked or can_apply,
                                "linked" if self.actions_linked else "secondary")

    def run_action(self, action):
        if self.actions_linked:
            if self.validate():
                self.apply()
        elif action == "validate":
            self.validate()
        else:
            self.apply()

    def invalidate(self):
        self.preview = self.result = self.validated_inputs = None
        self.refresh_action_group()
        self.set_button_enabled(self.save_button, False, "accent")
        self.show_text(self.diff_box, "")
        self.show_text(self.result_box, "")
        self.status.set("Patch changed. Validate again before applying.")

    def patch_changed(self, _event=None):
        if self.patch_box.edit_modified():
            self.patch_box.edit_modified(False)
            self.invalidate()

    def validate(self):
        self.invalidate()
        try:
            patch_text, force = self.inputs()
            plan = self.app.action("patch.validate", {"path": str(self.session.path),
                "patch": patch_text, "force_indent": force,
                "sha256": hashlib.sha256(self.session.original_bytes).hexdigest()})
            self.plan_id = plan["plan_id"]
            self.preview = plan["text"]
            self.validated_inputs = (patch_text, force)
            diff = "\n".join(difflib.unified_diff(
                self.session.source.splitlines(), self.preview.splitlines(),
                fromfile=str(self.session.path), tofile="patched result", lineterm=""))
            self.show_diff(self.diff_box, diff or "(No differences)")
            self.views.select(1)
            self.refresh_action_group()
            summary = diff_summary((DiffFile(str(self.session.path), self.session.source, self.preview),))
            self.status.set(f"Validated: +{summary['additions']} / -{summary['deletions']}. Review the diff, then Apply to Result. The file has not been changed.")
            return True
        except (ValueError, PatchError) as exc:
            self.status.set(f"Validation failed: {exc}")
            return False

    def apply(self):
        if self.preview is None or self.validated_inputs != self.inputs():
            self.invalidate()
            return
        try:
            self.result = self.app.action("patch.result", {"plan_id": self.plan_id})["text"]
        except PatchError as exc:
            self.invalidate()
            self.status.set(f"Apply failed: {exc}")
            return
        self.show_text(self.result_box, self.result)
        self.views.select(2)
        self.set_button_enabled(self.save_button, True, "accent")
        self.status.set("Result ready. Save Result writes it to disk.")

    def save(self):
        if self.result is None or self.validated_inputs != self.inputs():
            self.invalidate()
            return
        # Do not modify sources while another app operation is capturing them.
        if self.app.running_tasks or self.app.scan_pending:
            self.status.set("Wait for the current scan or compile to finish before saving.")
            return
        try:
            data = {"plan_id": self.plan_id,
                    "suffix": self.suffix.get() if self.version.get() else None,
                    "backup": self.backup.get()}
            saved = self.app.action("patch.save", data)
            path = Path(saved["path"])
            self.session = Session(self.app, path)
        except (OSError, PatchError) as exc:
            self.status.set(f"Save failed: {exc}")
            return
        self.invalidate()
        self.show_text(self.source_box, self.session.source)
        self.views.select(0)
        self.path_label.config(text=str(path))
        self.top.title(f"Tokenizing Patcher — {path.name}")
        self.status.set(f"Saved: {path}. The source now shows the saved file.")
        self.app.file_transformed(path)

    def reload(self):
        if self.result is not None and not messagebox.askyesno(
                "Discard unsaved result?", "Reload the file and discard the unsaved result?", parent=self.top):
            return
        try:
            session = Session(self.app, self.session.path)
        except (OSError, PatchError) as exc:
            self.status.set(f"Reload failed: {exc}")
            return
        self.session = session
        self.invalidate()
        self.show_text(self.source_box, self.session.source)
        self.views.select(0)
        self.status.set("Target reloaded. Validate the patch against this source.")

    def load_patch(self):
        path = filedialog.askopenfilename(parent=self.top, filetypes=[("JSON patch", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            text = self.app.action("patch.load", {"path": path})["text"]
        except (OSError, UnicodeError, PatchError) as exc:
            self.status.set(f"Could not load patch: {exc}")
            return
        self.patch_box.delete("1.0", "end")
        self.patch_box.insert("1.0", text)
        self.invalidate()

    def copy_schema(self):
        self.top.clipboard_clear()
        self.top.clipboard_append(self.app.action("patch.schema")["text"])
        self.status.set("Patch schema copied.")

    def close(self):
        if self.result is not None and not messagebox.askyesno(
                "Discard unsaved result?", "Close without saving the patched result?", parent=self.top):
            return
        self.top.destroy()
