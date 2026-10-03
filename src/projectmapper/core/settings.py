"""Per-user settings that the owner sets in advance: agent result limits and approvals.

The file lives outside every project (the adapters confine agents to the project root),
so an agent cannot change these limits. A missing, unreadable or invalid file never
stops the application: each bad value falls back to its default and is reported.
"""

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import sys

from .writes import atomic_write_bytes

FILE_NAME = "settings.json"

# name: (default, minimum, maximum); booleans have no range.
NUMBERS = {
    "max_result_bytes": (256 * 1024, 4 * 1024, 16 * 1024 * 1024),
    "max_resource_bytes": (1024 * 1024, 4 * 1024, 64 * 1024 * 1024),
    "approval_timeout_seconds": (120, 10, 3600),
}
FLAGS = {"ask_before_single_file_writes": True,
         "ask_before_structural_writes": False}


def settings_path():
    """The per-user settings file (``PROJECTMAPPER_SETTINGS`` overrides it)."""
    override = os.environ.get("PROJECTMAPPER_SETTINGS")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ProjectMapper" / FILE_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ProjectMapper" / FILE_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "projectmapper" / FILE_NAME


@dataclass(frozen=True)
class Settings:
    max_result_bytes: int = NUMBERS["max_result_bytes"][0]
    max_resource_bytes: int = NUMBERS["max_resource_bytes"][0]
    approval_timeout_seconds: int = NUMBERS["approval_timeout_seconds"][0]
    ask_before_single_file_writes: bool = FLAGS["ask_before_single_file_writes"]
    ask_before_structural_writes: bool = FLAGS["ask_before_structural_writes"]
    problems: tuple = ()

    def to_dict(self):
        values = asdict(self)
        values.pop("problems")
        return values


def _checked(values):
    """Return ``(accepted values, problems)``; invalid entries keep their defaults."""
    accepted, problems = {}, []
    for key, value in values.items():
        if key in NUMBERS:
            _, low, high = NUMBERS[key]
            if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
                accepted[key] = value
            else:
                problems.append(f"{key} must be a whole number from {low} to {high}; using the default.")
        elif key in FLAGS:
            if isinstance(value, bool):
                accepted[key] = value
            else:
                problems.append(f"{key} must be true or false; using the default.")
        else:
            problems.append(f"Unknown setting {key!r} ignored.")
    return accepted, problems


def load_settings(path=None):
    path = Path(path) if path else settings_path()
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return Settings()
    except (OSError, UnicodeDecodeError) as exc:
        return Settings(problems=(f"Settings file {path} could not be read ({exc}); using defaults.",))
    try:
        values = json.loads(raw)
    except ValueError as exc:
        return Settings(problems=(f"Settings file {path} is not valid JSON ({exc}); using defaults.",))
    if not isinstance(values, dict):
        return Settings(problems=(f"Settings file {path} must hold a JSON object; using defaults.",))
    accepted, problems = _checked(values)
    return Settings(**accepted, problems=tuple(problems))


def save_settings(values, path=None):
    """Validate and atomically write ``values`` (a dict); raise ``ValueError`` if any is invalid."""
    accepted, problems = _checked(dict(values))
    if problems:
        raise ValueError(" ".join(problems))
    settings = Settings(**accepted)
    path = Path(path) if path else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, (json.dumps(settings.to_dict(), indent=2) + "\n").encode("utf-8"))
    return settings
