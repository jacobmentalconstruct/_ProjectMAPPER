"""File creation and naming rules, independent of Tk."""
from datetime import datetime
from pathlib import Path
import re
import os
from .writes import discard_scratch, stage_bytes
from .paths import PathSafetyError as PatchError, validate_target

EXTENSIONS = (".txt", ".py", ".md", ".json", ".csv", ".log", ".bat", ".sh", ".yaml", "(None)")


def file_name(raw_name, extension=".txt", timestamp=False, now=None):
    name = raw_name.strip()
    if not name or name in (".", ".."):
        raise PatchError("Enter a file name.")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((".", " ")):
        raise PatchError("Use a file name without path separators or invalid filename characters.")
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])", name.split(".")[0]):
        raise PatchError("That name is reserved by Windows. Choose another name.")
    if extension not in EXTENSIONS:
        raise PatchError("Choose an extension preset, or (None) and enter your own extension in the name.")
    suffix = Path(name).suffix
    base = name[:-len(suffix)] if suffix else name
    # Explicit extensions and dotfiles take precedence over the preset.
    suffix = suffix or ("" if extension == "(None)" or name.startswith(".") else extension)
    stamp = "_" + (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S") if timestamp else ""
    return base + stamp + suffix


def create_text_file(folder, name, content, extension=".txt", timestamp=False):
    folder = validate_target(folder)
    if not folder.is_dir():
        raise PatchError("The destination folder no longer exists. Choose another folder.")
    path = validate_target(folder / file_name(name, extension, timestamp))
    data = content.encode("utf-8")
    # Exclusive creation protects existing files even if one appears after validation.
    scratch = stage_bytes(path, data)
    try:
        os.link(scratch, path)
    finally:
        discard_scratch(scratch)
    return path


