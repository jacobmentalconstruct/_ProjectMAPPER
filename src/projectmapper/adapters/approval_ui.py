"""Minimal trusted preview window. Imported only by the approval broker on demand."""


def _flash_taskbar(window):
    """Flash this process window on Windows without relying on foreground focus."""
    import ctypes
    import os

    if os.name != "nt":
        return

    class FlashInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p),
                    ("dwFlags", ctypes.c_uint), ("uCount", ctypes.c_uint),
                    ("dwTimeout", ctypes.c_uint)]

    info = FlashInfo(ctypes.sizeof(FlashInfo), window.winfo_id(), 3, 4, 0)
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))


def show_approval(request, timeout_seconds):
    """Show the exact action summary and diff; approve only on an explicit button press."""
    import tkinter as tk
    from tkinter import ttk
    try:
        from ..app import THEME
        from ..tools.ui_base import attach_tooltip
    except ImportError:
        from app import THEME
        from tools.ui_base import attach_tooltip

    root = tk.Tk()
    root.withdraw()
    window = tk.Toplevel(root)
    window.title(request.title or "ProjectMapper approval")
    window.geometry("960x700")
    window.minsize(640, 420)
    window.attributes("-topmost", True)

    frame = ttk.Frame(window, padding=14)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text=f"Approve {request.action}?", font=("Segoe UI", 15, "bold")).pack(anchor="w")
    ttk.Label(frame, text=request.message, wraplength=900, justify=tk.LEFT).pack(anchor="w", pady=(8, 6))
    ttk.Label(frame, text="Affected paths", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
    paths = "\n".join(request.paths) or "(No project paths supplied)"
    path_label = ttk.Label(frame, text=paths, wraplength=900, justify=tk.LEFT)
    path_label.pack(anchor="w", fill=tk.X, pady=(0, 8))
    ttk.Label(frame, text="Exact proposed diff", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(2, 2))

    diff_frame = ttk.Frame(frame)
    diff_frame.pack(fill=tk.BOTH, expand=True)
    diff = tk.Text(diff_frame, wrap=tk.NONE, height=20, font=("Consolas", 9),
                   undo=False, borderwidth=1, relief=tk.SOLID)
    vertical = ttk.Scrollbar(diff_frame, orient=tk.VERTICAL, command=diff.yview)
    horizontal = ttk.Scrollbar(diff_frame, orient=tk.HORIZONTAL, command=diff.xview)
    diff.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    diff.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    diff_frame.rowconfigure(0, weight=1)
    diff_frame.columnconfigure(0, weight=1)
    diff.insert("1.0", request.diff or "(No differences)")
    diff.configure(state=tk.DISABLED)

    decision = {"approved": False}
    remaining = {"seconds": int(timeout_seconds)}
    countdown = ttk.Label(frame, text=f"Denied automatically in {remaining['seconds']} seconds.")
    countdown.pack(anchor="w", pady=(8, 2))

    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X, pady=(6, 0))

    def finish(approved):
        if not window.winfo_exists():
            return
        decision["approved"] = approved is True
        window.destroy()

    def tick():
        if not window.winfo_exists():
            return
        remaining["seconds"] -= 1
        if remaining["seconds"] <= 0:
            finish(False)
            return
        countdown.configure(text=f"Denied automatically in {remaining['seconds']} seconds.")
        window.after(1000, tick)

    deny = ttk.Button(buttons, text="Deny", command=lambda: finish(False), takefocus=True)
    attach_tooltip(deny, "approval.deny", THEME)
    deny.pack(side=tk.RIGHT, padx=(8, 0))
    approve = ttk.Button(buttons, text="Approve", command=lambda: finish(True))
    attach_tooltip(approve, "approval.approve", THEME)
    approve.pack(side=tk.RIGHT)
    deny.focus_set()
    window.protocol("WM_DELETE_WINDOW", lambda: finish(False))
    window.bind("<Escape>", lambda _event: finish(False))
    window.after(1000, tick)
    window.update_idletasks()
    window.deiconify()
    window.lift()
    try:
        window.grab_set()
        window.focus_force()
    except tk.TclError:
        pass
    try:
        _flash_taskbar(window)
    except (AttributeError, OSError):
        # The preview remains usable when Windows focus flashing is unavailable.
        pass

    try:
        root.wait_window(window)
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
    return decision["approved"]
