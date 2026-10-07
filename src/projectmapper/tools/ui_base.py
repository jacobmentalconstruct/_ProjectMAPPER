"""Shared dark-theme Tk helpers for ProjectMapper tool windows."""

import tkinter as tk
from tkinter import scrolledtext, ttk

try:
    from ..core.diff import diff_line_kinds
except ImportError:
    from core.diff import diff_line_kinds

DIFF_KINDS = ("header", "hunk", "add", "remove")  # Theme tokens are "diff_<kind>".


class ToolTip:
    """Delayed, non-activating help bubble for a Tk control."""

    def __init__(self, widget, text, colors, *, delay=500, wraplength=360):
        self.widget = widget
        self.text = text
        self.colors = colors
        self.delay = delay
        self.wraplength = wraplength
        self.pending = None
        self.window = None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<FocusOut>", self.hide, add="+")

    def _timer_owner(self):
        """The root window. A timer registered on a child widget is recorded in that widget's
        command list, so cancelling it through the root (as test teardown and shutdown do)
        would later make the widget's own destroy delete the same Tcl command twice."""
        return self.widget.nametowidget(".")

    def schedule(self, _event=None):
        self.cancel_pending()
        try:
            self.pending = self._timer_owner().after(self.delay, self.show)
        except (tk.TclError, KeyError):
            self.pending = None

    def cancel_pending(self):
        if self.pending is not None:
            try:
                self._timer_owner().after_cancel(self.pending)
            except (tk.TclError, KeyError):
                pass
            self.pending = None

    def show(self):
        self.pending = None
        if self.window is not None or not self.widget.winfo_exists():
            return
        window = self.window = tk.Toplevel(self.widget)
        window.withdraw()
        window.overrideredirect(True)
        window.transient(self.widget.winfo_toplevel())
        bg = self.colors["panel_alt_bg"]
        frame = tk.Frame(window, bg=bg, bd=1, relief=tk.SOLID,
                         highlightthickness=1, highlightbackground=self.colors["secondary"])
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(frame, text=self.text, justify=tk.LEFT, wraplength=self.wraplength,
                 bg=bg, fg=self.colors["text"], padx=9, pady=6).pack()
        window.update_idletasks()
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        x = min(x, max(0, window.winfo_screenwidth() - window.winfo_reqwidth() - 8))
        y = min(y, max(0, window.winfo_screenheight() - window.winfo_reqheight() - 8))
        window.geometry(f"+{x}+{y}")
        window.deiconify()

    def hide(self, _event=None):
        self.cancel_pending()
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None


def attach_tooltip(widget, tooltip_id, colors):
    """Attach registry text and a stable id to a widget for coverage checks."""
    try:
        from .tooltips import TOOLTIPS
    except ImportError:
        from tools.tooltips import TOOLTIPS
    if tooltip_id not in TOOLTIPS:
        raise KeyError(f"No tooltip text registered for {tooltip_id!r}.")
    widget._projectmapper_tooltip_id = tooltip_id
    widget._projectmapper_tooltip = ToolTip(widget, TOOLTIPS[tooltip_id], colors)
    return widget


INTERACTIVE_WIDGET_CLASSES = frozenset({
    "Button", "TButton", "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton",
    "Entry", "TEntry", "Spinbox", "TSpinbox", "Combobox", "TCombobox", "Treeview",
})


def missing_tooltips(root):
    """Return interactive descendants without a stable tooltip id."""
    missing = []

    def walk(widget):
        if widget.winfo_class() in INTERACTIVE_WIDGET_CLASSES and not getattr(
                widget, "_projectmapper_tooltip_id", None):
            missing.append(widget)
        for child in widget.winfo_children():
            walk(child)

    walk(root)
    return missing


class ToolWindowMixin:
    def configure_tool_window(self, title, geometry, minimum):
        self.top.configure(bg=self.colors["app_bg"])
        self.top.title(title)
        self.top.geometry(geometry)
        self.top.minsize(*minimum)

    def fit_minimum_width_to(self, *widgets, margin=80):
        """Keep packed toolbar controls visible across platform font metrics."""
        self.top.update_idletasks()
        minimum_width, minimum_height = self.top.minsize()
        requested = max((widget.winfo_reqwidth() for widget in widgets if widget), default=0)
        self.top.minsize(max(minimum_width, requested + margin), minimum_height)

    def frame(self, parent):
        return tk.Frame(parent, bg=self.colors["panel_bg"])

    def label(self, parent, panel=False, **kwargs):
        defaults = dict(bg=self.colors["panel_bg" if panel else "app_bg"],
                        fg=self.colors["muted_text"], font=("Arial", 10), anchor="w")
        defaults.update(kwargs)
        return tk.Label(parent, **defaults)

    def button(self, parent, text, command, color=None, state="normal", *, tooltip_id, **kwargs):
        emphasized = color is not None
        color = color or "panel_alt_bg"
        kwargs.setdefault("bold", emphasized)
        # _make_button attaches the tooltip itself; attaching again would stack a second one.
        button = self.app._make_button(parent, text, command, self.colors[color],
                                       self.colors.get(color + "_hover", self.colors["field_bg_alt"]),
                                       tooltip_id=tooltip_id, **kwargs)
        button.configure(state=state, disabledforeground=self.colors["muted_text"])
        return button

    def set_button_enabled(self, button, enabled, color):
        """Disabled action buttons lose their colour so they do not look clickable."""
        shade = color if enabled else "panel_alt_bg"
        button.configure(state="normal" if enabled else "disabled", bg=self.colors[shade],
                         activebackground=self.colors.get(shade + "_hover", self.colors["field_bg_alt"]))

    def checkbutton(self, parent, text, variable, command=None, *, tooltip_id):
        widget = tk.Checkbutton(parent, text=text, variable=variable, command=command,
                                bg=self.colors["panel_bg"], fg=self.colors["text"],
                                selectcolor=self.colors["tree_bg"], activebackground=self.colors["panel_bg"],
                                activeforeground=self.colors["text"], font=("Arial", 10))
        attach_tooltip(widget, tooltip_id, self.colors)
        return widget

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
