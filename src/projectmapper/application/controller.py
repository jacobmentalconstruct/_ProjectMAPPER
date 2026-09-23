"""Headless services exposed through named application actions."""

import hashlib
from pathlib import Path
import threading
import json
import copy
from uuid import uuid4
from types import SimpleNamespace

from .contracts import ActionError, ApprovalPlan, Request
from .dispatcher import Dispatcher
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
    from ..tools.project_patcher import ProjectPatchSession, project_patch_diff
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
    from tools.project_patcher import ProjectPatchSession, project_patch_diff



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

    def _changed(self, path):
        with self.lock:
            if path.is_relative_to(self.state.root):
                self.state.mark_dirty("file_transformed", (path,))

    def _save(self, payload, context):
        inputs(payload, ("path", "text", "sha256"), ("suffix", "backup"))
        if not isinstance(payload["text"], str):
            raise ActionError("invalid_input", "Text must be a string.")
        session = PatchSession(payload["path"])
        if fingerprint(session.original_bytes) != payload["sha256"]:
            raise ActionError("source_changed", "The target changed. Reload before saving.")
        context.check_cancelled()
        path = session.save(payload["text"], payload.get("suffix"), backup=payload.get("backup", False))
        self._changed(path)
        return {"path": str(path), "paths": [str(path)], "sha256": fingerprint(session.original_bytes)}

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
        inputs(payload, ("path", "text"))
        path = validate_target(payload["path"])
        if not path.exists():
            return self._create({"folder": str(path.parent), "name": path.name,
                                 "content": payload["text"], "extension": "(None)"}, context)
        session = PatchSession(path)
        generation = self.state.generation
        def approved(ctx):
            ctx.check_cancelled()
            if self.state.generation != generation:
                raise ActionError("stale_plan", "Project changed while awaiting approval.")
            saved = session.save(payload["text"])
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
        schema = {"version": 1, "description": "Project patch", "files": []} if payload.get("project") else {
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
        saved = self._save({"path": str(session.path), "text": result,
                            "sha256": fingerprint(session.original_bytes),
                            "suffix": payload.get("suffix"), "backup": payload.get("backup", False)}, context)
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
        manifest["files"].append({"path": relative, "sha256": fingerprint(session.original_bytes),
                                  "hunks": [{"description": "Describe the change", "search_block": session.source,
                                             "replace_block": session.source, "use_patch_indent": False}]})
        return {"text": json.dumps(manifest, indent=2)}

    def _project_validate(self, payload, context):
        inputs(payload, ("root", "manifest"), ("force_indent",))
        session = ProjectPatchSession(payload["root"], payload["manifest"])
        results = session.validate_all(payload.get("force_indent", False))
        context.check_cancelled()
        key = self._store_plan("project_patch", session)
        return {"plan_id": key, "count": len(results), "diff": project_patch_diff(results),
                "files": [{k: str(v) if isinstance(v, Path) else v for k, v in r.items() if k != "original_bytes"} for r in results]}

    def _project_apply(self, payload, context):
        inputs(payload, ("plan_id",), ("backup",))
        session = self._plan(payload["plan_id"], "project_patch")
        def approved(ctx):
            ctx.check_cancelled()
            self._plan(payload["plan_id"], "project_patch")
            try:
                paths = session.apply_all(backup=payload.get("backup", False))
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
        return ApprovalPlan({"title": "Apply project patch?", "message": f"Apply validated changes to {len(session.results)} file(s)?\n\nAll files will be rechecked before writing.",
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


def create_application(root):
    """Return the public controller and a separate trusted approval capability.

    Code in the same interpreter is trusted. Future transport adapters must expose
    named actions only; never publish the approval resolver to an agent.
    """
    controller = Controller(root)
    return controller, controller.dispatcher._resolve_approval
