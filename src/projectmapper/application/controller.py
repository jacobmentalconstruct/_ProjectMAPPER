"""Headless services exposed through named application actions."""

from collections import Counter
import hashlib
import stat
from pathlib import Path
import threading
import json
import copy
from uuid import uuid4
from types import SimpleNamespace

from .contracts import ActionError, ApprovalPlan, Request
from .dispatcher import Dispatcher
from .history import OperationHistory
try:
    from ..core.state import ProjectState
    from ..core.tree import scan_project_tree
    from ..core.tree_model import LogicalTree
    from ..core.exclusions import ExclusionPolicy
    from ..core.files import create_text_file, file_name
    from ..core import snapshots, exports
    from ..core.config import OUTPUT_ROOT_NAME
    from ..core.diagnostics import collect_diagnostics
    from ..tools.patcher import PatchSession, validate_target, apply_patch_text, PatchError
    from ..tools.project_patcher import ProjectPatchSession, project_patch_diff, EXAMPLE_ENTRY, EXAMPLE_MANIFEST
    from ..core.diff import DiffFile, unified_diff_text
    from ..core.backups import BackupError, BackupStore
    from ..core.writes import atomic_write_bytes
except ImportError:
    from core.state import ProjectState
    from core.tree import scan_project_tree
    from core.tree_model import LogicalTree
    from core.exclusions import ExclusionPolicy
    from core.files import create_text_file, file_name
    from core import snapshots, exports
    from core.config import OUTPUT_ROOT_NAME
    from core.diagnostics import collect_diagnostics
    from tools.patcher import PatchSession, validate_target, apply_patch_text, PatchError
    from tools.project_patcher import ProjectPatchSession, project_patch_diff, EXAMPLE_ENTRY, EXAMPLE_MANIFEST
    from core.diff import DiffFile, unified_diff_text
    from core.backups import BackupError, BackupStore
    from core.writes import atomic_write_bytes



def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def inputs(payload, required, optional=()):
    if set(payload) - set(required) - set(optional) or set(required) - set(payload):
        raise ActionError("invalid_input", "Missing or unknown action fields.")


class Controller:
    @property
    def rows(self):
        return self.tree_model.rows

    @rows.setter
    def rows(self, value):
        self.tree_model.replace(value, self.selection)

    @property
    def selection(self):
        return self.tree_model.selection

    @selection.setter
    def selection(self, value):
        self.tree_model.selection = value

    def __init__(self, root, dispatcher=None):
        self.state = ProjectState(Path(root).resolve())
        self.policy = ExclusionPolicy()
        self.policy.load_gitignore(self.state.root)
        self.skipped = []
        self.tree_model = LogicalTree()
        self.dispatcher = dispatcher or Dispatcher()
        # Subscribed before any action exists, so every operation is recorded from its first event.
        self.history = OperationHistory()
        self.dispatcher.subscribe(self.history.observe)
        self.dispatcher.on_observer_error = lambda trace: self.history.record_problem(
            "listener", "An event listener failed", trace)
        self.lock = threading.RLock()
        self.scan_fn = scan_project_tree
        self.plans = {}
        self.include_binary = False
        for name, handler in {
            "project.set_root": self._set_root, "project.scan": self._scan,
            "state.get": lambda p, c: self.state_view(),
            "selection.set": self._selection, "exclusions.update": self._exclusions,
            "exclusions.inspect": self._inspect_exclusions,
            "capture.configure": self._configure, "project.dirty": self._dirty,
            "file.create": self._create, "file.name": self._file_name, "text.save_as": self._save_as,
            "text.find": self._find, "text.replace": self._replace,
            "patch.load": self._load, "patch.schema": self._schema,
            "patch.validate": self._patch_validate, "patch.result": self._patch_result,
            "patch.save": self._patch_save, "project_patch.add_entry": self._add_entry,
            "project_patch.validate": self._project_validate, "project_patch.apply": self._project_apply,
            "snapshot.compile": self._compile, "snapshot.require": self._require,
            "snapshot.export": self._export, "vendor.export": self._vendor,
            "application.diagnostics": self._diagnostics,
            "output.location": self._output_location,
            "text.open": self._open, "text.save": self._save, "file.delete": self._delete,
            "backup.list": self._backup_list, "backup.preview": self._backup_preview,
            "backup.restore": self._backup_restore, "backup.prune_preview": self._backup_prune_preview,
            "backup.prune": self._backup_prune, "history.query": self._history_query,
        }.items():
            self.dispatcher.register(name, handler)

    def execute(self, action, payload=None, *, origin="desktop", request_id=None, timeout=30):
        kwargs = {"request_id": request_id} if request_id else {}
        return self.dispatcher.execute(Request(action, payload or {}, origin=origin, **kwargs), timeout)

    def state_view(self):
        with self.lock:
            return {"root": str(self.state.root), "generation": self.state.generation,
                    "scan_revision": self.state.scan_revision, "capture_revision": self.state.capture_revision,
                    "dirty_reasons": sorted(self.state.dirty_reasons),
                    "snapshot_path": str(self.state.snapshot_path) if self.state.snapshot_path else None}

    def reserve_scan(self):
        """Nonblocking scheduling seam: supersede pending scans without waiting on I/O."""
        with self.lock:
            return self.state.mark_scan_requested()

    def _set_root(self, payload, context):
        inputs(payload, ("path",))
        root = Path(payload["path"]).resolve()
        if not root.is_dir():
            raise ActionError("not_found", "Choose an existing project folder.")
        context.check_cancelled()
        with self.lock:
            self.state.set_root(root)
            self.policy.load_gitignore(root)
            self.skipped = []
            self.tree_model = LogicalTree()
        return self.state_view()

    def _scan(self, payload, context):
        inputs(payload, (), ("revision",))
        with self.lock:
            revision = payload.get("revision") or self.state.mark_scan_requested()
            self.policy.load_gitignore(self.state.root)
            root = self.state.root
            generation = self.state.generation
            policy = copy.deepcopy(self.policy)
        rows, skipped = self.scan_fn(root, policy, context.cancel_event)
        context.check_cancelled()
        with self.lock:
            if generation != self.state.generation or revision != self.state.scan_revision:
                raise ActionError("stale_scan", "Project changed during scan; a newer scan is required.")
            self.skipped = skipped
            self.state.mark_scan_applied(revision, max((r["mtime"] or 0 for r in rows), default=0))
            self.tree_model.replace(rows, self.selection)
        return {"count": len(rows), "revision": revision, "generation": self.state.generation,
                "rows": [{key: str(value) if isinstance(value, Path) else value for key, value in r.items()} for r in rows],
                "skipped": skipped}

    def _open(self, payload, context):
        inputs(payload, ("path",))
        context.check_cancelled()
        session = PatchSession(payload["path"])
        return {"path": str(session.path), "text": session.source, "sha256": fingerprint(session.original_bytes),
                "bom": session.bom}

    def _generation_writer(self, kind, action, context):
        """Return a writer for ``[(path, data, mode)]`` that stores one generation per scope."""
        def write(items):
            groups = {}
            for path, data, mode in items:
                store = BackupStore.for_target(path, self.state.root)
                groups.setdefault((store.scope, str(store.directory)), (store, []))[1].append((path, data, mode))
            names = [f"{store.create(kind, action, context.operation_id, files).id} ({store.scope} store)"
                     for store, files in groups.values()]
            return ", ".join(names)
        return write

    def _changed(self, path):
        with self.lock:
            if path.is_relative_to(self.state.root):
                self.state.mark_dirty("file_transformed", (path,))

    def _save(self, payload, context):
        inputs(payload, ("path", "text", "sha256"), ("suffix", "backup"))
        return self._guarded_save(payload, context, "text.save")

    def _guarded_save(self, payload, context, action):
        if not isinstance(payload["text"], str):
            raise ActionError("invalid_input", "Text must be a string.")
        session = PatchSession(payload["path"])
        if fingerprint(session.original_bytes) != payload["sha256"]:
            raise ActionError("source_changed", "The target changed. Reload before saving.")
        context.check_cancelled()
        backup = None
        if payload.get("backup", False):
            write = self._generation_writer("backup", action, context)
            backup = lambda path, data, mode: write([(path, data, mode)])
        path = session.save(payload["text"], payload.get("suffix"), backup=backup)
        self._changed(path)
        return {"path": str(path), "paths": [str(path)], "sha256": fingerprint(session.original_bytes)}

    def _history_query(self, payload, context):
        inputs(payload, (), ("category", "outcome", "text", "limit"))
        limit = payload.get("limit", 200)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
            raise ActionError("invalid_input", "Limit must be a whole number from 1 to 1000.")
        for key in ("category", "outcome", "text"):
            if payload.get(key) is not None and not isinstance(payload[key], str):
                raise ActionError("invalid_input", f"{key} must be text.")
        try:
            operations = self.history.query(payload.get("category"), payload.get("outcome"),
                                            payload.get("text"), limit)
        except ValueError as exc:
            raise ActionError("invalid_input", str(exc)) from exc
        return {"operations": operations}

    # --- backups: list, preview, restore, retention ------------------------

    def _backup_store(self, scope):
        if scope == "project":
            return BackupStore.for_project(self.state.root)
        if scope == "user":
            return BackupStore.for_user()
        raise ActionError("invalid_input", "Backup scope must be 'project' or 'user'.")

    @staticmethod
    def _as_text(data):
        if data is None:
            return None
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return None

    @staticmethod
    def _bytes_diff(key, current, backup):
        try:
            before = "" if current is None else current.decode("utf-8-sig")
            after = backup.decode("utf-8-sig")
        except UnicodeDecodeError:
            return f"(Not UTF-8 text; current {len(current or b'')} bytes, backup {len(backup)} bytes.)"
        return unified_diff_text([DiffFile(key, before, after)])

    def _backup_list(self, payload, context):
        inputs(payload, (), ("scope",))
        scopes = [payload["scope"]] if payload.get("scope") else ["project", "user"]
        generations = [g.to_dict() for scope in scopes for g in self._backup_store(scope).list()]
        return {"generations": generations, "count": len(generations)}

    def _backup_preview(self, payload, context):
        inputs(payload, ("scope", "generation"), ("targets",))
        store = self._backup_store(payload["scope"])
        try:
            generation = store.get(payload["generation"])
        except BackupError as exc:
            raise ActionError("not_found", str(exc)) from exc
        if generation.status != "ok":
            raise ActionError("backup_invalid", f"Backup {generation.id} is {generation.status}: {generation.problem}")
        recorded = {item["target"]: item for item in generation.files}
        targets = payload.get("targets") or list(recorded)
        if not isinstance(targets, list) or not all(key in recorded for key in targets):
            raise ActionError("invalid_input", "Choose files recorded in this backup.")
        files, bound = [], []
        for key in targets:
            data = store.read(generation.id, key)
            path = validate_target(store.target_path(key))
            if any(part.casefold() == OUTPUT_ROOT_NAME.casefold() for part in path.parts):
                raise ActionError("unsafe_path", f"{key} is inside {OUTPUT_ROOT_NAME}; it cannot be restored.")
            current = path.read_bytes() if path.is_file() else None
            files.append({"target": key, "path": str(path), "current_exists": current is not None,
                          "identical": current == data, "diff": self._bytes_diff(key, current, data),
                          "current_text": self._as_text(current), "backup_text": self._as_text(data),
                          "backup_size": len(data), "current_size": None if current is None else len(current)})
            bound.append({"key": key, "path": str(path), "backup_sha256": recorded[key]["sha256"],
                          "current_sha256": None if current is None else fingerprint(current),
                          "mode": recorded[key]["mode"]})
        plan = {"scope": payload["scope"], "generation": generation.id, "files": bound}
        return {"plan_id": self._store_plan("restore", plan), "generation": generation.id, "files": files}

    def _backup_restore(self, payload, context):
        inputs(payload, ("plan_id",))
        plan = self._plan(payload["plan_id"], "restore")
        store = self._backup_store(plan["scope"])

        def approved(ctx):
            ctx.check_cancelled()
            self._plan(payload["plan_id"], "restore")
            self.plans.pop(payload["plan_id"], None)  # single use: any failure needs a new preview
            checked = []
            for item in plan["files"]:
                path = validate_target(item["path"])
                current = path.read_bytes() if path.is_file() else None
                if (None if current is None else fingerprint(current)) != item["current_sha256"]:
                    raise ActionError("source_changed", f"{item['key']} changed after the preview. Preview again.")
                try:
                    data = store.read(plan["generation"], item["key"])
                except BackupError as exc:
                    raise ActionError("backup_invalid", str(exc)) from exc
                if fingerprint(data) != item["backup_sha256"]:
                    raise ActionError("backup_invalid", f"Backup of {item['key']} changed after the preview.")
                checked.append((item, path, current, data))
            existing = [(path, current, stat.S_IMODE(path.stat().st_mode))
                        for _, path, current, _ in checked if current is not None]
            saved = self._generation_writer("pre-restore", "backup.restore", ctx)(existing) if existing else None
            restored = []
            for item, path, _, data in checked:
                try:
                    atomic_write_bytes(path, data, mode=item["mode"])
                except OSError as exc:
                    detail = (f"Restore stopped at {item['key']}: {exc}. "
                              + (f"Already restored {', '.join(restored)}. " if restored else "No file was restored. ")
                              + (f"Previous contents are in pre-restore backup {saved}." if saved else ""))
                    raise ActionError("recovery_required" if restored else "io_error", detail) from exc
                restored.append(f"restored {item['key']}")
                self._changed(path)
            return {"paths": [str(path) for _, path, _, _ in checked], "count": len(checked), "pre_restore": saved}

        names = "\n".join(item["key"] for item in plan["files"][:20])
        more = f"\n… and {len(plan['files']) - 20} more" if len(plan["files"]) > 20 else ""
        return ApprovalPlan({"title": "Restore from backup?",
                             "message": f"Replace {len(plan['files'])} file(s) with their contents in backup "
                                        f"{plan['generation']}?\n\n{names}{more}\n\nCurrent contents are saved "
                                        "first as a pre-restore backup.",
                             "paths": [item["path"] for item in plan["files"]]}, approved)

    def _backup_prune_preview(self, payload, context):
        inputs(payload, ("scope", "keep"), ("include",))
        keep, include = payload["keep"], payload.get("include") or []
        if not isinstance(keep, int) or isinstance(keep, bool) or keep < 0:
            raise ActionError("invalid_input", "Keep must be a whole number of generations, 0 or more.")
        if not isinstance(include, list) or not all(isinstance(item, str) for item in include):
            raise ActionError("invalid_input", "Include must be a list of generation ids.")
        store = self._backup_store(payload["scope"])
        listed = store.list()
        verified = [g for g in listed if g.status == "ok"]
        unknown = set(include) - {g.id for g in verified}
        if unknown:
            raise ActionError("invalid_input", f"Only verified generations can be removed: {', '.join(sorted(unknown))}")
        # Recovery generations are never chosen by the keep rule, only by explicit id.
        routine = [g for g in verified if g.kind in ("backup", "pre-restore")]
        chosen = {g.id for g in routine[keep:]} | set(include)
        candidates = [g for g in verified if g.id in chosen]
        bound = [{"id": g.id, "fingerprint": store.fingerprint(g.id)} for g in candidates]
        plan_id = (self._store_plan("prune", {"scope": payload["scope"], "candidates": bound,
                                              "bytes": sum(g.size for g in candidates)}) if candidates else None)
        return {"plan_id": plan_id, "bytes": sum(g.size for g in candidates),
                "candidates": [{"id": g.id, "kind": g.kind, "size": g.size, "created_at": g.created_at,
                                "files": len(g.files)} for g in candidates],
                "not_eligible": [{"id": g.id, "status": g.status, "problem": g.problem}
                                 for g in listed if g.status != "ok"]}

    def _backup_prune(self, payload, context):
        inputs(payload, ("plan_id",))
        plan = self._plan(payload["plan_id"], "prune")
        store = self._backup_store(plan["scope"])

        def approved(ctx):
            ctx.check_cancelled()
            self._plan(payload["plan_id"], "prune")
            self.plans.pop(payload["plan_id"], None)
            removed, problems = [], []
            for candidate in plan["candidates"]:
                try:
                    store.remove(candidate["id"], candidate["fingerprint"])
                    removed.append(candidate["id"])
                except (BackupError, OSError) as exc:
                    problems.append(f"{candidate['id']}: {exc}")
            if problems:
                raise ActionError("prune_incomplete", f"Removed {len(removed)} of {len(plan['candidates'])} "
                                  "generation(s). Not removed: " + "; ".join(problems))
            return {"removed": removed, "count": len(removed)}

        ids = "\n".join(candidate["id"] for candidate in plan["candidates"][:20])
        more = f"\n… and {len(plan['candidates']) - 20} more" if len(plan["candidates"]) > 20 else ""
        return ApprovalPlan({"title": "Delete backup generations?",
                             "message": f"Permanently delete {len(plan['candidates'])} backup generation(s) "
                                        f"({plan['bytes']:,} bytes) from the {plan['scope']} store?\n\n{ids}{more}",
                             "paths": [str(store.directory / c["id"]) for c in plan["candidates"]]}, approved)

    def _delete(self, payload, context):
        inputs(payload, ("path",))
        path = validate_target(payload["path"])
        if not path.is_relative_to(self.state.root) or not path.is_file():
            raise ActionError("unsafe_path", "Choose an existing file inside the project.")
        original = path.read_bytes()
        identity = path.stat()
        generation = self.state.generation
        def approved(context):
            context.check_cancelled()
            current = validate_target(path).stat()
            if generation != self.state.generation or (identity.st_dev, identity.st_ino, identity.st_mtime_ns, identity.st_ctime_ns) != (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_ctime_ns) or path.read_bytes() != original:
                raise ActionError("stale_plan", "The target or project changed while awaiting approval.")
            path.unlink()
            self._changed(path)
            return {"paths": [str(path)], "path": str(path)}
        return ApprovalPlan({"title": "Delete file?", "path": str(path),
                             "message": f"Permanently delete this file?\n\n{path}",
                             "sha256": fingerprint(original), "generation": generation}, approved)

    def _dirty(self, payload, context):
        inputs(payload, ("reason",), ("paths",))
        paths = [Path(p).resolve() for p in payload.get("paths", [])]
        if not paths or any(p.is_relative_to(self.state.root) for p in paths):
            self.state.mark_dirty(payload["reason"], [p for p in paths if p.is_relative_to(self.state.root)])
        return self.state_view()

    def _selection(self, payload, context):
        inputs(payload, ("state",), ("path",))
        if payload["state"] not in ("checked", "unchecked"):
            raise ActionError("invalid_input", "Unknown selection state.")
        parent = Path(payload.get("path", self.state.root)).resolve()
        self.tree_model.set_selection(parent, payload["state"])
        self.state.mark_dirty("selection_changed")
        return self.state_view()

    def _exclusions(self, payload, context):
        inputs(payload, ("operation",), ("pattern", "source", "enabled", "respect"))
        operation = payload["operation"]
        if operation == "add":
            self.policy.add_pattern(payload["pattern"])
        elif operation == "delete":
            self.policy.delete_rule(payload["source"], payload["pattern"])
        elif operation == "enable":
            self.policy.set_rule_enabled(payload["source"], payload["pattern"], payload["enabled"])
        elif operation == "respect":
            self.policy.respect_exclusions = bool(payload["respect"])
        else:
            raise ActionError("invalid_input", "Unknown exclusion operation.")
        self.state.mark_dirty("exclusions_changed")
        return {"rules": self.policy.collect_rules()}

    def _inspect_exclusions(self, payload, context):
        inputs(payload, ())
        before = self.policy.collect_rules()
        self.policy.load_gitignore(self.state.root)
        rules = self.policy.collect_rules()
        if rules != before:
            self.state.mark_dirty("exclusions_changed")
        return {"rules": rules}

    def _configure(self, payload, context):
        inputs(payload, ("include_binary",))
        self.include_binary = bool(payload["include_binary"])
        self.state.mark_dirty("capture_options")
        return self.state_view()

    def _create(self, payload, context):
        inputs(payload, ("folder", "name", "content"), ("extension", "timestamp"))
        context.check_cancelled()
        path = create_text_file(**payload)
        self._changed(path)
        return {"path": str(path), "paths": [str(path)]}

    def _file_name(self, payload, context):
        inputs(payload, ("name",), ("extension", "timestamp"))
        return {"name": file_name(payload["name"], payload.get("extension", ".txt"), payload.get("timestamp", False))}

    def _output_location(self, payload, context):
        inputs(payload, ())
        path = self.state.root / OUTPUT_ROOT_NAME
        context.check_cancelled()
        path.mkdir(parents=True, exist_ok=True)
        return {"path": str(path)}

    def _save_as(self, payload, context):
        inputs(payload, ("path", "text"), ("backup",))
        path = validate_target(payload["path"])
        if not path.exists():
            # Nothing is overwritten, so there is nothing to back up.
            return self._create({"folder": str(path.parent), "name": path.name,
                                 "content": payload["text"], "extension": "(None)"}, context)
        session = PatchSession(path)
        generation = self.state.generation
        def approved(ctx):
            ctx.check_cancelled()
            if self.state.generation != generation:
                raise ActionError("stale_plan", "Project changed while awaiting approval.")
            backup = None
            if payload.get("backup", False):
                write = self._generation_writer("backup", "text.save_as", ctx)
                backup = lambda target, data, mode: write([(target, data, mode)])
            saved = session.save(payload["text"], backup=backup)
            self._changed(saved)
            return {"path": str(saved), "paths": [str(saved)]}
        return ApprovalPlan({"title": "Overwrite file?", "path": str(path),
                             "message": f"Overwrite this file?\n\n{path}"}, approved)

    def _find(self, payload, context):
        inputs(payload, ("text", "query"), ("start",))
        text, query = payload["text"], payload["query"]
        index = text.find(query, payload.get("start", 0)) if query else -1
        if index < 0 and query:
            index = text.find(query)
        return {"index": index, "count": text.count(query) if query else 0}

    def _replace(self, payload, context):
        inputs(payload, ("text", "query", "replacement"))
        if not payload["query"]:
            raise ActionError("invalid_input", "Enter text to replace.")
        return {"text": payload["text"].replace(payload["query"], payload["replacement"]),
                "count": payload["text"].count(payload["query"])}

    def _load(self, payload, context):
        inputs(payload, ("path",))
        text = Path(payload["path"]).read_text(encoding="utf-8-sig")
        json.loads(text)
        return {"text": text}

    def _schema(self, payload, context):
        inputs(payload, (), ("project",))
        schema = EXAMPLE_MANIFEST if payload.get("project") else {
            "hunks": [{"description": "Describe the change", "search_block": "old", "replace_block": "new", "use_patch_indent": False}]}
        return {"text": json.dumps(schema, indent=2)}

    def _store_plan(self, kind, value):
        if len(self.plans) >= 64:
            del self.plans[next(iter(self.plans))]
        key = str(uuid4())
        self.plans[key] = (kind, self.state.generation, value)
        return key

    def _plan(self, key, kind):
        found = self.plans.get(key)
        if found is None or found[0] != kind or found[1] != self.state.generation:
            raise ActionError("stale_plan", "Preview expired or the project changed. Validate again.")
        return found[2]

    def _patch_validate(self, payload, context):
        inputs(payload, ("path", "patch", "sha256"), ("force_indent",))
        session = PatchSession(payload["path"])
        if fingerprint(session.original_bytes) != payload["sha256"]:
            raise ActionError("source_changed", "The target changed. Reload before validating.")
        patch = json.loads(payload["patch"]) if isinstance(payload["patch"], str) else payload["patch"]
        result = apply_patch_text(session.source, patch, payload.get("force_indent", False))
        key = self._store_plan("patch", (session, result))
        return {"plan_id": key, "text": result, "path": str(session.path)}

    def _patch_result(self, payload, context):
        inputs(payload, ("plan_id",))
        session, result = self._plan(payload["plan_id"], "patch")
        if session.path.read_bytes() != session.original_bytes:
            raise ActionError("source_changed", "The target changed. Reload and validate again.")
        return {"text": result}

    def _patch_save(self, payload, context):
        inputs(payload, ("plan_id",), ("suffix", "backup"))
        session, result = self._plan(payload["plan_id"], "patch")
        saved = self._guarded_save({"path": str(session.path), "text": result,
                                    "sha256": fingerprint(session.original_bytes),
                                    "suffix": payload.get("suffix"), "backup": payload.get("backup", False)},
                                   context, "patch.save")
        self.plans.pop(payload["plan_id"], None)
        return saved

    def _add_entry(self, payload, context):
        inputs(payload, ("root", "path", "manifest"))
        root, path = validate_target(payload["root"]), validate_target(payload["path"])
        relative = path.relative_to(root).as_posix()
        session = PatchSession(path)
        manifest = json.loads(payload["manifest"]) if isinstance(payload["manifest"], str) else payload["manifest"]
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
            raise ActionError("invalid_input", "Expected a manifest with a files list.")
        if any(item.get("path", "").casefold() == relative.casefold() for item in manifest["files"]):
            raise ActionError("invalid_input", "File is already in the manifest.")
        # An untouched copied example would otherwise make the first validation fail.
        manifest["files"] = [item for item in manifest["files"] if item != EXAMPLE_ENTRY]
        # Template: the first line that matches exactly once (as the engine matches); else the whole file.
        lines = session.source.splitlines()
        counts = Counter(line.strip(" \t") for line in lines)
        anchor = next((line for line in lines if line.strip(" \t") and counts[line.strip(" \t")] == 1),
                      session.source)
        manifest["files"].append({"path": relative, "sha256": fingerprint(session.original_bytes),
                                  "hunks": [{"description": "Describe the change", "search_block": anchor,
                                             "replace_block": anchor, "use_patch_indent": False}]})
        return {"text": json.dumps(manifest, indent=2)}

    def _project_validate(self, payload, context):
        inputs(payload, ("root", "manifest"), ("force_indent",))
        session = ProjectPatchSession(payload["root"], payload["manifest"])
        outcomes = session.review(payload.get("force_indent", False))
        context.check_cancelled()
        errors = [item["error"] for item in outcomes if item["status"] == "error"]
        # Every file is reviewed; only a completely valid manifest becomes an applicable plan.
        key = None if errors else self._store_plan("project_patch", session)
        return {"valid": not errors, "plan_id": key, "count": len(outcomes), "errors": errors,
                "diff": project_patch_diff([item for item in outcomes if item["status"] != "error"]),
                "files": [{k: str(v) if isinstance(v, Path) else v for k, v in item.items() if k != "original_bytes"}
                          for item in outcomes]}

    def _project_apply(self, payload, context):
        inputs(payload, ("plan_id",), ("backup",))
        session = self._plan(payload["plan_id"], "project_patch")
        def approved(ctx):
            ctx.check_cancelled()
            self._plan(payload["plan_id"], "project_patch")
            try:
                backup = (self._generation_writer("backup", "project_patch.apply", ctx)
                          if payload.get("backup", False) else None)
                # Recovery material is always made durable, whether or not backups were requested.
                recover = self._generation_writer("recovery", "project_patch.apply", ctx)
                paths = session.apply_all(backup=backup, recover=recover)
            except PatchError as exc:
                for item in session.results:
                    self._changed(item["path"])
                if "Recovery required" in str(exc):
                    raise ActionError("recovery_required", str(exc)) from exc
                raise
            finally:
                self.plans.pop(payload["plan_id"], None)
            for path in paths:
                self._changed(path)
            return {"paths": [str(p) for p in paths], "count": len(paths)}
        stats = [DiffFile(r["relative_path"], r["original"], r["patched"]) for r in session.results]
        lines = [f"+{d.additions} / -{d.deletions}   {d.relative_path}" for d in stats[:20]]
        if len(stats) > 20:
            lines.append(f"… and {len(stats) - 20} more file(s)")
        total = f"+{sum(d.additions for d in stats)} / -{sum(d.deletions for d in stats)}"
        message = (f"Apply validated changes to {len(stats)} file(s) ({total})?\n\n" + "\n".join(lines)
                   + "\n\nAll files will be rechecked before writing.")
        return ApprovalPlan({"title": "Apply project patch?", "message": message,
                             "paths": [str(r["path"]) for r in session.results]}, approved)

    def _compile(self, payload, context):
        inputs(payload, ())
        self.state.mark_dirty("compile_required")
        self._scan({}, context)
        try:
            path = snapshots.compile_snapshot(self.state.root, self.state.root / OUTPUT_ROOT_NAME,
                self.rows, self.selection, self.policy, self.skipped, self.include_binary,
                context.cancel_event, lambda message, level="INFO": context.progress(message=message, level=level))
        except snapshots.SnapshotSourceChanged as exc:
            context.check_cancelled()
            raise ActionError("source_changed", str(exc)) from exc
        except RuntimeError:
            context.check_cancelled()
            raise
        context.check_cancelled()
        self.state.mark_snapshot(path)
        return {"path": str(path)}

    def _require(self, payload, context):
        inputs(payload, ())
        if self.state.dirty_reasons or self.state.transformed_paths:
            raise ActionError("stale_snapshot", self.state.explain_export_block())
        path = self.state.snapshot_path or self.state.root / OUTPUT_ROOT_NAME / f"{self.state.root.name}_{snapshots.SNAPSHOT_DB_SUFFIX}"
        metadata = snapshots.load_snapshot_metadata(path)
        if not metadata:
            raise ActionError("stale_snapshot", "No readable snapshot for this project. Compile one first.")
        found = metadata.get("snapshot_schema_version")
        if found != snapshots.SNAPSHOT_SCHEMA_VERSION:
            raise ActionError("stale_snapshot", f"Snapshot format {found or 'unknown'} is not supported by this "
                              f"version of ProjectMapper (expects {snapshots.SNAPSHOT_SCHEMA_VERSION}). Compile again.")
        if Path(metadata.get("source_root_absolute_path", "")) != self.state.root:
            raise ActionError("stale_snapshot", "Snapshot belongs to another project.")
        if not snapshots.snapshot_matches(path, self.state.root, self.policy, self.selection, self.include_binary):
            raise ActionError("stale_snapshot", "Project files or capture configuration changed. Compile again.")
        self.state.snapshot_path = path
        return {"path": str(path)}

    def _export(self, payload, context):
        inputs(payload, ("output", "suffix"), ("include_tree",))
        allowed = {"project_tree_markdown": snapshots.TREE_MD_SUFFIX,
                   "project_filedump_markdown": snapshots.FILEDUMP_MD_SUFFIX,
                   "project_tree_and_filedump_markdown": snapshots.COMBINED_MD_SUFFIX,
                   "snapshot_manifest_markdown": snapshots.MANIFEST_MD_SUFFIX}
        if payload["output"] not in allowed or payload["suffix"] != allowed[payload["output"]]:
            raise ActionError("invalid_input", "Unknown snapshot projection.")
        path = Path(self._require({}, context)["path"])
        name = payload["output"]
        if name == "project_tree_and_filedump_markdown" or payload.get("include_tree"):
            content = snapshots.combine_tree_and_filedump_markdown(snapshots.load_snapshot_output(path, "project_tree_markdown"), snapshots.load_snapshot_output(path, "project_filedump_markdown"))
        else:
            content = snapshots.load_snapshot_output(path, name)
        context.check_cancelled()
        target = self.state.root / OUTPUT_ROOT_NAME / snapshots.snapshot_output_filename(self.state.root, payload["suffix"])
        snapshots.write_text_file(target, content)
        return {"path": str(target)}

    def _vendor(self, payload, context):
        inputs(payload, (), ("source_root", "export_root", "make_zip"))
        result = exports.create_vendor_export(**{k: Path(v) if k.endswith("root") else v for k, v in payload.items()}, stop_event=context.cancel_event)
        return {k: str(v) if isinstance(v, Path) else v for k, v in result.items()}

    def _diagnostics(self, payload, context):
        inputs(payload, ())
        return collect_diagnostics(SimpleNamespace(selected_root=self.state.root,
            get_output_dir=lambda: self.state.root / OUTPUT_ROOT_NAME))

    def close(self):
        self.dispatcher.close()


def create_application(root, dispatcher=None):
    """Return the public controller and a separate trusted approval capability.

    Code in the same interpreter is trusted. Future transport adapters must expose
    named actions only; never publish the approval resolver to an agent.
    """
    controller = Controller(root, dispatcher)
    return controller, controller.dispatcher._resolve_approval
