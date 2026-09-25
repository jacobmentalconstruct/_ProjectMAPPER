"""Native ProjectMapper text editor, based on the MonacoVIEWER workflow."""

import re
import hashlib
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

from .patcher import PatchError
from .ui_base import ToolWindowMixin
try:
    from ..application.desktop import Session
except ImportError:
    from application.desktop import Session


class TextEditorWindow(ToolWindowMixin):
    def __init__(self, app, path, read_only=False):
        self.app = app
        self.colors = app.theme
        self.session = Session(app, path)
        self.read_only = read_only
        self.dirty = False
        self.top = tk.Toplevel(app.root)
        self.configure_tool_window(self.title_text(), "1100x760", (700, 500))
        self.top.protocol("WM_DELETE_WINDOW", self.close)
        self.build_ui()
        self.editor.insert("1.0", self.session.source)
        self.editor.edit_modified(False)
        self.editor.bind("<<Modified>>", self.changed)
        self.editor.focus_set()
        self.stale = False
        app.editor_windows.add(self)
        self.editor.bind("<FocusIn>", lambda event: self.check_source(), add="+")

    def check_source(self):
        """Observe disk changes without replacing the user's unsaved buffer."""
        try:
            current = self.app.action("text.open", {"path": str(self.session.path)})
            self.stale = current["sha256"] != self.session.sha256
        except (OSError, PatchError):
            self.stale = True
        if self.stale:
            self.status.set("Source changed or is unavailable. Your edits are preserved; reopen before saving.")

    def title_text(self):
        marker = " •" if self.dirty else ""
        return f"{self.session.path.name}{marker} — Text Editor"

    def build_ui(self):
        toolbar = self.frame(self.top)
        toolbar.pack(fill="x", padx=12, pady=8)
        self.button(toolbar, "Open…", self.open_file, "secondary").pack(side="left")
        self.button(toolbar, "Save", self.save, "success").pack(side="left", padx=5)
        self.button(toolbar, "Save As…", self.save_as).pack(side="left")
        self.button(toolbar, "Find / Replace", self.show_find_replace).pack(side="left", padx=5)
        self.button(toolbar, "Tokenizing Patcher…", self.open_patcher, "accent").pack(side="left")
        self.read_only_var = tk.BooleanVar(self.top, self.read_only)
        self.checkbutton(toolbar, "Read-only", self.read_only_var,
                         self.toggle_read_only).pack(side="right")
        # Keep the previous bytes as a backup generation whenever this window overwrites a file.
        self.backup = tk.BooleanVar(self.top, False)
        self.checkbutton(toolbar, "Keep backup", self.backup).pack(side="right", padx=(0, 8))
        body = self.frame(self.top)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.editor = tk.Text(body, wrap="none", undo=True, font=("Consolas", 10),
                              bg=self.colors["log_bg"], fg=self.colors["text"],
                              insertbackground=self.colors["text"], selectbackground=self.colors["selection"],
                              selectforeground=self.colors["text"], relief="flat", padx=10, pady=8,
                              highlightthickness=1, highlightbackground=self.colors["panel_alt_bg"],
                              highlightcolor=self.colors["secondary"])
        self.editor.grid(row=0, column=0, sticky="nsew")
        ybar = tk.Scrollbar(body, command=self.editor.yview, bg=self.colors["panel_alt_bg"],
                            troughcolor=self.colors["log_bg"], activebackground=self.colors["secondary"])
        ybar.grid(row=0, column=1, sticky="ns")
        xbar = tk.Scrollbar(body, orient="horizontal", command=self.editor.xview,
                            bg=self.colors["panel_alt_bg"], troughcolor=self.colors["log_bg"],
                            activebackground=self.colors["secondary"])
        xbar.grid(row=1, column=0, sticky="ew")
        self.editor.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.status = tk.StringVar(self.top, "Ready.")
        tk.Label(self.top, textvariable=self.status, bg=self.colors["status_bg"], fg=self.colors["status_text"],
                 anchor="w", padx=10, pady=7, font=("Arial", 10)).pack(fill="x", padx=12, pady=(0, 10))

    def changed(self, _event=None):
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            self.dirty = True
            self.top.title(self.title_text())

    def toggle_read_only(self):
        self.read_only = self.read_only_var.get()
        self.editor.configure(state="disabled" if self.read_only else "normal")
        self.status.set("Read-only mode enabled." if self.read_only else "Editing enabled.")

    def content(self):
        state = self.editor.cget("state")
        self.editor.configure(state="normal")
        text = self.editor.get("1.0", "end-1c")
        self.editor.configure(state=state)
        return text

    def open_file(self):
        if not self.confirm_discard():
            return
        selected = filedialog.askopenfilename(parent=self.top, initialdir=self.session.path.parent,
                                              filetypes=(("Text files", "*.txt *.py *.md *.json *.js *.ts *.css *.html"),
                                                         ("All files", "*.*")))
        if not selected:
            return
        try:
            self.session = Session(self.app, selected)
        except (OSError, PatchError) as exc:
            self.status.set(f"Open failed: {exc}")
            return
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", self.session.source)
        self.editor.edit_modified(False)
        self.dirty = False
        self.toggle_read_only()
        self.top.title(self.title_text())
        self.status.set(f"Opened: {self.session.path}")

    def save(self):
        if self.read_only:
            self.status.set("Read-only mode is enabled. Disable it before saving.")
            return
        try:
            text = self.content()
            result = self.app.action("text.save", {"path": str(self.session.path), "text": text,
                "sha256": hashlib.sha256(self.session.original_bytes).hexdigest(), "backup": self.backup.get()})
            path = Path(result["path"])
            self.session = Session(self.app, path)
        except (OSError, PatchError) as exc:
            self.status.set(f"Save failed: {exc}")
            return
        self.dirty = False
        self.top.title(self.title_text())
        self.status.set(f"Saved: {path}")
        self.app.file_transformed(path)

    def save_as(self):
        if self.read_only:
            self.status.set("Read-only mode is enabled. Disable it before saving.")
            return
        selected = filedialog.asksaveasfilename(parent=self.top, initialdir=self.session.path.parent,
                                                initialfile=self.session.path.name,
                                                filetypes=(("All files", "*.*"),))
        if not selected:
            return
        try:
            result = self.app.action("text.save_as", {"path": selected, "text": self.content(),
                                                      "backup": self.backup.get()}, parent=self.top)
            path = Path(result["path"])
        except (OSError, PatchError) as exc:
            self.status.set(f"Save As failed: {exc}")
            return
        self.session = Session(self.app, path)
        self.dirty = False
        self.top.title(self.title_text())
        self.status.set(f"Saved as: {path}")
        self.app.file_transformed(path)

    def show_find_replace(self):
        if getattr(self, "find_window", None) and self.find_window.winfo_exists():
            self.find_window.lift()
            return
        self.find_window = tk.Toplevel(self.top)
        self.find_window.title("Find / Replace")
        self.find_window.configure(bg=self.colors["panel_bg"])
        self.find_window.transient(self.top)
        find = tk.StringVar(self.find_window)
        replace = tk.StringVar(self.find_window)
        for row, label, variable in ((0, "Find:", find), (1, "Replace:", replace)):
            tk.Label(self.find_window, text=label, bg=self.colors["panel_bg"], fg=self.colors["text"]).grid(row=row, column=0, padx=8, pady=7)
            tk.Entry(self.find_window, textvariable=variable, width=38, bg=self.colors["field_bg"], fg=self.colors["field_text"],
                     insertbackground=self.colors["text"], relief="flat").grid(row=row, column=1, padx=8, pady=7)
        self.button(self.find_window, "Find Next", lambda: self.find_next(find.get())).grid(row=2, column=0, padx=8, pady=8)
        self.button(self.find_window, "Replace All", lambda: self.replace_all(find.get(), replace.get()), "accent").grid(row=2, column=1, padx=8, pady=8)

    def find_next(self, value):
        if not value:
            return
        offset = len(self.editor.get("1.0", "insert"))
        found = self.app.action("text.find", {"text": self.content(), "query": value, "start": offset})
        if found["index"] >= 0:
            start = f"1.0+{found['index']}c"
            end = f"{start}+{len(value)}c"
            self.editor.tag_remove("found", "1.0", "end")
            self.editor.tag_add("found", start, end)
            self.editor.tag_configure("found", background=self.colors["selection"])
            self.editor.mark_set("insert", end)
            self.editor.see(start)

    def replace_all(self, value, replacement):
        if self.read_only or not value:
            return
        result = self.app.action("text.replace", {"text": self.content(), "query": value, "replacement": replacement})
        count = result["count"]
        if not count:
            self.status.set("No matches found.")
            return
        if not messagebox.askyesno("Replace all?", f"Replace {count} occurrence(s)?", parent=self.top, default="no"):
            return
        text = result["text"]
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_modified(False)
        self.dirty = True
        self.top.title(self.title_text())
        self.status.set(f"Replaced {count} occurrence(s). Save to write the file.")

    def open_patcher(self):
        if self.dirty and not messagebox.askyesno("Open patcher?", "Discard unsaved editor changes?", parent=self.top, default="no"):
            return
        self.app.open_tokenizing_patcher(self.session.path)

    def confirm_discard(self):
        return (not self.dirty) or messagebox.askyesno("Discard changes?", "Discard unsaved editor changes?", parent=self.top, default="no")

    def close(self):
        if self.confirm_discard():
            self.top.destroy()
