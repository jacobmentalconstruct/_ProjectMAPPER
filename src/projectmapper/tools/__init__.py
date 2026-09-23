"""ProjectMapper's user-facing file tools."""

from importlib import import_module

_MODULES = {
    "PatchError": "patcher", "PatchSession": "patcher", "apply_patch_text": "patcher",
    "validate_target": "patcher", "PatcherWindow": "patcher_ui",
    "ProjectPatchSession": "project_patcher", "project_patch_diff": "project_patcher",
    "ProjectPatcherWindow": "project_patcher_ui", "TextEditorWindow": "text_editor",
    "TextToucherWindow": "text_toucher", "create_text_file": "text_toucher", "file_name": "text_toucher",
}


def __getattr__(name):
    if name not in _MODULES:
        raise AttributeError(name)
    value = getattr(import_module('.' + _MODULES[name], __name__), name)
    globals()[name] = value
    return value

__all__ = [
    "PatchError", "PatchSession", "PatcherWindow", "ProjectPatchSession", "ProjectPatcherWindow",
    "TextEditorWindow", "TextToucherWindow",
    "apply_patch_text", "create_text_file", "file_name", "project_patch_diff", "validate_target",
]
