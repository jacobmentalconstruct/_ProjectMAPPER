"""Thin desktop adapter; all file rules stay in headless action handlers."""
from pathlib import Path
from .contracts import Request, ActionError
from .errors import describe
try:
    from ..tools.patcher import PatchError
except ImportError:
    from tools.patcher import PatchError


class Session:
    def __init__(self, app, path):
        self.app = app
        self.load(path)

    def load(self, path):
        data = self.app.action("text.open", {"path": str(path)})
        self.path = Path(data["path"])
        self.source = data["text"]
        self.sha256 = data["sha256"]
        self.bom = data["bom"]
        self.original_bytes = (b"\xef\xbb\xbf" if self.bom else b"") + self.source.encode("utf-8")

    def save(self, text, suffix=None, backup=False):
        data = self.app.action("text.save", {"path": str(self.path), "text": text,
            "sha256": self.sha256, "suffix": suffix, "backup": backup})
        self.load(data["path"])
        return self.path


def perform(app, name, payload=None, parent=None, approval_guard=None):
    """Only composition-root UI code receives the trusted approval capability."""
    from tkinter import messagebox
    try:
        operation = app.controller.dispatcher.submit(Request(name, payload or {}))
        if not hasattr(app, "desktop_operations"):
            app.desktop_operations = set()
        app.desktop_operations.add(operation)
        app.action_operations.add(operation)
        try:
            result = app.controller.dispatcher.wait(operation, None)
            if result.status == "awaiting_approval":
                summary = result.data["summary"]
                approved = messagebox.askyesno(summary["title"], summary["message"],
                                              parent=parent or app.root, default="no")
                if approved and approval_guard and not approval_guard():
                    app.controller.dispatcher.cancel(operation)
                    raise PatchError("Inputs changed while awaiting approval. Review again.")
                app.approve_action(operation, approved)
                result = app.controller.dispatcher.wait(operation, None)
            if result.status != "succeeded":
                raise PatchError(describe(result.error or {"code": result.status}))
            return result.data
        finally:
            app.action_operations.discard(operation)
    except ActionError as exc:
        raise PatchError(describe({"code": exc.code, "message": str(exc)})) from exc
