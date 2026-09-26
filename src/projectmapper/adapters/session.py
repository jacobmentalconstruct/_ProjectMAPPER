"""One agent-facing session over the public actions of a single project root.

Shared by the CLI and the MCP server. The desktop trusts its user; an agent is not
trusted, so this session adds (plan section 12B, decisions F2–F5):
- an explicit allow-list: every registered action is classified, so a new action is
  never exposed by accident
- confinement of every path field to the project root; the root never changes
- backups forced on for every write
- a trusted human approver, never the agent, for project applies and (unless the
  owner's settings waive it) single-file writes, shown the exact diff that will be written
- results bounded to the owner's limit, with every cut stated
"""

import copy
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from ..application.contracts import ActionError, Request
from ..application.controller import create_application
from ..core.config import OUTPUT_ROOT_NAME
from ..core.diff import DiffFile, unified_diff_text
from ..core.files import file_name
from ..core.paths import PathSafetyError, validate_target
from ..core.settings import NUMBERS, load_settings
from .bounds import bound, encoded_size

# Exposed actions and the payload fields that name a path (confined to the root).
READS = {
    "state.get": (), "project.scan": (), "selection.set": ("path",),
    "exclusions.update": (), "exclusions.inspect": (), "capture.configure": (),
    "snapshot.compile": (), "snapshot.require": (), "snapshot.export": (),
    "output.location": (), "application.diagnostics": (),
    "text.open": ("path",), "text.find": (), "text.replace": (), "file.name": (),
    "patch.schema": (), "patch.load": ("path",), "patch.validate": ("path",), "patch.result": (),
    "project_patch.add_entry": ("root", "path"), "project_patch.validate": ("root",),
    "backup.list": (), "history.query": (),
}
WRITES = {"text.save": ("path",), "patch.save": (), "file.create": ("folder",), "project_patch.apply": ()}
EXPOSED = {**READS, **WRITES}
NOT_EXPOSED = {
    "project.set_root": "The project root is fixed when the adapter starts.",
    "project.dirty": "Desktop bookkeeping; writes mark the project themselves.",
    "text.save_as": "It overwrites without a fingerprint; use text.save or file.create.",
    "file.delete": "Deleting files is left to the desktop.",
    "vendor.export": "It writes outside the project.",
    "backup.preview": "Restoring backups is left to the desktop.",
    "backup.restore": "Restoring backups is left to the desktop.",
    "backup.prune_preview": "Removing backups is left to the desktop.",
    "backup.prune": "Removing backups is left to the desktop.",
}
SINGLE_FILE_WRITES = ("text.save", "patch.save", "file.create")
BACKED_UP = ("text.save", "patch.save", "project_patch.apply")
NOTE_RESERVE = 2048  # room kept for the truncation record itself
PLAN_MEMORY = 64     # the controller keeps at most this many plans too


@dataclass(frozen=True)
class ApprovalRequest:
    """What a trusted human approver is shown. ``diff`` is exactly what will be written."""
    action: str
    origin: str
    title: str
    message: str
    paths: tuple
    diff: str


def _outcome(action, status, data=None, error=None):
    return {"action": action, "status": status, "data": data or {}, "error": error}


def _approval_required(action):
    return _outcome(action, "approval_required", error={
        "code": "approval_required",
        "message": "This change needs a person's approval and no approval window is available. "
                   "Nothing was written."})


def _endings(text):
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "mixed" if crlf and lf else "CRLF" if crlf else "LF" if lf else None


def _unseen_changes(before, after):
    """Changes a line diff does not show: line-ending style and the final newline."""
    notes = []
    old, new = _endings(before), _endings(after)
    if old and new and old != new:
        notes.append(f"Line endings change from {old} to {new}.")
    if before and after and before.endswith(("\n", "\r")) != after.endswith(("\n", "\r")):
        notes.append("The final newline is " + ("removed." if before.endswith(("\n", "\r")) else "added."))
    return "".join("\n\n" + note for note in notes)


def _denied(action):
    return _outcome(action, "cancelled", error={"code": "approval_denied",
                                                "message": "Not approved. Nothing was written."})


class AdapterSession:
    def __init__(self, root, origin, *, approver=None, settings=None):
        if not Path(root).is_dir():
            raise ValueError(f"Project root is not a folder: {root}")
        self.controller, self._resolve_approval = create_application(root)
        self.root = self.controller.state.root
        self.origin = origin
        self.approver = approver  # callable(ApprovalRequest) -> bool; only a trusted human adapter
        self.settings = settings or load_settings()
        self._project_diffs = {}  # project plan_id -> the diff its validation returned
        self._patch_targets = {}  # single-file plan_id -> target path
        self._partial = set()     # (path, sha256) whose text was served truncated

    def actions(self):
        return tuple(sorted(EXPOSED))

    def close(self):
        self.controller.close()

    # --- the one entry point ------------------------------------------------

    def call(self, action, payload=None, *, max_bytes=None):
        """Run one exposed action; always returns a bounded outcome dict, never raises."""
        try:
            limit = self._limit(max_bytes)
        except ActionError as exc:
            return _outcome(action, "failed", error={"code": exc.code, "message": str(exc)})
        try:
            if action not in EXPOSED:
                reason = NOT_EXPOSED.get(action, "Unknown action.")
                raise ActionError("invalid_input", f"{action} is not available to agents. {reason}")
            if payload is None:
                payload = {}
            if not isinstance(payload, dict):
                raise ActionError("invalid_input", "The payload must be a JSON object.")
            payload = self._prepare(action, copy.deepcopy(payload))
            if action in SINGLE_FILE_WRITES and self.settings.ask_before_single_file_writes:
                outcome = self._approved_single_write(action, payload)
            else:
                outcome = self._run(action, payload)
        except ActionError as exc:
            outcome = _outcome(action, "failed", error={"code": exc.code, "message": str(exc)})
        except Exception as exc:  # an adapter fault must reach the agent as a result, not a crash
            outcome = _outcome(action, "failed", error={"code": "action_failed", "message": f"{type(exc).__name__}: {exc}"})
        return self._bounded(action, outcome, limit)

    # --- inputs ---------------------------------------------------------------

    def _limit(self, requested):
        ceiling = self.settings.max_result_bytes
        if requested is None:
            return ceiling
        low = NUMBERS["max_result_bytes"][1]
        if not isinstance(requested, int) or isinstance(requested, bool) or requested < low:
            raise ActionError("invalid_input", f"max_bytes must be a whole number of at least {low}.")
        return min(requested, ceiling)  # an agent may ask for less, never more

    def _confine(self, value, write):
        if not isinstance(value, str) or not value.strip():
            raise ActionError("invalid_input", "Paths must be non-empty text.")
        path = Path(value)
        path = Path(os.path.normpath(path if path.is_absolute() else self.root / path))
        if path != self.root and not path.is_relative_to(self.root):
            raise ActionError("unsafe_path", f"{value} is outside the project root.")
        try:
            validate_target(path)
        except PathSafetyError as exc:
            raise ActionError("unsafe_path", str(exc)) from exc
        if write and any(part.casefold() == OUTPUT_ROOT_NAME.casefold()
                         for part in path.relative_to(self.root).parts):
            raise ActionError("unsafe_path", f"{OUTPUT_ROOT_NAME} is ProjectMapper's own folder; agents cannot write there.")
        return str(path)

    def _prepare(self, action, payload):
        if action in ("project_patch.validate", "project_patch.add_entry"):
            payload.setdefault("root", str(self.root))
        for key in EXPOSED[action]:
            if key in payload:
                payload[key] = self._confine(payload[key], action in WRITES)
        if action == "backup.list":
            if payload.get("scope", "project") != "project":
                raise ActionError("invalid_input", "Agents can list only the project's backups.")
            payload["scope"] = "project"
        if action in BACKED_UP:
            if "backup" in payload:
                raise ActionError("invalid_input", "Backups are always kept for agent writes; leave out 'backup'.")
            payload["backup"] = True
        if action == "text.save" and (self._key(payload.get("path")), payload.get("sha256")) in self._partial:
            raise ActionError("invalid_input", "This file was read truncated, so saving whole text would cut it. "
                                               "Change it with patch.validate and patch.save.")
        return payload

    @staticmethod
    def _key(path):
        return os.path.normcase(str(path)) if path else None

    # --- running and approval -----------------------------------------------

    def _run(self, action, payload):
        dispatcher = self.controller.dispatcher
        operation = dispatcher.submit(Request(action, payload, origin=self.origin))
        result = dispatcher.wait(operation, None)
        if result.status == "awaiting_approval":
            summary = result.data["summary"]
            diff = self._project_diffs.pop(payload.get("plan_id"), None)
            if self.approver is not None and diff is None:  # never ask without the exact preview
                dispatcher.cancel(operation)
                return _outcome(action, "failed", error={
                    "code": "stale_plan", "message": "No reviewed preview for this plan. Validate again."})
            decision = self._ask(ApprovalRequest(action, self.origin, summary.get("title", ""),
                                                 summary.get("message", ""), tuple(summary.get("paths", ())), diff))
            if decision is True:
                self._resolve_approval(operation, True)
                result = dispatcher.wait(operation, None)
            else:
                dispatcher.cancel(operation)
                return _approval_required(action) if decision is None else _denied(action)
        outcome = _outcome(action, result.status, result.data, result.error)
        if result.status == "succeeded":
            self._remember(action, result.data)
        return outcome

    def _remember(self, action, data):
        store = {"project_patch.validate": self._project_diffs, "patch.validate": self._patch_targets}.get(action)
        if store is None or not data.get("plan_id"):
            return
        if len(store) >= PLAN_MEMORY:
            del store[next(iter(store))]
        store[data["plan_id"]] = data["diff"] if action == "project_patch.validate" else data["path"]

    def _ask(self, request):
        """True only for an explicit True from the trusted approver; None when there is none."""
        if self.approver is None:
            return None
        try:
            return self.approver(request) is True
        except Exception:
            return False  # a failing approval window denies

    def _approved_single_write(self, action, payload):
        if self.approver is None:
            return _approval_required(action)
        preview = getattr(self, "_preview_" + action.replace(".", "_"))(payload)
        if isinstance(preview, dict):
            return preview  # the preview failed; nothing was written
        if not self._ask(preview):
            return _denied(action)
        return self._run(action, payload)

    def _relative(self, path):
        return Path(path).relative_to(self.root).as_posix()

    def _read_current(self, path):
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            raise ActionError("not_found", f"Cannot read {self._relative(path)}: {exc}") from exc
        return data, data.decode("utf-8-sig", errors="replace")

    def _preview_text_save(self, payload):
        path, text, sha = payload.get("path"), payload.get("text"), payload.get("sha256")
        if not all(isinstance(value, str) for value in (path, text, sha)):
            raise ActionError("invalid_input", "text.save needs path, text and sha256 as text.")
        data, before = self._read_current(path)
        if hashlib.sha256(data).hexdigest() != sha:
            raise ActionError("source_changed", "The target changed. Reload before saving.")
        name = self._relative(path)
        target = name
        if payload.get("suffix") is not None:
            suffix = str(payload["suffix"])
            original = Path(path)
            target = self._relative(original.with_name(original.stem + (suffix if suffix.startswith("_")
                                                                       else "_" + suffix) + original.suffix))
        message = (f"Save changes to {name}?" if target == name
                   else f"Save a new version of {name} as {target}?") + "\n\nA backup is kept." \
            + _unseen_changes(before, text)
        return ApprovalRequest("text.save", self.origin, "Save file?", message, (str(path),),
                               unified_diff_text([DiffFile(target, before, text)]))

    def _preview_patch_save(self, payload):
        path = self._patch_targets.get(payload.get("plan_id"))
        if path is None:
            raise ActionError("stale_plan", "Preview expired or the project changed. Validate again.")
        result = self._run("patch.result", {"plan_id": payload["plan_id"]})
        if result["status"] != "succeeded":
            return result
        _, before = self._read_current(path)
        name, after = self._relative(path), result["data"]["text"]
        return ApprovalRequest("patch.save", self.origin, "Apply patch?",
                               f"Apply the validated patch to {name}?\n\nA backup is kept."
                               + _unseen_changes(before, after), (path,),
                               unified_diff_text([DiffFile(name, before, after)]))

    def _preview_file_create(self, payload):
        folder, name, content = payload.get("folder"), payload.get("name"), payload.get("content")
        if not all(isinstance(value, str) for value in (folder, name, content)):
            raise ActionError("invalid_input", "file.create needs folder, name and content as text.")
        try:
            created = file_name(name, payload.get("extension", ".txt"), payload.get("timestamp", False))
        except PathSafetyError as exc:
            raise ActionError("invalid_input", str(exc)) from exc
        target = self._relative(Path(folder) / created)
        return ApprovalRequest("file.create", self.origin, "Create file?",
                               f"Create the new file {target}?\n\nAn existing file is never overwritten.",
                               (str(Path(folder) / created),), unified_diff_text([DiffFile(target, "", content)]))

    # --- results ----------------------------------------------------------------

    def _bounded(self, action, outcome, limit):
        budget = limit - NOTE_RESERVE if limit > 2 * NOTE_RESERVE else limit // 2
        outcome, cuts, total = bound(outcome, budget)
        if cuts:
            outcome["truncated"] = cuts[:10] + ([{"field": "...", "more_cuts": len(cuts) - 10}] if len(cuts) > 10 else [])
            outcome["total_bytes"] = total
        if action == "text.open" and outcome["status"] == "succeeded":
            key = (self._key(outcome["data"].get("path")), outcome["data"].get("sha256"))
            if any(cut["field"] == "data.text" for cut in cuts):
                self._partial.add(key)
            else:
                self._partial.discard(key)
        if encoded_size(outcome) > limit:  # only a result made of many unshrinkable parts
            return _outcome(action, "failed", error={
                "code": "capacity", "message": f"The result could not be reduced to {limit} bytes; "
                                               "narrow the request or ask for a larger limit."})
        return outcome
