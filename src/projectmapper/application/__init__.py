"""Headless application API. Desktop and future transports are clients."""

from .contracts import ActionError, Request, Result, Event, ApprovalPlan
from .dispatcher import Dispatcher

__all__ = ["ActionError", "Request", "Result", "Event", "ApprovalPlan", "Dispatcher"]
