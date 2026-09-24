"""One catalogue of human wording for action error codes.

Codes are the contract (stable, machine-readable); labels are presentation. Every code
raised anywhere in the source must have a label here (enforced by a test).
"""

LABELS = {
    "invalid_input": "Invalid request",
    "not_found": "Not found",
    "unsafe_path": "That location is not allowed",
    "source_changed": "The file changed on disk",
    "stale_plan": "The preview is out of date",
    "stale_scan": "The project changed during the scan",
    "stale_snapshot": "The snapshot is out of date",
    "backup_invalid": "The backup cannot be used",
    "prune_incomplete": "Clean-up was incomplete",
    "recovery_required": "Recovery required",
    "io_error": "File system error",
    "cancelled": "Cancelled",
    "approval_denied": "Not approved",
    "closed": "The application is closing",
    "capacity": "Session limit reached",
    "reentrant": "Operation ordering error",
    "action_failed": "Operation failed",
    "internal_error": "Internal problem",
}
FALLBACK = "Operation failed"


def label(code):
    return LABELS.get(code, FALLBACK)


def describe(error):
    """``{"code", "message"}`` → "Label: message" (or just the label without a message)."""
    error = error or {}
    text = label(error.get("code"))
    message = str(error.get("message") or "").strip()
    return f"{text}: {message}" if message else text
