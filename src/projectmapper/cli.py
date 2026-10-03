"""One-shot, JSON-first command-line adapter over ProjectMapper's public actions.

The CLI never exposes an approval capability. Operations that require a human
decision therefore return ``approval_required`` and do not write project files.
"""

import argparse
import json
import sys
import threading
from pathlib import Path

from .adapters.session import AdapterSession
from .core.config import (
    COMBINED_MD_SUFFIX,
    FILEDUMP_MD_SUFFIX,
    MANIFEST_MD_SUFFIX,
    TREE_MD_SUFFIX,
)


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_STALE = 3
EXIT_APPROVAL_REQUIRED = 4
EXIT_UNSAFE_PATH = 5
EXIT_CANCELLED = 130

EXIT_CODES = {
    "invalid_input": EXIT_USAGE,
    "stale_snapshot": EXIT_STALE,
    "stale_plan": EXIT_STALE,
    "source_changed": EXIT_STALE,
    "stale_scan": EXIT_STALE,
    "approval_required": EXIT_APPROVAL_REQUIRED,
    "unsafe_path": EXIT_UNSAFE_PATH,
    "cancelled": EXIT_CANCELLED,
}

PROJECTIONS = {
    "tree": ("project_tree_markdown", TREE_MD_SUFFIX),
    "filedump": ("project_filedump_markdown", FILEDUMP_MD_SUFFIX),
    "combined": ("project_tree_and_filedump_markdown", COMBINED_MD_SUFFIX),
    "manifest": ("snapshot_manifest_markdown", MANIFEST_MD_SUFFIX),
}


class CLIUsageError(Exception):
    """An argparse usage error, rendered in the selected output format."""


class ProjectMapperArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CLIUsageError(message)


def _add_common_options(parser):
    parser.add_argument("--root", type=Path, default=argparse.SUPPRESS,
                        help="project folder (default: current directory)")
    parser.add_argument("--exclude", action="append", default=argparse.SUPPRESS,
                        metavar="PATTERN", help="exclude matching filenames; repeat for more patterns")
    parser.add_argument("--include-binary", action="store_true", default=argparse.SUPPRESS,
                        help="preserve selected binary files in the compiled snapshot")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", dest="output_format", action="store_const", const="json",
                        default=argparse.SUPPRESS, help="print JSON (the default)")
    output.add_argument("--text", dest="output_format", action="store_const", const="text",
                        default=argparse.SUPPRESS, help="print a short human-readable result")


def build_parser():
    parser = ProjectMapperArgumentParser(
        prog="projectmapper-cli",
        description="Scan, compile, export and validate ProjectMapper snapshots and patches.",
        epilog=(
            "Examples:\n"
            "  projectmapper-cli --root ./my-project scan\n"
            "  projectmapper-cli compile --root ./my-project --exclude '*.log' --include-binary\n"
            "  projectmapper-cli export tree --root ./my-project\n"
            "  projectmapper-cli validate-patch src/app.py patch.json --root ./my-project\n\n"
            "Patch validation only prepares proposals. apply-patch and apply-project open a\n"
            "trusted local approval window; denial returns exit code 130."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_common_options(parser)
    parser.set_defaults(root=Path.cwd(), exclude=[], include_binary=False, output_format="json")
    subparsers = parser.add_subparsers(dest="command", required=True,
                                       parser_class=ProjectMapperArgumentParser)

    scan = subparsers.add_parser("scan", aliases=["tree"], help="scan and show the project tree")
    _add_common_options(scan)

    compile_command = subparsers.add_parser("compile", help="compile a SQLite snapshot")
    _add_common_options(compile_command)

    export = subparsers.add_parser("export", help="export a compiled snapshot projection")
    _add_common_options(export)
    export.add_argument("projection", choices=sorted(PROJECTIONS),
                        help="tree, filedump, combined, or manifest")

    validate_patch = subparsers.add_parser(
        "validate-patch", help="validate a single-file patch without writing it")
    _add_common_options(validate_patch)
    validate_patch.add_argument("file", type=Path, help="project file to patch")
    validate_patch.add_argument("patch_json", type=Path, help="JSON file containing the patch")

    apply_patch = subparsers.add_parser(
        "apply-patch", help="validate and apply a single-file patch after local approval")
    _add_common_options(apply_patch)
    apply_patch.add_argument("file", type=Path, help="project file to patch")
    apply_patch.add_argument("patch_json", type=Path, help="JSON file containing the patch")

    validate_project = subparsers.add_parser(
        "validate-project", help="validate a project patch manifest without writing it")
    _add_common_options(validate_project)
    validate_project.add_argument("manifest_json", type=Path, help="JSON project patch manifest")

    apply_project = subparsers.add_parser(
        "apply-project", help="validate and apply a project patch after local approval")
    _add_common_options(apply_project)
    apply_project.add_argument("manifest_json", type=Path, help="JSON project patch manifest")

    history = subparsers.add_parser("history", help="show this invocation's action history")
    _add_common_options(history)
    history.add_argument("--category")
    history.add_argument("--outcome")
    history.add_argument("--contains")
    history.add_argument("--limit", type=int, default=200)
    return parser


def exit_code(outcome):
    if outcome.get("status") == "succeeded":
        return EXIT_OK
    error = outcome.get("error") or {}
    if outcome.get("status") == "cancelled":
        return EXIT_CANCELLED
    return EXIT_CODES.get(error.get("code"), EXIT_FAILED)


def _result(command, outcome, code):
    result = {"command": command, **outcome, "exit_code": code}
    return result


def _failed(command, action, error, code):
    return _result(command, {
        "action": action,
        "status": "failed",
        "data": {},
        "error": error,
    }, code)


def _invoke(session, command, action, payload=None):
    outcome = session.call(action, payload or {})
    return _result(command, outcome, exit_code(outcome))


def _text_result(result):
    lines = [f"Command: {result['command']}", f"Status: {result['status']}"]
    error = result.get("error")
    if error:
        lines.append(f"Error: {error.get('code', 'action_failed')}: {error.get('message', '')}")
    data = result.get("data") or {}
    if "rows" in data:
        lines.append(f"Entries: {len(data['rows'])}")
        lines.extend(str(row.get("relative_path", row.get("name", ""))) for row in data["rows"])
    if "path" in data:
        lines.append(f"Path: {data['path']}")
    if "valid" in data:
        lines.append(f"Valid: {data['valid']}")
    if "errors" in data and data["errors"]:
        lines.extend(str(message) for message in data["errors"])
    if "operations" in data:
        lines.append(f"History entries: {len(data['operations'])}")
        lines.extend(f"{item.get('action', '')}: {item.get('status', '')}"
                     for item in data["operations"])
    if result.get("truncated"):
        lines.append("Result truncated to the configured output limit.")
    lines.append(f"Exit code: {result['exit_code']}")
    return "\n".join(lines)


def _emit(result, output_format, stream=None):
    stream = stream or sys.stdout
    if output_format == "text":
        stream.write(_text_result(result) + "\n")
    else:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, {"code": "invalid_input", "message": f"Cannot read JSON file {path}: {exc}"}


def _prepare_session(session, args):
    for pattern in args.exclude:
        outcome = session.call("exclusions.update", {"operation": "add", "pattern": pattern})
        if outcome["status"] != "succeeded":
            return outcome
    if args.include_binary:
        outcome = session.call("capture.configure", {"include_binary": True})
        if outcome["status"] != "succeeded":
            return outcome
    return None


def _run_command(session, args):
    if args.command in ("scan", "tree"):
        return _invoke(session, args.command, "project.scan")
    if args.command == "compile":
        return _invoke(session, args.command, "snapshot.compile")
    if args.command == "export":
        output_name, suffix = PROJECTIONS[args.projection]
        return _invoke(session, args.command, "snapshot.export",
                       {"output": output_name, "suffix": suffix})
    if args.command == "validate-patch":
        opened = session.call("text.open", {"path": str(args.file)})
        if opened["status"] != "succeeded":
            return _result(args.command, opened, exit_code(opened))
        patch, error = _read_json(args.patch_json)
        if error:
            return _failed(args.command, "patch.validate", error, EXIT_USAGE)
        return _invoke(session, args.command, "patch.validate", {
            "path": opened["data"]["path"],
            "sha256": opened["data"]["sha256"],
            "patch": patch,
        })
    if args.command == "apply-patch":
        opened = session.call("text.open", {"path": str(args.file)})
        if opened["status"] != "succeeded":
            return _result(args.command, opened, exit_code(opened))
        patch, error = _read_json(args.patch_json)
        if error:
            return _failed(args.command, "patch.validate", error, EXIT_USAGE)
        validated = session.call("patch.validate", {
            "path": opened["data"]["path"],
            "sha256": opened["data"]["sha256"],
            "patch": patch,
        })
        if validated["status"] != "succeeded":
            return _result(args.command, validated, exit_code(validated))
        return _invoke(session, args.command, "patch.save", {"plan_id": validated["data"]["plan_id"]})
    if args.command == "validate-project":
        manifest, error = _read_json(args.manifest_json)
        if error:
            return _failed(args.command, "project_patch.validate", error, EXIT_USAGE)
        result = _invoke(session, args.command, "project_patch.validate", {"manifest": manifest})
        # The action returns a complete review as a successful operation even when
        # the proposed manifest is invalid; give shell callers a stable input-error code.
        if result["status"] == "succeeded" and not result["data"].get("valid", False):
            result["exit_code"] = EXIT_USAGE
        return result
    if args.command == "apply-project":
        manifest, error = _read_json(args.manifest_json)
        if error:
            return _failed(args.command, "project_patch.validate", error, EXIT_USAGE)
        validated = session.call("project_patch.validate", {"manifest": manifest})
        if validated["status"] != "succeeded":
            return _result(args.command, validated, exit_code(validated))
        if not validated["data"].get("valid", False):
            return _result(args.command, validated, EXIT_USAGE)
        return _invoke(session, args.command, "project_patch.apply", {
            "plan_id": validated["data"]["plan_id"]})
    if args.command == "history":
        payload = {"limit": args.limit}
        if args.category is not None:
            payload["category"] = args.category
        if args.outcome is not None:
            payload["outcome"] = args.outcome
        if args.contains is not None:
            payload["text"] = args.contains
        return _invoke(session, args.command, "history.query", payload)
    return _failed(args.command, "", {"code": "invalid_input", "message": "Unknown command."}, EXIT_USAGE)


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except CLIUsageError as exc:
        result = _failed("usage", "", {"code": "invalid_input", "message": str(exc)}, EXIT_USAGE)
        _emit(result, "json")
        return EXIT_USAGE
    except SystemExit as exc:
        return int(exc.code or 0)

    if args.command not in {"apply-patch", "apply-project"}:
        return _execute(args)

    from .adapters.approval import ApprovalBroker

    broker = ApprovalBroker()
    finished = threading.Event()
    result = {}

    def run_write_command():
        try:
            result["exit_code"] = _execute(args, approver=broker)
        finally:
            finished.set()

    worker = threading.Thread(target=run_write_command, name="projectmapper-cli-action")
    worker.start()
    try:
        broker.serve(finished)
    except KeyboardInterrupt:
        finished.set()
        return EXIT_CANCELLED
    finally:
        worker.join()
    return result.get("exit_code", EXIT_FAILED)


def _execute(args, approver=None):
    try:
        with _session_context(args.root, None, approver) as session:
            preparation = _prepare_session(session, args)
            if preparation:
                result = _result(args.command, preparation, exit_code(preparation))
            else:
                result = _run_command(session, args)
    except KeyboardInterrupt:
        result = _failed(args.command, "", {"code": "cancelled", "message": "Operation cancelled."},
                         EXIT_CANCELLED)
    except (OSError, ValueError) as exc:
        code = EXIT_USAGE if isinstance(exc, ValueError) else EXIT_FAILED
        result = _failed(args.command, "", {"code": "invalid_input" if code == EXIT_USAGE else "io_error",
                                             "message": str(exc)}, code)

    _emit(result, args.output_format)
    return result["exit_code"]


class _session_context:
    """Close the adapter session reliably without importing GUI code."""

    def __init__(self, root, settings, approver=None):
        self.root = Path(root).expanduser().resolve()
        self.settings = settings
        self.approver = approver
        self.session = None

    def __enter__(self):
        self.session = AdapterSession(self.root, "cli", approver=self.approver, settings=self.settings)
        if self.approver is not None:
            self.approver.timeout_seconds = self.session.settings.approval_timeout_seconds
        for problem in self.session.settings.problems:
            print(f"ProjectMapper settings: {problem}", file=sys.stderr)
        return self.session

    def __exit__(self, exc_type, exc, traceback):
        if self.session is not None:
            self.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
