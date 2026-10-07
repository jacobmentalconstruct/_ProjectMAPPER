# UI entry-point map

Tranche 8, step 8.2 (2026-09-24). Every desktop control, keyboard binding and menu
entry, with the shared action it calls (see `action-inventory.md`) and a test that
drives it. Tests live in `tests/`; `ui_smoke` is `tests/test_ui_smoke.py`.

A test "drives" an entry point when it invokes the real button, binding or handler.
Tooltip IDs link interactive controls to the concise help text in `src/projectmapper/tools/tooltips.py`.

Dialogs, the OS file browser and the vendor export are patched in tests so nothing
leaves the temporary fixture.

## Main window

| Entry point | Action | Test | Tooltip ID(s) |
| --- | --- | --- | --- |
| Project Root entry, Return | project.set_root | ui_smoke `test_path_entry_return_sets_root_and_rejects_invalid` | main.project_root |
| Choose... | project.set_root | ui_smoke `test_choose_button_sets_root_from_dialog`, `test_cancelled_choose_changes_nothing` | main.choose_root |
| ↑ (parent) | project.set_root | ui_smoke `test_up_button_goes_to_parent` | main.parent |
| Tree: click name / checkbox | selection.set | test_tree_lazy (click, indicator), ui_smoke `test_tree_navigation_columns` | main.tree |
| Tree: ↑ / ↓ columns | project.set_root | ui_smoke `test_tree_navigation_columns` | main.tree |
| Tree: expand folder | (presentation) | test_tree_lazy | main.tree |
| Tree: right-click / Shift+F10 menu | (opens tools) | test_patcher, test_text_editor, test_text_toucher (`keysym="F10"`) | — (menu) |
| Menu: Tokenizing Patcher… | text.open | test_patcher | — (menu) |
| Menu: Open Text Editor… | text.open | test_text_editor | — (menu) |
| Menu: New Text File… | file.name / file.create | test_text_toucher | — (menu) |
| Menu: Delete File… | file.delete | test_file_deletion | — (menu) |
| Menu: Project Patcher… | project_patch.* | test_project_patcher | — (menu) |
| All / None | selection.set | test_safety_regressions | main.select_all, main.select_none |
| Hide pattern entry, Add | exclusions.update | test_exclusions | main.exclusion_pattern, main.add_exclusion |
| Exclusions | exclusions.inspect | test_exclusions | main.manage_exclusions |
| Rescan | project.scan | test_exclusions, test_tree_lazy, test_file_deletion | main.rescan |
| Apply exclusions (hide matches) | exclusions.update | test_exclusions, test_safety_regressions | main.apply_exclusions |
| Tree in filedump export | snapshot.export argument | ui_smoke `test_tree_in_filedump_checkbox_adds_the_tree` | main.tree_export |
| Preserve binary blobs in DB | capture.configure | test_safety_regressions | main.binary_blobs |
| Compile Snapshot | snapshot.compile | ui_smoke `test_compile_and_every_export_button` | main.compile |
| Export Tree MD / Filedump MD / Tree+Dump MD | snapshot.export | ui_smoke `test_compile_and_every_export_button`, `test_export_before_compile_is_refused_with_a_label` | main.export_tree, main.export_filedump, main.export_combined |
| Export Vendor App | vendor.export | ui_smoke `test_vendor_export_button_runs_the_action` | main.vendor_export |
| Open Output Folder | output.location | ui_smoke `test_open_output_folder_button_opens_the_resolved_folder` | main.output_folder |
| Diagnostics | application.diagnostics | ui_smoke `test_diagnostics_button_reports` | main.diagnostics |
| Backups… | backup.list | test_backups_window | main.backups |
| History… (log header) | history.query | test_history_window | main.history |
| Progress window: CANCEL OPERATION / close box | dispatcher cancel | ui_smoke `test_progress_cancel_button_stops_the_task_and_closes` | progress.cancel |
| Close the main window | dispatcher close (root `<Destroy>`) | ui_smoke `test_destroying_the_main_window_closes_the_controller` | — (window close) |

## Exclusions window

| Entry point | Action | Test | Tooltip ID(s) |
| --- | --- | --- | --- |
| Apply exclusions checkbox | exclusions.update | test_exclusions | exclusions.apply |
| Pattern entry, Return / Add | exclusions.update | test_exclusions | exclusions.pattern, exclusions.add |
| Per-rule checkboxes, batch buttons | exclusions.update | test_exclusions | exclusions.row_select, exclusions.rule, exclusions.select_all, exclusions.deselect_all, exclusions.exclude_selected, exclusions.allow_selected, exclusions.delete_selected |
| Escape closes | (presentation) | ui_smoke `test_escape_closes_the_exclusions_window` | — (keyboard binding) |
| Mouse wheel (Windows/macOS), buttons 4/5 (X11) | (presentation) | ui_smoke `test_exclusions_mouse_wheel_scrolls_the_rule_list` | — (scroll gesture) |

## Text editor

| Entry point | Action | Test | Tooltip ID(s) |
| --- | --- | --- | --- |
| Open… | text.open | ui_smoke `test_editor_open_and_save_as` | editor.open |
| Save | text.save | test_text_editor, ui_smoke `EditorBackupTests` | editor.save |
| Save As… | text.save_as | ui_smoke `test_editor_open_and_save_as`, `EditorBackupTests` | editor.save_as |
| Keep backup | `backup` flag of text.save / text.save_as | ui_smoke `EditorBackupTests` | patcher.backup |
| Read-only | (presentation) | test_text_editor | editor.read_only |
| Find / Replace → Find Next | text.find | ui_smoke `test_editor_find_next_highlights_the_match` | editor.find, editor.find_next |
| Find / Replace → Replace All | text.replace | test_text_editor | editor.find, editor.replace, editor.replace_all |
| Tokenizing Patcher… | text.open | test_text_editor | editor.patcher |
| Focus: stale-source check | text.open | test_safety_regressions | editor.text |
| Close with unsaved edits | (presentation) | ui_smoke `test_editor_close_asks_before_discarding`, `test_clean_windows_close_without_asking` | — (window close) |

## New Text File (TextTOUCHER)

| Entry point | Action | Test | Tooltip ID(s) |
| --- | --- | --- | --- |
| Choose Folder… | (presentation) | test_text_toucher | new_file.choose_folder |
| Name, extension, date/time option | file.name | test_text_toucher | new_file.name, new_file.extension, new_file.timestamp |
| Create File | file.create | test_text_toucher | new_file.create |
| Close box with a draft | (presentation) | ui_smoke `test_new_file_close_box_asks_before_discarding_a_name`, `test_clean_windows_close_without_asking` | — (window close) |

## Tokenizing Patcher

| Entry point | Action | Test | Tooltip ID(s) |
| --- | --- | --- | --- |
| Reload Target | text.open | ui_smoke `test_patcher_reload_and_load_patch_json` | patcher.reload |
| Load Patch JSON | patch.load | ui_smoke `test_patcher_reload_and_load_patch_json` | project_patcher.load |
| Copy Schema | patch.schema | ui_smoke `test_patcher_copy_schema_button` | project_patcher.schema |
| Force patch indentation | patch.validate argument | test_patcher | project_patcher.indent |
| Validate / Preview, Apply to Result | patch.validate / patch.result | test_patcher | patcher.proposal, patcher.validate, patcher.apply |
| & (link) | (composes the two) | test_patcher (linked tests) | patcher.link |
| Save Result, Save as version | patch.save | test_patcher | patcher.save, patcher.version |
| Keep backup | `backup` flag of patch.save | ui_smoke `test_patcher_keep_backup_checkbox_creates_a_generation` | patcher.backup |
| Close box with an unsaved result | (presentation) | ui_smoke `test_patcher_close_box_asks_before_discarding_a_result`, `test_clean_windows_close_without_asking` | — (window close) |

## Project Patcher

| Entry point | Action | Test | Tooltip ID(s) |
| --- | --- | --- | --- |
| Add File… | project_patch.add_entry | test_project_review_window | project_patcher.add_file |
| Load Patch JSON | patch.load | ui_smoke `test_project_patcher_load_json_and_keep_backups`, test_project_review_window | project_patcher.load |
| Copy Schema | patch.schema | test_project_review_window | project_patcher.schema |
| Force patch indentation | project_patch.validate argument | ui_smoke `test_project_patcher_force_indentation_reaches_validation` | project_patcher.indent |
| Validate / Preview, & (link), Apply Project Patch | project_patch.validate / project_patch.apply | test_project_patcher, test_project_review_window | project_patcher.proposal, project_patcher.validate, project_patcher.link, project_patcher.apply |
| Keep backups | `backup` flag of project_patch.apply | ui_smoke `test_project_patcher_load_json_and_keep_backups` | project_patcher.backup |
| File list, ◀ File / File ▶, ◀ Hunk / Hunk ▶ | (presentation) | test_project_review_window | project_patcher.list, project_patcher.prev_operation, project_patcher.next_operation, project_patcher.prev_hunk, project_patcher.next_hunk |
| Alt+↑/↓, F8 / Shift+F8, Ctrl+Enter | (presentation) / project_patch.validate | test_project_review_window | — (keyboard binding) |
| Close box with an unapplied manifest | (presentation) | ui_smoke `test_project_patcher_close_box_asks_before_discarding_a_manifest`, `test_clean_windows_close_without_asking` | — (window close) |

## Backups window

| Entry point | Action | Test | Tooltip ID(s) |
| --- | --- | --- | --- |
| Refresh, F5 | backup.list | test_backups_window `test_single_instance_and_refresh_key` | backups.refresh |
| Generation and file lists | backup.list / backup.preview | test_backups_window | backups.generations, backups.files |
| Current / Diff / Backup views | backup.preview | test_backups_window | — (read-only views) |
| Restore File… / Restore All Files… | backup.preview / backup.restore | test_backups_window | backups.restore_file, backups.restore_all |
| Delete Selected… | backup.prune_preview / backup.prune | test_backups_window | backups.delete |
| Clean Up…, keep newest, store selector | backup.prune_preview / backup.prune | test_backups_window, ui_smoke `test_backups_store_selector_drives_clean_up_scope` | backups.cleanup, backups.keep, backups.scope |

## History window

| Entry point | Action | Test | Tooltip ID(s) |
| --- | --- | --- | --- |
| Category / Outcome / Contains filters, Clear | history.query | test_history_window | history.category, history.outcome, history.contains, history.clear |
| Refresh | history.query | test_history_window | history.refresh |
| F5 | history.query | ui_smoke `test_history_refresh_key` | history.refresh |
| Operation list → details | (presentation) | test_history_window | history.operations |
| Open Backups… | backup.list | test_history_window | history.backups |
| Live updates | dispatcher subscribe | test_history_window | — (automatic) |
| Close box | dispatcher unsubscribe | ui_smoke `test_history_close_box_stops_live_updates` | — (window close) |
