"""Local stdio MCP adapter over ProjectMapper's agent-facing actions.

The optional ``mcp`` SDK is imported only when the server is constructed, so the
desktop application and CLI remain usable without the MCP extra installed.
"""

import argparse
import ast
import inspect
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Annotated, Any

from .adapters.session import AdapterSession, BACKED_UP, EXPOSED, NOT_EXPOSED
from .application import controller as controller_module
from .core.config import (
    APP_VERSION,
    COMBINED_MD_SUFFIX,
    FILEDUMP_MD_SUFFIX,
    MANIFEST_MD_SUFFIX,
    TREE_MD_SUFFIX,
)
from .core import snapshots
from .core.settings import NUMBERS, load_settings


_PROJECTIONS = {
    "tree": ("project_tree_markdown", TREE_MD_SUFFIX),
    "filedump": ("project_filedump_markdown", FILEDUMP_MD_SUFFIX),
    "combined": ("project_tree_and_filedump_markdown", COMBINED_MD_SUFFIX),
    "manifest": ("snapshot_manifest_markdown", MANIFEST_MD_SUFFIX),
}

# MCP tool field schemas supplement the required/optional names extracted from
# the same ``inputs(...)`` contracts that the action handlers enforce.
_FIELD_TYPES = {
    "path": "string", "root": "string", "folder": "string", "name": "string", "to": "string",
    "text": "string", "sha256": "string", "suffix": "string", "backup": "boolean",
    "category": "string", "outcome": "string", "limit": "integer", "start": "integer", "scope": "string",
    "generation": "string", "targets": "array", "keep": "integer", "include": "array",
    "reason": "string", "paths": "array", "state": "string", "operation": "string",
    "pattern": "string", "source": "string", "enabled": "boolean", "respect": "boolean",
    "include_binary": "boolean", "content": "string", "extension": "string",
    "timestamp": "boolean", "query": "string", "replacement": "string", "project": "boolean",
    "patch": "object", "force_indent": "boolean", "plan_id": "string", "manifest": "object",
    "output": "string", "include_tree": "boolean", "source_root": "string",
    "export_root": "string", "make_zip": "boolean", "revision": "integer",
    "max_bytes": "integer", "recursive": "boolean",
}

_DESCRIPTIONS = {
    "max_bytes": "Optional result limit in bytes; the configured user limit is the maximum.",
    "path": "Project-relative path, or an absolute path inside the configured project root.",
    "root": "Must be the configured project root.",
    "patch": "Structured patch proposal accepted by ProjectMapper's patch validator.",
    "manifest": "Structured project patch proposal accepted by ProjectMapper's validator.",
}

_ACTION_DESCRIPTIONS = {
    "file.create": "Create a new file inside the project. Existing files are never overwritten.",
    "patch.validate": "Validate a single-file patch and return its review without writing.",
    "patch.save": "Apply a previously validated single-file patch; approval may be required.",
    "project_patch.validate": "Validate a multi-file project patch and return its review without writing.",
    "project_patch.apply": "Apply a validated project changeset. Content edits and deletes require trusted approval; safe structural operations follow the owner's setting.",
    "text.save": "Save changed text to a project file; approval may be required.",
    "file.delete": "Delete a project file after trusted approval; a backup changeset is kept for undo.",
    "file.rename": "Rename a project file. The change is recorded for undo.",
    "file.move": "Move a project file within the project. The change is recorded for undo.",
    "folder.create": "Create a project folder. The change is recorded for undo.",
    "folder.rename": "Rename a project folder within the project. The change is recorded for undo.",
    "folder.move": "Move a project folder within the project. The change is recorded for undo.",
    "folder.delete": "Delete an empty project folder, or recursively delete its contents when requested. Approval is required for destructive changes.",
}


def _literal_string_tuple(node):
    if not isinstance(node, (ast.Tuple, ast.List)):
        raise RuntimeError("Action input contract must use a literal tuple or list.")
    values = tuple(ast.literal_eval(item) for item in node.elts)
    if not all(isinstance(item, str) for item in values):
        raise RuntimeError("Action input contract fields must be strings.")
    return values


def action_input_contracts():
    """Return required/optional fields declared by Controller handler inputs()."""
    tree = ast.parse(inspect.getsource(controller_module.Controller))
    controller = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                      and node.name == "Controller")
    methods = {node.name: node for node in controller.body if isinstance(node, ast.FunctionDef)}
    init = methods["__init__"]
    registrations = {}
    for node in ast.walk(init):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            if isinstance(value, ast.Attribute) and value.attr.startswith("_"):
                registrations[key.value] = value.attr
            elif isinstance(value, ast.Lambda):
                registrations[key.value] = None
    contracts = {}
    for action, method_name in registrations.items():
        if method_name is None:
            contracts[action] = ((), ())
            continue
        method = methods.get(method_name)
        if method is None:
            continue
        for node in ast.walk(method):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "inputs"):
                required = _literal_string_tuple(node.args[1])
                optional = _literal_string_tuple(node.args[2]) if len(node.args) > 2 else ()
                contracts[action] = (required, optional)
                break
        else:
            raise RuntimeError(f"Action handler {method_name} has no inputs() contract.")
    # These actions share Controller._structural_action's validator, whose contract
    # depends on the registered action name rather than a distinct handler method.
    contracts.update({
        "file.rename": (("path", "name"), ()),
        "file.move": (("path", "to"), ()),
        "folder.create": (("path",), ()),
        "folder.rename": (("path", "name"), ()),
        "folder.move": (("path", "to"), ()),
        "folder.delete": (("path",), ("recursive",)),
    })
    return contracts


def _schema(action, contracts):
    required, optional = contracts[action]
    optional = tuple(field for field in optional if not (field == "backup" and action in BACKED_UP))
    fields = {}
    for field in (*required, *optional):
        kind = _FIELD_TYPES.get(field)
        if kind is None:
            raise RuntimeError(f"No MCP JSON schema type is declared for {action}.{field}.")
        item = {"type": kind}
        if kind == "array":
            item["items"] = {"type": "string"}
        elif kind == "object":
            item["additionalProperties"] = True
        if field in ("patch", "manifest"):
            item = {"anyOf": [{"type": "string"},
                              {"type": "object", "additionalProperties": True}]}
        if field in _DESCRIPTIONS:
            item["description"] = _DESCRIPTIONS[field]
        fields[field] = item
    fields["max_bytes"] = {"type": "integer", "minimum": NUMBERS["max_result_bytes"][1],
                            "description": _DESCRIPTIONS["max_bytes"]}
    return {"type": "object", "properties": fields,
            "required": list(required), "additionalProperties": False}


def schema_contract_errors():
    """Find drift between agent allow-list, handler contracts, and schema fields."""
    contracts = action_input_contracts()
    errors = []
    if set(contracts) != set(EXPOSED) | set(NOT_EXPOSED):
        errors.append("Controller action registrations differ from adapter action inventory.")
    if set(EXPOSED) - set(contracts):
        errors.append("Exposed actions have no handler input contract.")
    for action in EXPOSED:
        if action in contracts:
            try:
                schema = _schema(action, contracts)
                required, optional = contracts[action]
                optional = tuple(field for field in optional
                                 if not (field == "backup" and action in BACKED_UP))
                if (set(schema["properties"]) != set(required) | set(optional) | {"max_bytes"}
                        or schema["required"] != list(required)):
                    errors.append(f"Schema fields drifted for {action}.")
            except RuntimeError as exc:
                errors.append(str(exc))
    return errors


def _annotation(kind):
    return {"string": str, "integer": int, "boolean": bool,
            "array": list[Any], "object": dict[str, Any]}[kind]


def _bound_resource(content, limit):
    encoded = content.encode("utf-8")
    if len(encoded) <= limit:
        return content
    note = f"\n\n[Truncated: resource limit is {limit} bytes; full size was {len(encoded)} bytes.]"
    if len(note.encode("utf-8")) > limit:
        note = f"[Truncated; {len(encoded)} bytes total.]"
        return note.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
    clipped = encoded[:max(0, limit - len(note.encode("utf-8")))].decode("utf-8", errors="ignore")
    return clipped + note


def _tool_function(server, action, contract):
    from pydantic import Field

    required, optional = contract
    optional = tuple(field for field in optional if not (field == "backup" and action in BACKED_UP))
    parameters = []
    annotations = {"return": dict[str, Any]}
    for field in (*required, *optional, "max_bytes"):
        kind = _FIELD_TYPES[field] if field != "max_bytes" else "integer"
        annotation = _annotation(kind)
        if field in ("patch", "manifest"):
            annotation = str | dict[str, Any]
        if field == "max_bytes":
            annotation = Annotated[int, Field(ge=NUMBERS["max_result_bytes"][1])]
        annotations[field] = annotation
        parameters.append(inspect.Parameter(
            field, inspect.Parameter.KEYWORD_ONLY, annotation=annotation,
            default=inspect.Parameter.empty if field in required else None))

    def call_action(**kwargs):
        payload = {key: value for key, value in kwargs.items() if value is not None and key != "max_bytes"}
        outcome = server.call(action, payload, max_bytes=kwargs.get("max_bytes"))
        if outcome.get("status") == "failed" and outcome.get("error", {}).get("code") == "invalid_input":
            # Keep action validation errors machine-readable in the result. JSON-RPC
            # -32602 is reserved for malformed MCP envelopes and is handled by SDK.
            return outcome
        return outcome

    call_action.__name__ = action.replace(".", "_")
    call_action.__doc__ = _ACTION_DESCRIPTIONS.get(action, f"Run the {action} action.")
    call_action.__signature__ = inspect.Signature(parameters, return_annotation=dict[str, Any])
    call_action.__annotations__ = annotations
    return call_action


def create_server(root, *, session=None, approver=None):
    """Build the optional-SDK MCP server; callers own and close its session."""
    try:
        from mcp.server import CacheHint, MCPServer
        from mcp.types import ToolAnnotations
    except ImportError as exc:
        raise RuntimeError("Install ProjectMapper's MCP support with `pip install projectmapper[mcp]`.") from exc

    errors = schema_contract_errors()
    if errors:
        raise RuntimeError("MCP action schemas are out of sync: " + "; ".join(errors))
    session = session or AdapterSession(root, "mcp", approver=approver)
    call_lock = threading.RLock()

    class SerializedSession:
        def call(self, action, payload=None, *, max_bytes=None):
            with call_lock:
                return session.call(action, payload, max_bytes=max_bytes)

    serialized = SerializedSession()
    server = MCPServer(
        "ProjectMapper", version=APP_VERSION,
        description="Read and safely transform files in one configured ProjectMapper project.",
        instructions=("This server is bound to one project root. Paths are confined to that root. "
                      "Validate proposals before applying them. Human approval is never supplied "
                      "by an MCP tool, argument, or client response."),
        cache_hints={
            "tools/list": CacheHint(ttl_ms=60_000, scope="private"),
            "resources/list": CacheHint(ttl_ms=60_000, scope="private"),
            "resources/templates/list": CacheHint(ttl_ms=60_000, scope="private"),
            "resources/read": CacheHint(ttl_ms=0, scope="private"),
        },
    )
    contracts = action_input_contracts()
    for action in sorted(EXPOSED):
        server.add_tool(
            _tool_function(serialized, action, contracts[action]), name=action,
            description=_ACTION_DESCRIPTIONS.get(action, f"Run the {action} action."),
            annotations=ToolAnnotations(readOnlyHint=action not in {
                "text.save", "patch.save", "file.create", "project_patch.apply", "file.delete",
                "file.rename", "file.move", "folder.create", "folder.rename", "folder.move",
                "folder.delete"},
                destructiveHint=action in {"text.save", "patch.save", "project_patch.apply",
                                           "file.delete", "folder.delete"},
                idempotentHint=action in {"state.get", "project.scan", "exclusions.inspect",
                                          "snapshot.require", "application.diagnostics"}),
            structured_output=True,
        )

    def snapshot_resource(projection):
        if projection not in _PROJECTIONS:
            from mcp.server.mcpserver.exceptions import ResourceNotFoundError
            raise ResourceNotFoundError(f"Unknown snapshot projection: {projection}")
        required = serialized.call("snapshot.require")
        if required["status"] != "succeeded":
            raise RuntimeError(required.get("error", {}).get("message", "Snapshot is unavailable."))
        name, _suffix = _PROJECTIONS[projection]
        content = snapshots.load_snapshot_output(Path(required["data"]["path"]), name)
        limit = load_settings().max_resource_bytes
        return _bound_resource(content, limit)

    async def read_tree():
        outcome = serialized.call("project.scan")
        if outcome["status"] != "succeeded":
            raise RuntimeError(outcome.get("error", {}).get("message", "Project scan failed."))
        content = json.dumps(outcome["data"], ensure_ascii=False, separators=(",", ":"))
        return _bound_resource(content, load_settings().max_resource_bytes)

    # The SDK's high-level URI resource API registers static and templated readers.
    server.resource("projectmapper://tree", name="Project tree", mime_type="application/json")(read_tree)
    server.resource("projectmapper://snapshot/{projection}", name="Snapshot projection",
                    mime_type="text/markdown")(snapshot_resource)
    return server, session


def build_parser():
    parser = argparse.ArgumentParser(prog="projectmapper-mcp",
                                     description="Serve one ProjectMapper project over MCP stdio.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root (default: current directory)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    try:
        from .adapters.approval import ApprovalBroker

        broker = ApprovalBroker()
        server, session = create_server(args.root, approver=broker)
        broker.timeout_seconds = session.settings.approval_timeout_seconds
        for problem in session.settings.problems:
            print(f"ProjectMapper settings: {problem}", file=sys.stderr)
    except (RuntimeError, ValueError) as exc:
        print(f"projectmapper-mcp: {exc}", file=sys.stderr)
        return 2

    stopped = threading.Event()
    failures = []

    def run_server():
        try:
            server.run("stdio")
        except BaseException as exc:
            failures.append(exc)
            print(f"projectmapper-mcp: {type(exc).__name__}: {exc}", file=sys.stderr)
        finally:
            stopped.set()

    server_thread = threading.Thread(target=run_server, name="projectmapper-mcp-stdio")
    server_thread.start()
    try:
        broker.serve(stopped)
    except KeyboardInterrupt:
        stopped.set()
        return 130
    finally:
        server_thread.join(timeout=5)
        session.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
