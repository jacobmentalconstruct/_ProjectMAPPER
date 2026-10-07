"""Desktop controls for per-user adapter limits and approval policy."""

import tkinter as tk
from tkinter import ttk
from .ui_base import attach_tooltip

try:
    from ..core.settings import NUMBERS, load_settings, save_settings
except ImportError:
    # The vendor export imports ``tools`` and ``core`` as top-level packages.
    from core.settings import NUMBERS, load_settings, save_settings


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.colors = app.theme
        self.top = tk.Toplevel(app.root)
        self.top.title("ProjectMapper Settings")
        self.top.geometry("540x380")
        self.top.minsize(480, 340)
        self.top.transient(app.root)
        self.settings = load_settings()

        body = ttk.Frame(self.top, padding=18)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="Agent limits and approvals", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Label(body, text="Tool result limit (KiB)").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Label(body, text="Resource read limit (KiB)").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Label(body, text="Approval timeout (seconds)").grid(row=3, column=0, sticky="w", pady=5)

        self.result_kib = tk.StringVar(self.top, str(self.settings.max_result_bytes // 1024))
        self.resource_kib = tk.StringVar(self.top, str(self.settings.max_resource_bytes // 1024))
        self.timeout_seconds = tk.StringVar(self.top, str(self.settings.approval_timeout_seconds))
        for row, (variable, setting, width) in enumerate((
                (self.result_kib, "max_result_bytes", 16384),
                (self.resource_kib, "max_resource_bytes", 65536),
                (self.timeout_seconds, "approval_timeout_seconds", 3600)), start=1):
            low = NUMBERS[setting][1] // 1024 if setting != "approval_timeout_seconds" else NUMBERS[setting][1]
            spinbox = ttk.Spinbox(body, from_=low, to=width, width=12, textvariable=variable)
            tooltip_id = {"max_result_bytes": "settings.result_limit",
                          "max_resource_bytes": "settings.resource_limit",
                          "approval_timeout_seconds": "settings.approval_timeout"}[setting]
            attach_tooltip(spinbox, tooltip_id, self.colors)
            spinbox.grid(row=row, column=1, sticky="w", padx=(12, 4), pady=5)

        self.ask_before_single = tk.BooleanVar(self.top, self.settings.ask_before_single_file_writes)
        single = ttk.Checkbutton(body, text="Ask before each single-file write", variable=self.ask_before_single)
        attach_tooltip(single, "settings.single_approval", self.colors)
        single.grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 4))
        self.ask_before_structural = tk.BooleanVar(self.top, self.settings.ask_before_structural_writes)
        structural = ttk.Checkbutton(body, text="Ask before non-destructive project transforms",
                                     variable=self.ask_before_structural)
        attach_tooltip(structural, "settings.structural_approval", self.colors)
        structural.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 2))
        ttk.Label(body, text="Destructive operations still need your approval.",
                  wraplength=480).grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 6))
        self.status = tk.StringVar(self.top, "\n".join(self.settings.problems))
        ttk.Label(body, textvariable=self.status, foreground="#A33", wraplength=480).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(2, 6))

        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(12, 0))
        cancel = ttk.Button(buttons, text="Cancel", command=self.top.destroy)
        attach_tooltip(cancel, "settings.cancel", self.colors)
        cancel.pack(side=tk.RIGHT, padx=(8, 0))
        save = ttk.Button(buttons, text="Save", command=self.save)
        attach_tooltip(save, "settings.save", self.colors)
        save.pack(side=tk.RIGHT)
        body.columnconfigure(2, weight=1)
        self.top.bind("<Escape>", lambda _event: self.top.destroy())
        self.top.bind("<Return>", lambda _event: self.save())

    def save(self):
        from tkinter import messagebox

        try:
            values = {
                "max_result_bytes": int(self.result_kib.get()) * 1024,
                "max_resource_bytes": int(self.resource_kib.get()) * 1024,
                "approval_timeout_seconds": int(self.timeout_seconds.get()),
                "ask_before_single_file_writes": bool(self.ask_before_single.get()),
                "ask_before_structural_writes": bool(self.ask_before_structural.get()),
            }
            saved = save_settings(values)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Invalid settings", str(exc), parent=self.top)
            return False
        self.settings = saved
        self.status.set("Settings saved. New adapter processes will use these values.")
        self.app.log_message("Agent limits and approval settings saved.", "INFO")
        return True
