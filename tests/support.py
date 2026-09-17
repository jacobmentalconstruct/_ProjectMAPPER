"""Isolated fixtures with cleanup registered before test setup continues."""

import gc
import tempfile
import tkinter as tk


def temporary_directory(case):
    fixture = tempfile.TemporaryDirectory(prefix="projectmapper-test-")
    case.addCleanup(fixture.cleanup)
    return fixture


def tk_root(case):
    gc.collect()
    root = tk.Tk()

    def close():
        for timer in root.tk.call("after", "info"):
            root.after_cancel(timer)
        root.destroy()
        for name in ("window", "popup", "app", "root"):
            if hasattr(case, name):
                setattr(case, name, None)
        gc.collect()

    case.addCleanup(close)
    return root
