"""Small health checks, including an exclusively owned temporary write probe."""

from pathlib import Path
import importlib
import sqlite3
import sys
import tempfile


def collect_diagnostics(app=None):
    """Return structured health checks that can be shown in the app log or UI."""
    checks = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    modules = (("src.core.snapshots", "core.snapshots"), ("src.tools.patcher", "tools.patcher"),
               ("src.tools.project_patcher", "tools.project_patcher"),
               ("src.core.files", "core.files"),
               ("src.application.controller", "application.controller"))
    for candidates in modules:
        try:
            loaded = next((name for name in candidates if _try_import(name)), None)
            check(f"Import {candidates[0]}", loaded is not None, loaded or "module unavailable")
        except Exception as exc:
            check(f"Import {candidates[0]}", False, exc)

    root = Path(getattr(app, "selected_root", Path.cwd())) if app is not None else Path.cwd()
    try:
        check("Project root", root.is_dir() and root.resolve() == root, root)
    except OSError as exc:
        check("Project root", False, exc)

    try:
        output = app.get_output_dir() if app is not None else root / "_projectmapper"
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=output, prefix=".projectmapper-diagnostic-") as probe:
            probe.write(b"ok")
            probe.flush()
        check("Output directory writable", True, output)
    except Exception as exc:
        check("Output directory writable", False, exc)

    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("select 1")
        connection.close()
        check("SQLite runtime", True, "available")
    except Exception as exc:
        check("SQLite runtime", False, exc)

    parts = root / ".parts"
    parts_token = str(parts.resolve()).casefold()
    imported_parts = any(parts_token in str(getattr(module, "__file__", "")).casefold()
                         for module in tuple(sys.modules.values()) if module is not None)
    check("Reference folder isolation", (not parts.exists() or parts.is_dir()) and not imported_parts,
          ".parts is optional and never imported or required")

    failed = sum(not item["ok"] for item in checks)
    return {"checks": checks, "ok": failed == 0, "failed": failed}


def _try_import(name):
    try:
        importlib.import_module(name)
        return name
    except Exception:
        return None


def format_diagnostics(report):
    lines = ["ProjectMapper diagnostics", "=" * 24]
    for item in report.get("checks", ()):
        mark = "OK" if item["ok"] else "FAIL"
        lines.append(f"[{mark}] {item['name']}: {item['detail']}")
    lines.append("")
    lines.append("All checks passed." if report.get("ok") else f"{report.get('failed', 0)} check(s) failed.")
    return "\n".join(lines)
