"""One serialized action seam with approvals and ordered in-process events."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import threading
import traceback
from uuid import uuid4

from .contracts import ActionError, ApprovalPlan, Context, Event, Request, Result, TERMINAL


class Dispatcher:
    def __init__(self, *, history_limit=1000, operation_limit=4096):
        self._handlers = {}
        self._operations = {}
        self._requests = {}
        self._listeners = {}
        self._events = deque(maxlen=history_limit)
        self._delivery = deque()
        self._delivering = False
        self._sequence = 0
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="projectmapper-actions")
        self._closed = False
        self._operation_limit = operation_limit
        self.observer_errors = deque(maxlen=32)
        self._local = threading.local()

    def register(self, name, handler):
        if name in self._handlers:
            raise ValueError(f"Action already registered: {name}")
        self._handlers[name] = handler

    def actions(self):
        return tuple(sorted(self._handlers))

    def subscribe(self, listener):
        key = str(uuid4())
        with self._lock:
            self._listeners[key] = listener
        def unsubscribe():
            with self._lock:
                self._listeners.pop(key, None)
        return unsubscribe

    def events(self, after=0):
        with self._lock:
            return {"events": copy.deepcopy([e for e in self._events if e.sequence > after]),
                    "resync_required": bool(self._events and after < self._events[0].sequence - 1),
                    "sequence": self._sequence}

    def _emit(self, operation, kind, payload=None):
        with self._lock:
            self._sequence += 1
            request = operation["request"]
            event = Event(self._sequence, operation["id"], request.action, request.origin, kind, copy.deepcopy(payload or {}))
            self._events.append(event)
            self._delivery.append((event, tuple(self._listeners.values())))
            if self._delivering:
                return
            self._delivering = True
        # Nested event production queues behind the current event. No listener
        # executes while the state lock is held; every observer sees one order.
        while True:
            with self._lock:
                if not self._delivery:
                    self._delivering = False
                    return
                event, listeners = self._delivery.popleft()
            for listener in listeners:
                try:
                    self._local.in_listener = True
                    listener(copy.deepcopy(event))
                except Exception:
                    self.observer_errors.append(traceback.format_exc())
                finally:
                    self._local.in_listener = False

    def submit(self, request):
        if not isinstance(request, Request):
            raise ActionError("invalid_input", "Expected an action Request.")
        try:
            signature = json.dumps([request.action, request.payload, request.version], sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ActionError("invalid_input", "Request payload must contain JSON values.") from exc
        if request.version != 1 or not isinstance(request.payload, dict) or not request.request_id:
            raise ActionError("invalid_input", "Invalid request version, payload or ID.")
        if len(signature) > 8_000_000:
            raise ActionError("capacity", "Action request exceeds the 8 MB session limit.")
        with self._lock:
            if request.request_id in self._requests:
                existing, previous = self._requests[request.request_id]
                if signature != previous:
                    raise ActionError("invalid_input", "Request ID was already used for different inputs.")
                return existing
            if self._closed:
                raise ActionError("closed", "Application actions have been closed.")
            if request.action not in self._handlers:
                raise ActionError("invalid_input", f"Unknown action: {request.action}")
            if len(self._operations) >= self._operation_limit:
                raise ActionError("capacity", "Session operation limit reached; start a new session.")
            operation_id = str(uuid4())
            operation = {"id": operation_id, "request": copy.deepcopy(request),
                         "result": Result(operation_id, request.action, "queued"),
                         "cancel": threading.Event(), "plan": None, "settled": False}
            self._operations[operation_id] = operation
            self._requests[request.request_id] = operation_id, signature
        self._emit(operation, "accepted")
        with self._lock:
            closed = self._closed
            if not closed:
                self._worker.submit(self._run, operation)
        if closed:
            self._finish(operation, "cancelled", error={"code": "closed", "message": "Application closed."})
        return operation_id

    def _finish(self, operation, status, data=None, error=None):
        with self._changed:
            if status == "awaiting_approval" and operation["cancel"].is_set():
                operation["plan"] = None
                status, data = "cancelled", {}
                error = {"code": "cancelled", "message": "Operation cancelled before approval."}
            operation["result"] = Result(operation["id"], operation["request"].action, status, data or {}, error)
        # Content lives in the queryable result, never in the history stream.
        summary = {key: value for key, value in (data or {}).items()
                   if key in {"paths", "path", "count", "generation", "revision", "summary"}}
        if error:
            summary["error"] = copy.deepcopy(error)
        self._emit(operation, status, summary)
        with self._changed:
            operation["settled"] = True
            self._changed.notify_all()

    def _run(self, operation, continuation=None):
        context = Context(operation["id"], operation["cancel"], lambda kind, payload: self._emit(operation, kind, payload))
        try:
            context.check_cancelled()
            with self._lock:
                operation["result"] = Result(operation["id"], operation["request"].action, "running")
            self._emit(operation, "started")
            data = continuation(context) if continuation else self._handlers[operation["request"].action](copy.deepcopy(operation["request"].payload), context)
            if isinstance(data, ApprovalPlan):
                context.check_cancelled()
                with self._lock:
                    operation["plan"] = data
                self._finish(operation, "awaiting_approval", {"summary": data.summary})
            else:
                self._finish(operation, "succeeded", data)
        except ActionError as exc:
            status = "cancelled" if exc.code == "cancelled" else "recovery_required" if exc.code == "recovery_required" else "failed"
            self._finish(operation, status, error={"code": exc.code, "message": str(exc), "details": exc.details})
        except Exception as exc:
            self._finish(operation, "failed", error={"code": "io_error" if isinstance(exc, OSError) else "action_failed", "message": str(exc)})

    def get(self, operation_id):
        with self._lock:
            if operation_id not in self._operations:
                raise ActionError("not_found", "Operation was not found.")
            return copy.deepcopy(self._operations[operation_id]["result"])

    def wait(self, operation_id, timeout=30):
        if getattr(self._local, "in_listener", False):
            raise ActionError("reentrant", "Event listeners must not wait on actions; queue work instead.")
        with self._changed:
            self._changed.wait_for(lambda: self._operations[operation_id]["settled"] and self.get(operation_id).status in TERMINAL | {"awaiting_approval"}, timeout)
            return self.get(operation_id)

    def execute(self, request, timeout=30):
        if getattr(self._local, "in_listener", False):
            raise ActionError("reentrant", "Event listeners must not execute blocking actions.")
        return self.wait(self.submit(request), timeout)

    def cancel(self, operation_id):
        with self._lock:
            operation = self._operations[operation_id]
            if operation["result"].status in TERMINAL:
                return self.get(operation_id)
            operation["cancel"].set()
            pending = operation["result"].status == "awaiting_approval"
            if pending:
                operation["plan"] = None
        if pending:
            self._finish(operation, "cancelled", error={"code": "approval_denied", "message": "Pending approval cancelled."})
        return self.get(operation_id)

    def _resolve_approval(self, operation_id, approved):
        """Private trusted-adapter capability; never register as a public action."""
        with self._lock:
            if self._closed:
                raise ActionError("closed", "Application actions have been closed.")
            operation = self._operations[operation_id]
            plan = operation["plan"]
            if operation["result"].status != "awaiting_approval" or plan is None:
                raise ActionError("stale_plan", "Approval is no longer pending.")
            operation["plan"] = None
            operation["settled"] = False
            if approved is not True:
                operation["cancel"].set()
            operation["result"] = Result(operation_id, operation["request"].action, "queued")
            self._worker.submit(self._run, operation, plan.execute)
        return operation_id

    def close(self):
        with self._lock:
            self._closed = True
            ids = list(self._operations)
        for operation_id in ids:
            self.cancel(operation_id)
        self._worker.shutdown(wait=not getattr(self._local, "in_listener", False), cancel_futures=False)
