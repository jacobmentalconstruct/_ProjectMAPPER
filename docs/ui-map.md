# UI entry-point map

Tranche 8, step 8.2 (2026-09-24). Every desktop control, keyboard binding and menu
entry, with the shared action it calls (see `action-inventory.md`) and a test that
drives it. Tests live in `tests/`; `ui_smoke` is `tests/test_ui_smoke.py`.

A test "drives" an entry point when it invokes the real button, binding or handler.
Dialogs, the OS file browser and the vendor export are patched in tests so nothing
leaves the temporary fixture.

## Main window

| Entry point | Action | Test |
| --- | --- | --- |
| Project Root entry, Return | project.set_root | ui_smoke `test_path_entry_return_sets_root_and_rejects_invalid` |
| Choose... | project.set_root | ui_smoke `test_choose_button_sets_root_from_dialog`, `test_cancelled_choose_changes_nothing` |
| ↑ (parent) | project.set_root | ui_smoke `test_up_button_goes_to_parent` |
| Tree: click name / checkbox | selection.set | test_tree_lazy (click, indicator), ui_smoke `test_tree_navigation_columns` |
| Tree: ↑ / ↓ columns | project.set_root | ui_smoke `test_tree_navigation_columns` |
| Tree: expand folder | (presentation) | test_tree_lazy |
| Tree: right-click / Shift+F10 menu | (opens tools) | test_patcher, test_text_editor, test_text_toucher (`keysym="F10"`) |
| Menu: Tokenizing Patcher… | text.open | test_patcher |
| Menu: Open Text Editor… | text.open | test_text_editor |
| Menu: New Text File… | file.name / file.create | test_text_toucher |
| Menu: Delete File… | file.delete | test_file_deletion |
| Menu: Project Patcher… | project_patch.* | test_project_patcher |
| All / None | selection.set | test_safety_regressions |
| Hide pattern entry, Add | exclusions.update | test_exclusions |
| Exclusions | exclusions.inspect | test_exclusions |
| Rescan | project.scan | test_exclusions, test_tree_lazy, test_file_deletion |
| Apply exclusions (hide matches) | exclusions.update | test_exclusions, test_safety_regressions |
| Tree in filedump export | snapshot.export argument | ui_smoke `test_tree_in_filedump_checkbox_adds_the_tree` |
| Preserve binary blobs in DB | capture.configure | test_safety_regressions |
| Compile Snapshot | snapshot.compile | ui_smoke `test_compile_and_every_export_button` |
| Export Tree MD / Filedump MD / Tree+Dump MD | snapshot.export | ui_smoke `test_compile_and_every_export_button`, `test_export_before_compile_is_refused_with_a_label` |
| Export Vendor App | vendor.export | ui_smoke `test_vendor_export_button_runs_the_action` |
| Open Output Folder | output.location | ui_smoke `test_open_output_folder_button_opens_the_resolved_folder` |
| Diagnostics | application.diagnostics | ui_smoke `test_diagnostics_button_reports` |
| Backups… | backup.list | test_backups_window |
| History… (log header) | history.query | test_history_window |
| Progress window: CANCEL OPERATION / close box | dispatcher cancel | ui_smoke `test_progress_cancel_button_stops_the_task_and_closes` |
| Close the main window | dispatcher close (root `<Destroy>`) | ui_smoke `test_destroying_the_main_window_closes_the_controller` |

## Exclusions window

| Entry point | Action | Test |
| --- | --- | --- |
| Apply exclusions checkbox | exclusions.update | test_exclusions |
| Pattern entry, Return / Add | exclusions.update | test_exclusions |
| Per-rule checkboxes, batch buttons | exclusions.update | test_exclusions |
| Escape closes | (presentation) | ui_smoke `test_escape_closes_the_exclusions_window` |
| Mouse wheel (Windows/macOS), buttons 4/5 (X11) | (presentation) | ui_smoke `test_exclusions_mouse_wheel_scrolls_the_rule_list` |

## Text editor

| Entry point | Action | Test |
| --- | --- | --- |
| Open… | text.open | ui_smoke `test_editor_open_and_save_as` |
| Save | text.save | test_text_editor, ui_smoke `EditorBackupTests` |
| Save As… | text.save_as | ui_smoke `test_editor_open_and_save_as`, `EditorBackupTests` |
| Keep backup | `backup` flag of text.save / text.save_as | ui_smoke `EditorBackupTests` |
| Read-only | (presentation) | test_text_editor |
| Find / Replace → Find Next | text.find | ui_smoke `test_editor_find_next_highlights_the_match` |
| Find / Replace → Replace All | text.replace | test_text_editor |
| Tokenizing Patcher… | text.open | test_text_editor |
| Focus: stale-source check | text.open | test_safety_regressions |
| Close with unsaved edits | (presentation) | ui_smoke `test_editor_close_asks_before_discarding`, `test_clean_windows_close_without_asking` |

## New Text File (TextTOUCHER)

| Entry point | Action | Test |
| --- | --- | --- |
| Choose Folder… | (presentation) | test_text_toucher |
| Name, extension, date/time option | file.name | test_text_toucher |
| Create File | file.create | test_text_toucher |
| Close box with a draft | (presentation) | ui_smoke `test_new_file_close_box_asks_before_discarding_a_name`, `test_clean_windows_close_without_asking` |

## Tokenizing Patcher

| Entry point | Action | Test |
| --- | --- | --- |
| Reload Target | text.open | ui_smoke `test_patcher_reload_and_load_patch_json` |
| Load Patch JSON | patch.load | ui_smoke `test_patcher_reload_and_load_patch_json` |
| Copy Schema | patch.schema | ui_smoke `test_patcher_copy_schema_button` |
| Force patch indentation | patch.validate argument | test_patcher |
| Validate / Preview, Apply to Result | patch.validate / patch.result | test_patcher |
| & (link) | (composes the two) | test_patcher (linked tests) |
| Save Result, Save as version | patch.save | test_patcher |
| Keep backup | `backup` flag of patch.save | ui_smoke `test_patcher_keep_backup_checkbox_creates_a_generation` |
| Close box with an unsaved result | (presentation) | ui_smoke `test_patcher_close_box_asks_before_discarding_a_result`, `test_clean_windows_close_without_asking` |

## Project Patcher

| Entry point | Action | Test |
| --- | --- | --- |
| Add File… | project_patch.add_entry | test_project_review_window |
| Load Patch JSON | patch.load | ui_smoke `test_project_patcher_load_json_and_keep_backups`, test_project_review_window |
| Copy Schema | patch.schema | test_project_review_window |
| Force patch indentation | project_patch.validate argument | ui_smoke `test_project_patcher_force_indentation_reaches_validation` |
| Validate / Preview, & (link), Apply Project Patch | project_patch.validate / project_patch.apply | test_project_patcher, test_project_review_window |
| Keep backups | `backup` flag of project_patch.apply | ui_smoke `test_project_patcher_load_json_and_keep_backups` |
| File list, ◀ File / File ▶, ◀ Hunk / Hunk ▶ | (presentation) | test_project_review_window |
| Alt+↑/↓, F8 / Shift+F8, Ctrl+Enter | (presentation) / project_patch.validate | test_project_review_window |
| Close box with an unapplied manifest | (presentation) | ui_smoke `test_project_patcher_close_box_asks_before_discarding_a_manifest`, `test_clean_windows_close_without_asking` |

## Backups window

| Entry point | Action | Test |
| --- | --- | --- |
| Refresh, F5 | backup.list | test_backups_window `test_single_instance_and_refresh_key` |
| Generation and file lists | backup.list / backup.preview | test_backups_window |
| Current / Diff / Backup views | backup.preview | test_backups_window |
| Restore File… / Restore All Files… | backup.preview / backup.restore | test_backups_window |
| Delete Selected… | backup.prune_preview / backup.prune | test_backups_window |
| Clean Up…, keep newest, store selector | backup.prune_preview / backup.prune | test_backups_window, ui_smoke `test_backups_store_selector_drives_clean_up_scope` |

## History window

| Entry point | Action | Test |
| --- | --- | --- |
| Category / Outcome / Contains filters, Clear | history.query | test_history_window |
| Refresh | history.query | test_history_window |
| F5 | history.query | ui_smoke `test_history_refresh_key` |
| Operation list → details | (presentation) | test_history_window |
| Open Backups… | backup.list | test_history_window |
| Live updates | dispatcher subscribe | test_history_window |
| Close box | dispatcher unsubscribe | ui_smoke `test_history_close_box_stops_live_updates` |
