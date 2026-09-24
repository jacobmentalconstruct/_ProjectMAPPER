# Desktop action inventory

Tranche 2 review, 2026-09-16. The desktop calls the same Controller/Dispatcher as
headless in-process clients. This is not a CLI/MCP transport or a process sandbox.

| Desktop operation | Shared action |
| --- | --- |
| Choose root, parent, descend, path entry | project.set_root |
| Refresh tree | project.scan |
| Folder/file checkbox, select all/none | selection.set |
| Add, toggle, enable/disable/delete exclusion rules | exclusions.update |
| Inspect/reload exclusion rules | exclusions.inspect |
| Binary capture option | capture.configure |
| Compile, discover, export tree/filedump/combined/manifest | snapshot.compile / snapshot.require / snapshot.export |
| Vendor export | vendor.export |
| Output folder creation/resolution | output.location |
| Diagnostics | application.diagnostics |
| Editor and patcher open/reload/read | text.open |
| Editor save / Save As | text.save / text.save_as |
| Find / Replace All | text.find / text.replace |
| Filename preview / Create | file.name / file.create |
| Delete | file.delete |
| Load patch / Copy Schema | patch.load / patch.schema |
| Single-file preview / Apply to Result / Save | patch.validate / patch.result / patch.save |
| Project Add File / preview / Apply | project_patch.add_entry / project_patch.validate / project_patch.apply |

Phase 5 contract notes (2026-09-23):
- `project_patch.validate` succeeds whenever the manifest itself is well formed and
  returns `valid`, `errors` and per-file outcomes (status, error, counts, diff hunks,
  flags). `plan_id` is `null` unless every file is valid. Manifest-level errors
  (JSON, duplicates, unsafe or missing paths) still fail the action.
- `patch.schema` with `project: true` returns the full example manifest.
- `project_patch.apply` approval summaries include per-file and total +/− counts.
- Review selection, hunk navigation and highlighting are presentation-only; they
  never change the plan.

Phase 6 contract notes (2026-09-24):
- The `backup` flag of `text.save`, `patch.save` and `project_patch.apply` now
  creates a managed generation (`core/backups.py`) in the target's scope (project
  store or per-user store), not a sibling `.bak`. If a requested backup fails, the
  write does not happen.
- `project_patch.apply` always saves unrestorable originals in a `recovery`
  generation; its `recovery_required` message names the generation or says it
  could not be saved.
- `project_patch.validate` refuses targets inside `_projectmapper/`.

Linked buttons compose the same actions. Project Apply consumes the displayed
plan ID, including after approval; it never silently rebuilds a preview.

Control-plane seams are synchronous: Controller.reserve_scan supersedes older scans
under the state lock without waiting for their I/O. Dispatcher.cancel cancels a
specific operation; enqueueing cancellation behind the operation would defeat it.
Dispatcher.subscribe/get/wait expose observation. The trusted approval resolver is
kept separate from ordinary requests. Future transports must not export it to agents.

Presentation remains local: window/dialog opening, folder choice, field editing,
focus, scroll/expansion, clipboard delivery, read-only and undo state, menu availability,
and opening the OS file browser at the service-resolved output path. Destination
chooser checks are advisory; actions independently enforce path/write rules.
The filedump's include-tree checkbox is a projection argument to snapshot.export.

The GUI queue projects external root, tree, selection, exclusion and capture-option
changes onto Tk. Operation identity distinguishes this desktop's requests; origin
labels are attribution only. Writes trigger a rescan and editor freshness checks.
Editors also check on focus, preserve unsaved buffers, and refuse stale saves through
the service fingerprint check. No continuous filesystem watcher is provided.

Compatibility properties delegate to controller/state. `_accept_compiled_snapshot`
remains an internal compatibility/test helper; production compilation and freshness
decisions belong to snapshot actions. Scan rendering no longer recalculates selection
or republishes controller state. UI task names track presentation-worker lifetimes;
dispatcher operation IDs track domain execution and cancellation.

Tranche 3 completed lazy widgets and measured performance. Expansion/scrolling stay
presentation-only; Controller delegates rows and capture selection to LogicalTree.
Snapshot ABA byte binding,
durable recovery generations, richer patch review and history remain separately
tracked work. A successful tranche 2 audit does not claim those guarantees.
