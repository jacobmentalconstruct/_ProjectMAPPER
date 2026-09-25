"""Shared dark-theme Tk helpers for ProjectMapper tool windows."""

import tkinter as tk
from tkinter import scrolledtext, ttk

try:
    from ..core.diff import diff_line_kinds
except ImportError:
    from core.diff import diff_line_kinds

DIFF_KINDS = ("header", "hunk", "add", "remove")  # Theme tokens are "diff_<kind>".


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

    def set_button_enabled(self, button, enabled, color):
        """Disabled action buttons lose their colour so they do not look clickable."""
        shade = color if enabled else "panel_alt_bg"
        button.configure(state="normal" if enabled else "disabled", bg=self.colors[shade],
                         activebackground=self.colors.get(shade + "_hover", self.colors["field_bg_alt"]))

    def checkbutton(self, parent, text, variable, command=None):
        return tk.Checkbutton(parent, text=text, variable=variable, command=command,
                              bg=self.colors["panel_bg"], fg=self.colors["text"],
                              selectcolor=self.colors["tree_bg"], activebackground=self.colors["panel_bg"],
                              activeforeground=self.colors["text"], font=("Arial", 10))

    def setup_review_styles(self):
        """Scoped styles for review panes and tabs; other windows' ttk defaults are untouched."""
        colors = self.colors
        style = ttk.Style(self.top)
        style.configure("Review.TPanedwindow", background=colors["app_bg"])
        style.configure("Review.TNotebook", background=colors["panel_bg"], borderwidth=0)
        style.configure("Review.TNotebook.Tab", background=colors["panel_alt_bg"],
                        foreground=colors["muted_text"], padding=(12, 7), font=("Arial", 10))
        style.map("Review.TNotebook.Tab",
                  background=[("selected", colors["secondary"]), ("active", colors["heading_bg"])],
                  foreground=[("selected", colors["text"]), ("active", colors["text"])])
        # clam draws the arrow box and frame with its own light/border colours unless set here.
        style.configure("Review.TCombobox", fieldbackground=colors["field_bg"], background=colors["panel_alt_bg"],
                        foreground=colors["text"], arrowcolor=colors["text"], bordercolor=colors["panel_alt_bg"],
                        lightcolor=colors["panel_alt_bg"], darkcolor=colors["panel_alt_bg"])
        style.map("Review.TCombobox", fieldbackground=[("readonly", colors["field_bg"])],
                  foreground=[("readonly", colors["text"])], selectbackground=[("readonly", colors["selection"])])
        style.configure("Review.TSpinbox", fieldbackground=colors["field_bg"], background=colors["panel_alt_bg"],
                        foreground=colors["field_text"], arrowcolor=colors["text"], insertcolor=colors["text"],
                        bordercolor=colors["panel_alt_bg"], lightcolor=colors["panel_alt_bg"],
                        darkcolor=colors["panel_alt_bg"], selectbackground=colors["selection"],
                        selectforeground=colors["text"], arrowsize=12)
        style.map("Review.TSpinbox", background=[("active", colors["field_bg_alt"])])

    def add_view(self, notebook, name):
        """Add a read-only text tab to a review notebook and return its text box."""
        frame = self.frame(notebook)
        box = self.editor(frame)
        box.pack(fill="both", expand=True)
        notebook.add(frame, text=name)
        return box

    @staticmethod
    def show_text(box, text):
        box.config(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.config(state="disabled")

    def show_diff(self, box, text):
        """Show unified-diff text with file headers, hunk headers, additions and removals tagged."""
        self.show_text(box, text)
        for kind in DIFF_KINDS:
            box.tag_configure(f"diff_{kind}", foreground=self.colors[f"diff_{kind}"])
        for number, kind in enumerate(diff_line_kinds(text), 1):
            if kind:
                box.tag_add(f"diff_{kind}", f"{number}.0", f"{number}.end")

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
        # Dark scrollbar under the application's "clam" theme; a named style leaves others unchanged.
        style = ttk.Style(box)
        style.configure("Review.Vertical.TScrollbar", background=self.colors["panel_alt_bg"],
                        troughcolor=self.colors["log_bg"], arrowcolor=self.colors["muted_text"],
                        bordercolor=self.colors["panel_bg"], lightcolor=self.colors["panel_alt_bg"],
                        darkcolor=self.colors["panel_alt_bg"])
        style.map("Review.Vertical.TScrollbar", background=[("active", self.colors["secondary"])])
        scrollbar = ttk.Scrollbar(box.frame, orient="vertical", command=box.yview,
                                  style="Review.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y", before=box._w)
        box.configure(yscrollcommand=scrollbar.set)
        return box
