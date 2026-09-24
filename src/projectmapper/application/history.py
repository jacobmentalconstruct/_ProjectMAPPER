"""Bounded, content-free operation history built from dispatcher events.

One record per operation, whatever its origin or outcome. Progress is coalesced into a
counter and the last message, so a busy operation can never push others out. Only
whitelisted fields are kept: actions, times, statuses, paths, counts, error codes and
messages, approval titles, and backup generation names. File contents never are.
"""

from collections import OrderedDict
from datetime import datetime
import copy
import re
import threading

TERMINAL = ("succeeded", "failed", "cancelled", "recovery_required")
OUTCOMES = frozenset(TERMINAL + ("running", "awaiting_approval", "queued"))
MAX_PATHS = 50
MAX_TEXT = 2000
MAX_TRACE = 8000
_GENERATION = re.compile(r"\b\d{8}T\d{12}Z-[0-9a-z]{1,16}\b")
# The history never records reading itself; a refreshing window would otherwise flood it.
UNRECORDED = frozenset({"history.query"})


def category_of(action):
    return action.split(".", 1)[0]


def _clip(text):
    text = str(text)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"


def _duration_ms(start, end):
    try:
        return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() * 1000)
    except (TypeError, ValueError):
        return None


class OperationHistory:
    def __init__(self, limit=500):
        self.limit = limit
        self._records = OrderedDict()
        self._lock = threading.Lock()
        self._listeners = []
        self._problem_count = 0

    # --- recording -----------------------------------------------------

    def observe(self, event):
        """Dispatcher listener. Safe to call from the dispatcher worker thread."""
        if event.action in UNRECORDED:
            return
        with self._lock:
            record = self._records.get(event.operation_id)
            if record is None:
                record = self._records[event.operation_id] = {
                    "id": event.operation_id, "action": event.action, "category": category_of(event.action),
                    "origin": event.origin, "status": "queued", "accepted_at": event.time, "started_at": None,
                    "finished_at": None, "duration_ms": None, "approval": None, "approval_title": None,
                    "approval_message": None, "progress_count": 0, "last_progress": None, "paths": [],
                    "count": None, "error": None, "generations": [], "detail": None}
            self._apply(record, event)
            self._evict()
            snapshot = copy.deepcopy(record)
        for listener in tuple(self._listeners):
            self._notify(listener, snapshot)

    def _apply(self, record, event):
        payload = event.payload or {}
        kind = event.type
        if kind == "accepted":
            record["accepted_at"] = event.time
        elif kind == "started":
            record["status"] = "running"
            record["started_at"] = record["started_at"] or event.time
            if record["approval"] == "requested":
                # Only an approved continuation starts again; a denial fails before starting.
                record["approval"] = "approved"
        elif kind == "progress":
            record["progress_count"] += 1
            if "message" in payload:
                record["last_progress"] = _clip(payload["message"])
        elif kind == "awaiting_approval":
            record["status"] = "awaiting_approval"
            record["approval"] = "requested"
            summary = payload.get("summary") or {}
            record["approval_title"] = _clip(summary.get("title", ""))
            record["approval_message"] = _clip(summary.get("message", ""))
            self._add_paths(record, summary.get("paths"))
            self._add_generations(record, record["approval_message"])
        elif kind in TERMINAL:
            record["status"] = kind
            record["finished_at"] = event.time
            record["duration_ms"] = _duration_ms(record["started_at"] or record["accepted_at"], event.time)
            if record["approval"] == "requested":
                record["approval"] = "denied"  # finished without the approved continuation starting
            self._add_paths(record, payload.get("paths"))
            self._add_paths(record, [payload["path"]] if payload.get("path") else None)
            if isinstance(payload.get("count"), int):
                record["count"] = payload["count"]
            error = payload.get("error")
            if error:
                record["error"] = {"code": str(error.get("code", "")), "message": _clip(error.get("message", ""))}
                self._add_generations(record, record["error"]["message"])

    def record_problem(self, source, message, trace=""):
        """Record an application-internal failure (listener, UI callback, worker) as a failed record.

        The traceback is kept in ``detail`` for the History window; logs stay concise.
        """
        now = datetime.now().astimezone().isoformat()
        with self._lock:
            self._problem_count += 1
            record = {
                "id": f"internal-{self._problem_count}", "action": f"internal.{source}", "category": "internal",
                "origin": "application", "status": "failed", "accepted_at": now, "started_at": now,
                "finished_at": now, "duration_ms": 0, "approval": None, "approval_title": None,
                "approval_message": None, "progress_count": 0, "last_progress": None, "paths": [], "count": None,
                "error": {"code": "internal_error", "message": _clip(message)}, "generations": [],
                "detail": str(trace)[-MAX_TRACE:]}
            self._records[record["id"]] = record
            self._evict()
            snapshot = copy.deepcopy(record)
        for listener in tuple(self._listeners):
            self._notify(listener, snapshot)
        return snapshot

    @staticmethod
    def _notify(listener, record):
        # A failing presentation listener must not re-enter the dispatcher's error path,
        # which would record a problem and notify the same listener again.
        try:
            listener(record)
        except Exception:
            pass

    @staticmethod
    def _add_paths(record, paths):
        for path in paths or ():
            if isinstance(path, str) and path not in record["paths"] and len(record["paths"]) < MAX_PATHS:
                record["paths"].append(path)

    @staticmethod
    def _add_generations(record, text):
        for name in _GENERATION.findall(text or ""):
            if name not in record["generations"]:
                record["generations"].append(name)

    def _evict(self):
        while len(self._records) > self.limit:
            victim = next((key for key, rec in self._records.items() if rec["status"] in TERMINAL), None)
            if victim is None:
                return  # only unfinished operations remain; never drop them
            del self._records[victim]

    # --- reading -------------------------------------------------------

    def subscribe(self, listener):
        """Receive a copy of each record whenever it changes (presentation refresh)."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def query(self, category=None, outcome=None, text=None, limit=200):
        if outcome is not None and outcome not in OUTCOMES:
            raise ValueError(f"Unknown outcome: {outcome}")
        needle = (text or "").casefold()
        with self._lock:
            records = [copy.deepcopy(r) for r in reversed(self._records.values())]
        found = []
        for record in records:
            if category and record["category"] != category:
                continue
            if outcome and record["status"] != outcome:
                continue
            if needle and needle not in " ".join(
                    [record["action"], record["origin"], *record["paths"], *record["generations"],
                     (record["error"] or {}).get("message", ""), record["approval_title"] or ""]).casefold():
                continue
            found.append(record)
            if len(found) >= limit:
                break
        return found
