# Developer guide: actions, events, approvals and errors

Everything ProjectMapper does to a project goes through one in-process action layer. The
desktop window is one client of it. Code in the same interpreter can drive the same
actions without Tk. This guide describes that contract for version 1.0. The desktop
controls that call each action are listed in [action-inventory.md](action-inventory.md)
and [ui-map.md](ui-map.md).

The layer is in-process only. There is no CLI or network transport yet (planned as
Phase 9), and it is not a sandbox: code in the same interpreter is trusted.

## Headless use

```python
from projectmapper.application.controller import create_application

controller, approve = create_application("path/to/project")
try:
    controller.execute("project.scan")
    controller.execute("snapshot.compile")
    result = controller.execute("snapshot.export", {
        "output": "project_tree_markdown", "suffix": "project_tree.md"})
    print(result.status, result.data["path"])        # succeeded …_project_tree.md
finally:
    controller.close()
```

- `create_application(root)` returns the controller and a separate **approval
  capability** (`approve`). The approval capability is private: never hand it to
  untrusted code or expose it through a transport.
- `controller.execute(action, payload=None, *, origin="desktop", request_id=None,
  timeout=30)` submits one request and waits for it to settle. `origin` is an
  attribution label for events and history, not an authority. A reused `request_id`
  with the same inputs returns the same operation; with different inputs it is
  refused.
- `controller.close()` cancels pending work and refuses new requests (`closed`).
- For non-blocking use: `controller.dispatcher.submit(Request(...))` returns an operation
  ID; then `get(id)`, `wait(id, timeout)` and `cancel(id)`.

## Requests, results and statuses

A request is `Request(action, payload, request_id, origin, version=1)`
(`application/contracts.py`). The payload must be a JSON-compatible `dict` of at most
8 MB. Every handler checks its fields: a missing or unknown field is `invalid_input`.

A result is `Result(operation_id, action, status, data, error)`. `status` is one of:

| Status | Meaning |
| --- | --- |
| `queued`, `running` | Not settled yet (`execute` waits past these). |
| `awaiting_approval` | A plan is ready and nothing has been written. `data["summary"]` describes it. |
| `succeeded` | Done; `data` holds the action's output. |
| `failed` | `error` is `{"code", "message", "details"}`; see [Error codes](#error-codes). |
| `cancelled` | Cancelled before completing, or approval was denied or withdrawn. |
| `recovery_required` | A write could not be completed or rolled back cleanly. Recovery material is kept as a backup generation (see the Backups window). |

Actions run one at a time on a single worker thread, in submission order.

## Approvals

Five actions return a plan instead of acting:

| Action | Plan summary title |
| --- | --- |
| `file.delete` | Delete file? |
| `text.save_as` (only when the target exists) | Overwrite file? |
| `project_patch.apply` | Apply project patch? |
| `backup.restore` | Restore from backup? |
| `backup.prune` | Delete backup generations? |

The operation settles as `awaiting_approval`. Nothing has been written at that point.
To continue, a trusted client calls `approve(operation_id, True)` and waits on the same
operation. Any other value denies it (status `cancelled`). Rules:
- A plan executes at most once; approving twice or late is `stale_plan`.
- `cancel(operation_id)` withdraws a pending plan.
- Before acting, each plan re-checks what it previewed: file identity and bytes, the
  project generation, or backup fingerprints. On a mismatch it refuses and nothing is
  written. The code depends on the action:
  - `stale_plan` for a delete or an overwrite
  - `source_changed` or `backup_invalid` for a restore
  - `source_changed` for a project apply
- A clean-up removes only the generations that still match, and reports the others as
  `prune_incomplete`.

`text.save` and `patch.save` do not ask for approval. They carry the SHA-256 of the
bytes the client read, and they refuse with `source_changed` if the file no longer
matches.

## Events

`controller.dispatcher.subscribe(listener)` delivers every event to `listener(event)`
and returns an `unsubscribe` function. `dispatcher.events(after=sequence)` replays the
recent ones (the last 1,000). Its `resync_required` flag is true when events were
missed. An event is `Event(sequence, operation_id, action, origin, type, payload, time,
version=1)`. `sequence` is one global order that every observer sees.

| `type` | Payload |
| --- | --- |
| `accepted` | `{"target": {...}}`: only the `path`, `root`, `folder`, `generation` and `scope` request fields, as strings of at most 4,096 characters |
| `started` | empty |
| `progress` | handler-defined details, such as `message` |
| `awaiting_approval` | `{"summary": ...}` |
| `succeeded` | the result's `paths`, `path`, `count`, `generation`, `revision` and `summary` fields only |
| `failed`, `cancelled`, `recovery_required` | the above plus `"error"` |

Events never carry file text, patches or manifests. Read content from the result.
Listeners run outside the state lock and must not block: calling `execute` or `wait`
from a listener raises `reentrant`. A listener that raises is recorded as an internal
problem and does not stop delivery.

## Error codes

Codes are the stable contract. The labels in `application/errors.py` are the desktop
wording ("Label: message"), and a test checks that every code raised has a label.

| Code | Label | Typical cause |
| --- | --- | --- |
| `invalid_input` | Invalid request | Missing or unknown fields, bad values, malformed patch JSON, a manifest path outside the root; any other `ValueError` from the engines |
| `not_found` | Not found | Unknown operation, plan, backup generation or file |
| `unsafe_path` | That location is not allowed | A linked path (symlink or junction), the read-only `.parts` folder, a target inside `_projectmapper/`, or a delete outside the project |
| `source_changed` | The file changed on disk | `text.save`/`patch.save` fingerprint mismatch; a restore or project-apply target changed after its preview |
| `stale_plan` | The preview is out of date | The project or target changed after the preview; approval no longer pending |
| `stale_scan` | The project changed during the scan | A newer scan superseded this one |
| `stale_snapshot` | The snapshot is out of date | Files, selection, exclusions or capture options changed since compile |
| `backup_invalid` | The backup cannot be used | A backup failed its integrity or ownership check |
| `prune_incomplete` | Clean-up was incomplete | Some generations could not be removed |
| `recovery_required` | Recovery required | A write or rollback failed; recovery material was kept |
| `io_error` | File system error | An operating-system error while reading or writing |
| `cancelled` | Cancelled | Cancelled by request |
| `approval_denied` | Not approved | A pending plan was cancelled |
| `closed` | The application is closing | Requests after `close()` |
| `capacity` | Session limit reached | Request over 8 MB, or more than 4,096 operations in a session |
| `reentrant` | Operation ordering error | `execute`/`wait` called from an event listener |
| `action_failed` | Operation failed | Any other unexpected failure |
| `internal_error` | Internal problem | Internal problem records (History) |

## History

`history.query` (optional `category`, `outcome`, `text` and `limit` of 1–1,000,
default 200) returns one record per operation from any client, newest first. Records
hold action, origin, status, times, duration, approval, affected paths, error and backup
generations. They never hold file contents. The category is the action's prefix
(`snapshot`, `backup`, …) or `internal` for recorded problems. The history keeps 500
records per session and is not persisted.

## Actions

Fields in *italics* are optional. Every action is available headlessly.

| Action | Payload | Notes |
| --- | --- | --- |
| `project.set_root` | `path` | Switch project folder |
| `project.scan` | *`revision`* | Read the folder tree |
| `project.dirty` | `reason`, *`paths`* | Mark the snapshot out of date |
| `state.get` | — | Root, generation, revisions, dirty reasons |
| `selection.set` | `state` (`checked`/`unchecked`), *`path`* | Capture selection for a subtree |
| `exclusions.update` | `operation` (`add`/`delete`/`enable`/`respect`), *`pattern`*, *`source`*, *`enabled`*, *`respect`* | Exclusion rules |
| `exclusions.inspect` | — | Reload `.gitignore` and list rules |
| `capture.configure` | `include_binary` | Keep binary blobs in the snapshot |
| `snapshot.compile` | — | Capture the selected files into the SQLite snapshot |
| `snapshot.require` | — | The current snapshot's path, or `stale_snapshot` |
| `snapshot.export` | `output`, `suffix`, *`include_tree`* | `output`/`suffix` pairs: `project_tree_markdown`/`project_tree.md`, `project_filedump_markdown`/`project_filedump.md`, `project_tree_and_filedump_markdown`/`project_tree_and_filedump.md`, `snapshot_manifest_markdown`/`snapshot_manifest.md` |
| `output.location` | — | The project's output folder |
| `vendor.export` | *`source_root`*, *`export_root`*, *`make_zip`* | Only from a source checkout |
| `application.diagnostics` | — | Environment and write-permission checks |
| `text.open` | `path` | Text and SHA-256 fingerprint |
| `text.save` | `path`, `text`, `sha256`, *`suffix`*, *`backup`* | Guarded by fingerprint |
| `text.save_as` | `path`, `text`, *`backup`* | **Approval** if the target exists |
| `text.find` | `text`, `query`, *`start`* | Pure; index or -1 |
| `text.replace` | `text`, `query`, `replacement` | Pure; returns new text |
| `file.name` | `name`, *`extension`*, *`timestamp`* | Preview a new file name |
| `file.create` | `folder`, `name`, `content`, *`extension`*, *`timestamp`* | Never overwrites |
| `file.delete` | `path` | **Approval** |
| `patch.schema` | *`project`* | The patch JSON example |
| `patch.load` | `path` | Read a patch or manifest file |
| `patch.validate` | `path`, `patch`, `sha256`, *`force_indent`* | Returns a preview and `plan_id` |
| `patch.result` | `plan_id` | The patched text |
| `patch.save` | `plan_id`, *`suffix`*, *`backup`* | Guarded by fingerprint |
| `project_patch.add_entry` | `root`, `path`, `manifest` | Adds a file entry to a manifest |
| `project_patch.validate` | `root`, `manifest`, *`force_indent`* | Per-file review; `plan_id` only when valid |
| `project_patch.apply` | `plan_id`, *`backup`* | **Approval**; all files or none |
| `backup.list` | *`scope`* (`project`/`user`) | Generations with integrity status |
| `backup.preview` | `scope`, `generation`, *`targets`* | Current vs backup; returns `plan_id` |
| `backup.restore` | `plan_id` | **Approval**; saves a pre-restore copy first |
| `backup.prune_preview` | `scope`, `keep`, *`include`* | Returns `plan_id` |
| `backup.prune` | `plan_id` | **Approval** |
| `history.query` | *`category`*, *`outcome`*, *`text`*, *`limit`* | Not itself recorded |

Backups: project files back up under `<project>/_projectmapper/backups/`. Files outside
the project go to a per-user store (`%LOCALAPPDATA%\ProjectMapper\backups` on Windows;
override with `PROJECTMAPPER_USER_BACKUPS`).
