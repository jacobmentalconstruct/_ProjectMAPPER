"""Shared dark-theme Tk helpers for ProjectMapper tool windows."""

import tkinter as tk
from tkinter import scrolledtext, ttk


class ToolWindowMixin:
    def configure_tool_window(self, title, geometry, minimum):
        self.top.configure(bg=self.colors["app_bg"])
        self.top.title(title)
        self.top.geometry(geometry)
        self.top.minsize(*minimum)

    def frame(self, parent):
        return tk.Frame(parent, bg=self.colors["panel_bg"])

    def label(self, parent, panel=False, **kwargs):
        defaults = dict(bg=self.colors["panel_bg" if panel else "app_bg"],
                        fg=self.colors["muted_text"], font=("Arial", 10), anchor="w")
        defaults.update(kwargs)
        return tk.Label(parent, **defaults)

    def button(self, parent, text, command, color=None, state="normal", **kwargs):
        emphasized = color is not None
        color = color or "panel_alt_bg"
        kwargs.setdefault("bold", emphasized)
        button = self.app._make_button(parent, text, command, self.colors[color],
                                       self.colors.get(color + "_hover", self.colors["field_bg_alt"]), **kwargs)
        button.configure(state=state, disabledforeground=self.colors["muted_text"])
        return button

    def checkbutton(self, parent, text, variable, command=None):
        return tk.Checkbutton(parent, text=text, variable=variable, command=command,
                              bg=self.colors["panel_bg"], fg=self.colors["text"],
                              selectcolor=self.colors["tree_bg"], activebackground=self.colors["panel_bg"],
                              activeforeground=self.colors["text"], font=("Arial", 10))

    def editor(self, parent, editable=False, background=None):
        box = scrolledtext.ScrolledText(
            parent, wrap="none", undo=editable, font=("Consolas", 10),
            bg=background or self.colors["log_bg" if editable else "tree_bg"], fg=self.colors["text"],
            insertbackground=self.colors["text"], selectbackground=self.colors["selection"],
            selectforeground=self.colors["text"], relief="flat", borderwidth=0,
            highlightthickness=1, highlightbackground=self.colors["panel_alt_bg"],
            highlightcolor=self.colors["secondary"], padx=10, pady=8,
            state="normal" if editable else "disabled")
        box.frame.configure(bg=self.colors["panel_bg"])
        box.vbar.pack_forget()
        scrollbar = ttk.Scrollbar(box.frame, orient="vertical", command=box.yview)
        scrollbar.pack(side="right", fill="y", before=box._w)
        box.configure(yscrollcommand=scrollbar.set)
        return box
