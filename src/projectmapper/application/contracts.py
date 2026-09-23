"""Serializable public contracts and private execution context."""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4


TERMINAL = frozenset({"succeeded", "failed", "cancelled", "recovery_required"})


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class ActionError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


@dataclass(frozen=True)
class Request:
    action: str
    payload: dict = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid4()))
    origin: str = "desktop"
    version: int = 1


@dataclass(frozen=True)
class Result:
    operation_id: str
    action: str
    status: str
    data: dict = field(default_factory=dict)
    error: dict | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Event:
    sequence: int
    operation_id: str
    action: str
    origin: str
    type: str
    payload: dict = field(default_factory=dict)
    time: str = field(default_factory=timestamp)
    version: int = 1

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ApprovalPlan:
    """Private handler result. Continuations never cross the public API boundary."""
    summary: dict
    execute: Callable


class Context:
    def __init__(self, operation_id, cancel_event, publish):
        self.operation_id = operation_id
        self.cancel_event = cancel_event
        self._publish = publish

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise ActionError("cancelled", "Operation cancelled.")

    def progress(self, **details):
        self.check_cancelled()
        self._publish("progress", details)
