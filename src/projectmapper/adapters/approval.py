"""Trusted human approval bridge; Tk is loaded only for an actual request."""

from queue import Empty, Queue
import threading
import time


class ApprovalBroker:
    """Callable approver serviced by a UI-owning thread, usually the process main thread."""

    def __init__(self, *, timeout_seconds=120, display=None):
        self.timeout_seconds = timeout_seconds
        self.display = display
        self._requests = Queue()

    def __call__(self, request):
        response = {"request": request, "event": threading.Event(), "decision": False,
                    "cancelled": False, "deadline": time.monotonic() + self.timeout_seconds}
        self._requests.put(response)
        if not response["event"].wait(self.timeout_seconds + 5):
            response["cancelled"] = True
            return False
        return response["decision"] is True

    def serve(self, stop_event):
        """Display queued requests on this thread until the server/command ends."""
        while not stop_event.is_set():
            try:
                response = self._requests.get(timeout=0.1)
            except Empty:
                continue
            if response["cancelled"]:
                continue
            try:
                if self.display is None:
                    from .approval_ui import show_approval
                    decision = show_approval(response["request"], self.timeout_seconds)
                else:
                    decision = self.display(response["request"], self.timeout_seconds)
            except Exception:
                decision = False
            response["decision"] = decision is True and time.monotonic() <= response["deadline"]
            response["event"].set()

        while True:
            try:
                response = self._requests.get_nowait()
            except Empty:
                break
            response["decision"] = False
            response["event"].set()
