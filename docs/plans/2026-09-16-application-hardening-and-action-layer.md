# ProjectMapper: application hardening and shared action layer

Date: 2026-09-16

Status: **Phase 2 completed and parked after external-review corrections, action
inventory and 110 passing tests. Phase 3 is next. See `.dev-log/02-review-followthrough.md`.**

Implementation was authorized after the initial planning review. Later tranches remain
subject to their entry records, implementation/review cycles and acceptance gates.

## 1. Expected outcome

ProjectMapper remains a native dark-theme desktop application for mapping projects,
editing and transforming files, and compiling portable SQLite snapshots. Its
application operations become accessible through one shared action layer, with
consistent safety rules, state transitions, results, and observable progress.

The desktop is the first client of that layer. Future CLI and MCP clients can reuse
the same operations without reimplementing application rules or constructing Tk
windows. Clients attached to the same running application can observe the same
operation stream. A separate process requires an explicit connection to that
application to share live state; importing the same Python package is not enough.

The completed pass also provides responsive large-project navigation, per-file
patch review, recoverable backup generations, useful session history, and a
repeatable verification suite.

## 2. Current state and gap

The following observations are based on the current source and prior checks. The
implementation phase must establish a new baseline before treating past test
results as evidence for new code.

| Area | Current state | Required difference |
| --- | --- | --- |
| Structure | `src/app.py` contains UI, exclusion policy, snapshot schema/compiler, export logic, and worker coordination. | Extract focused services and leave the UI responsible for presentation and collecting inputs. |
| Action routing | UI callbacks invoke engines, write files, update state, and display approvals directly. | Route application operations through a typed dispatcher with shared checks and results. |
| State | `ProjectState` exists, while the app retains parallel scan, snapshot, task, and dirty-state fields. | Establish one authoritative state owner and read-only views for clients. |
| Scanning | `src/core/tree.py` accumulates directory sizes during a walk; tree rendering is eager. | Reuse safe metadata, render lazily, and preserve navigation without hiding filesystem changes. |
| Project patches | The UI has JSON authoring, Add File, combined diff, linked actions, and apply approval. | Add per-file status and source/diff/result views with hunk navigation. |
| Recovery | Optional `.bak` siblings exist; the fixed name can replace an earlier backup. | Provide identifiable generations, restoration preview/approval, and ownership-aware retention. |
| History | General log messages describe operations. | Derive a searchable/filterable session history from structured operation events. |
| Testing | Focused suites passed previously; broader runs failed on temporary-directory and cache permissions. | Diagnose the actual environment issue and get a clean full run with isolated fixtures. |

### Specific issues to establish and fix first

- Project patch rollback currently loops over every original file after an exception,
  including failures before any destination was replaced. It can overwrite an
  external edit detected during staging. Track the exact replaced set and restore
  only that set, with conflict checks.
- Snapshot lookup is preceded by a state check that rejects a missing in-memory
  snapshot path. Verify that this does not make a valid existing snapshot impossible
  to discover after startup.
- Root changes reset scan counters. Use a project generation or session identifier
  as well as revisions so an old result cannot be accepted after switching roots
  away and back.
- Snapshot dirtiness must include capture selection and capture options, not only
  file transformations and exclusion changes.
- Audit project patch input changes during validation and approval. Programmatic
  edits and Tk modified-event timing must not permit stale application.
- Diagnose fresh temporary-directory permission failures. Existing evidence does
  not establish that file locks are the cause; do not delete old directories or
  weaken permissions as a speculative fix.
- Diagnostics must use uniquely named, exclusively created probe files and clean
  up only its own probes. It must not overwrite an existing fixed-name file.

## 3. Scope and constraints

### Included

1. Baseline audit and regression coverage for safety-critical behavior.
2. A shared in-process action dispatcher, results, event stream, and approval flow.
3. Migration of all UI-accessible application operations to that layer.
4. Extraction of exclusions, snapshots, exports, and state coordination.
5. Metadata reuse, lazy tree rendering, and measured performance checks.
6. Per-file and per-hunk project patch review.
7. Optional backup generations, restoration, and retention controls.
8. Session operation history and consistent error reporting.
9. Isolated tests, failure injection, GUI smoke checks, and standalone export checks.
10. Documentation and a final acceptance report.

### Deferred

- Shipping a CLI command surface or an MCP server.
- Network listeners, IPC transport, remote authentication, and cross-process coordination.
- Persistent event infrastructure, automatic filesystem watchers, and plugin frameworks.
- Repository patch operations for creation, deletion, rename, or binary transformation.
- Arbitrary shell execution or arbitrary dynamically registered external actions.
- A promise of crash-atomic multi-file writes. Ordinary filesystem replacements
  cannot provide one atomic transaction across an entire repository.

### Preserved behavior

- Keep the dark theme and linked Validate/Apply `&` controls.
- Preserve the distinction between single-file Apply to Result and Save Result.
- Preserve project patch validation, review, and explicit apply approval.
- Keep the current JSON hunk schema and version-1 project manifest compatible.
- Preserve UTF-8/BOM handling, existing newline behavior, guarded saves, exclusive
  creation, and version-save collision refusal.
- Keep delete approval blocking and default-deny; closing the prompt does not approve.
- Keep `.parts/` strictly read-only reference material. No writes, imports, runtime
  assets, vendor dependencies, or requirement that the directory exist.
- Preserve the ability to work with explicitly chosen files/folders outside the
  mapper's current root where existing tools support it; give those targets an
  explicit scope rather than silently broadening project-patch scope.
- Do not impose new approvals on routine actions unless needed by the accepted
  workflow. Existing destructive-action approvals must be enforced below the UI.

## 4. Architecture

```text
Desktop adapter       Future CLI adapter       Future MCP adapter
       |                       |                        |
       +--------------- shared action API --------------+
                               |
                       Action dispatcher
                validation / approval / scheduling
                               |
                    Application services
          project / files / patches / snapshots / backups
                               |
                   Filesystem and SQLite

Services -> state transitions + operation events -> subscribers
                                                   | UI adapter
                                                   | history
                                                   | future connected clients
```

### Dependency rules

- Core data types, engines, services, and the dispatcher must not import Tkinter,
  UI modules, or `src.app`.
- Adapters collect inputs, present results, and translate events into interface updates.
- Services own domain behavior; the dispatcher handles cross-cutting coordination.
- Engines remain directly unit-testable. Public interactive entry points use the
  dispatcher; UI callbacks cannot call private write services directly.
- Dependencies are supplied explicitly to one application controller/runtime.
  Avoid global singleton state and circular imports.
- Use the standard library initially. A small explicit action registry is sufficient.
- The seam is a logical entry point, not a requirement to run all work synchronously
  or make one class implement every operation.

### Proposed module boundaries

Exact filenames may be adjusted during extraction when doing so reduces complexity.

| Location | Responsibility |
| --- | --- |
| `src/application/contracts.py` | Request/result/event/error/approval data contracts. |
| `src/application/dispatcher.py` | Action registry, dispatch, operation lifecycle, scheduling and cancellation. |
| `src/application/controller.py` | Compose services, own shared state, provide the public action API. |
| `src/application/approvals.py` | Pending reviewed operations and trusted approval resolution. |
| `src/application/history.py` | Bounded session history derived from events. |
| `src/core/state.py` | Project generation, revisions, freshness and state views. |
| `src/core/tree.py` | Filesystem walk and metadata reuse primitives. |
| `src/core/exclusions.py` | Exclusion policy independent of UI. |
| `src/core/snapshots.py` | Schema, capture and snapshot loading. |
| `src/core/exports.py` | Markdown and vendor export behavior. |
| `src/core/writes.py` | Guarded staging/replacement and cleanup primitives. |
| `src/core/backups.py` | Backup ownership, generations, inspection, restore and retention. |
| `src/core/diff.py` | Diff data, summaries and hunk coordinates. |
| `src/tools/` | Existing patch engines and tool windows; engines remain independent of windows. |
| `src/ui/` | Shared styling, event bridge, main views and review/history views as needed. |
| `src/app.py` | Composition/launch entry point and temporary compatibility exports. |

## 5. Action contract

### Request

Define concrete schemas for each action rather than passing arbitrary callbacks
or Tk variables through the seam.

- Stable action name and contract version.
- Typed payload containing paths, manifest/content references, options, and IDs.
- Request ID; operation ID assigned by the runtime.
- Origin metadata such as desktop/test/future CLI/future MCP for attribution.
  Origin text is not authorization.
- Explicit project/session scope and applicable expected revisions.
- Validated plan ID for operations that consume a reviewed preview.

Paths, enums, timestamps, and errors must have documented serializable forms.
Do not put widgets, exception objects, open file handles, or callbacks in public
payloads. Keep large contents and previews in bounded session storage and retrieve
them explicitly instead of copying them into every event.

### Result

Return a structured result with operation ID, status, data, affected paths,
resulting revisions, and any error or recovery details.

Lifecycle states: queued, running, awaiting approval, succeeded, failed, cancelled,
and recovery required. A request rejected by validation/busy checks has a clear
structured outcome too. Approval denial is cancellation with an explicit reason.

Example error codes to define: invalid_input, unsupported_encoding, unsafe_path,
not_found, ambiguous_hunk, overlapping_hunks, stale_plan, source_changed, busy,
approval_required, approval_denied, io_error, and recovery_required.

Do not label partial recovery as success or cancellation. Distinguish no-op success
from a write that changed bytes. Unexpected errors retain diagnostic details but
present a concise user-facing message.

### Events and observation

- Events include schema version, increasing sequence number, operation ID, project
  generation, type, time, and structured payload.
- Emit accepted/started/progress/approval requested/completed/failed/cancelled events
  plus meaningful state changes and rollback/backup outcomes.
- The controller applies authoritative state changes before notifying subscribers.
- Tk receives events through a queue drained on the UI thread. Workers never update
  widgets or run modal prompts directly.
- Subscriber failures do not break operations. Unsubscribe when views close.
- Bound retained events and progress traffic. Preserve terminal outcomes and expose
  a resynchronization state snapshot if a consumer falls behind.
- Never put complete source files, patch contents, or environment secrets in history
  merely because they were present in a request.
- A caller may query operation status and shared state without a Tk root.

### Scheduling and cancellation

- Start with simple serialized conflicting project operations; avoid a generic
  fine-grained locking framework until measurements justify it.
- Independent read-only work can run when its state snapshot is well-defined.
- Capture root, generation, selection, exclusions, and options at operation start.
  Do not read mutable UI values partway through a worker operation.
- Queue or reject conflicts consistently with a useful reason. Never silently drop
  a second request or allow save and capture to race.
- Waiting for approval releases execution locks. Reacquire and revalidate before
  performing the approved mutation.
- Each operation has its own cancellation token. Cancellation cannot leak into a
  later request or interrupt another unrelated operation.
- Check cancellation between safe units; once replacement starts, reach a safe
  completion or rollback boundary before reporting cancellation.
- Deduplicate the same request ID within a session. A repeated Apply click or
  adapter retry must not repeat a completed mutation. This is not durable
  exactly-once execution across application restarts.

## 6. Approval and write safety

Approval is application behavior, not a messagebox side effect.

1. Prepare an immutable operation plan: targets, source fingerprints, intended
   result fingerprints, options, project generation and requested effect.
2. Publish its review summary and approval request where the action requires one.
3. A trusted human-interaction adapter records approve or deny against that plan.
4. The controller accepts a decision once, then rechecks inputs, scope, source bytes,
   operation conflicts and relevant revisions before mutation.
5. Changed state invalidates the plan and approval; the user reviews the new plan.

A public `approved: true` field is insufficient. Future agent-facing adapters must
not gain authority to approve their own destructive operations. The trusted
approval resolver is separate from ordinary action submission. Without a trusted
approver, an approval-required action remains pending or returns that requirement.

Approval policy for this pass:

| Operation | Policy |
| --- | --- |
| Scan, read, validate, diagnostics | No destructive approval. |
| Routine guarded save/new file | Preserve current workflow; enforce freshness/exclusive creation. |
| Save As over an existing file | Preserve overwrite confirmation, bound to the target state. |
| Delete file | Explicit blocking approval, default deny, then identity/freshness recheck. |
| Apply project patch | Explicit review/apply approval for the exact validated plan. |
| Restore backup | Preview and explicit blocking approval. |
| Delete managed backup generations | Show exact candidates and obtain explicit approval. |
| Replace All in editor | Preserve the current confirmation and unsaved-buffer behavior. |

### Multi-file failure handling

- Validate all files and stage outputs before replacements.
- Recheck direct paths and source bytes after staging and immediately before their
  replacement. These checks reduce external-edit races; they are not cross-process
  filesystem transaction isolation.
- Keep a journal of successfully replaced files and their before/after fingerprints.
- On failure, restore only files replaced by this operation, in reverse order.
- Before restoring, verify the destination still contains the bytes this operation
  wrote. Preserve subsequent external changes and report a recovery conflict.
- Restore through the atomic write primitive and preserve supported file modes.
- Track cleanup failures separately; they must not hide the original error or stop
  attempts to recover other eligible files.
- If recovery is incomplete, retain recovery material and report affected paths
  through events, history and the UI. Invalidate relevant snapshots regardless.
- Do not call this crash-proof or fully transactional. Document interruption and
  platform limitations honestly.

## 7. UI action inventory and migration matrix

This is the initial inventory. Phase 0 must audit every button, menu item, binding,
trace handler and indirect callback, and record any additional entry points.

| UI operation | Proposed action/service | Notes |
| --- | --- | --- |
| Choose root, typed root, parent/folder navigation | project.set_root | Validate root; advance project generation; schedule scan. |
| Rescan | project.scan | Cancellable; reject obsolete result application. |
| Toggle file/folder capture checkbox | selection.set | Recursive intent applies to unloaded descendants. |
| Select/deselect all capture entries | selection.set_all | Change model state, not only loaded tree rows. |
| Apply exclusions switch | exclusions.set_enabled | Preserve stored rules while bypassed. |
| Add/remove/enable/disable exclusion rules | exclusions.update | Support batch actions and current per-root imported overrides. |
| Compile snapshot | snapshot.compile | Freeze capture configuration and enforce freshness. |
| Capture binary option | capture.set_options | Changing capture options invalidates the prior snapshot configuration. |
| Export tree/filedump/combined/manifest | snapshot.export | Validate snapshot identity/freshness; projection options in request. |
| Export vendor application | application.export_vendor | Explicit app source root; no reference/cache/runtime dependencies. |
| Open output folder | output.resolve + desktop shell effect | Path resolution is shared; opening Explorer is adapter-specific. |
| Open/reload text target | text.open / text.reload | Return content/session identity and source fingerprint. |
| Editor Save and Save As | text.save / text.save_as | Guarded writes, explicit overwrite approval when applicable. |
| Find and replace-all | text.find / text.replace | Operate on a revisioned buffer or explicit content; no implicit save. |
| Create text file | file.create | Name validation, destination scope and exclusive creation. |
| Delete file | file.delete | Prepare/approve/execute through shared policy. |
| Load patch JSON | patch.load | File decoding and parse errors shared; chooser stays local. |
| Copy patch schema | patch.schema | Shared schema result; clipboard assignment stays local. |
| Single-file Validate | patch.validate | Produce immutable source/result/diff plan. |
| Single-file Apply to Result | patch.result | Consume current validated plan; does not write the file. |
| Single-file Save Result/version | patch.save | Consume current plan; same guarded write service as editor. |
| Project Add File | project_patch.add_entry | Safe relative path, duplicate prevention, return revised manifest. |
| Project Validate | project_patch.validate | Collect per-file/hunk outcomes; no writes. |
| Project Apply | project_patch.apply | Validated approved plan; staged writes and recovery reporting. |
| Backup inspect/list | backup.list / backup.preview | Read-only, ownership-aware. |
| Restore/prune backups | backup.restore / backup.prune | Plan, approve, recheck and execute. |
| Diagnostics | application.diagnostics | Structured results, bounded probes and safe cleanup. |
| Cancel active operation | operation.cancel | Target by operation ID. |
| History inspect/filter | history.query | Session events; filtering does not modify project data. |
| Approve/deny reviewed action | trusted approval resolver | Not an unrestricted externally callable approval bypass. |

Presentation-only interactions stay local: window opening/closing, focus, tab
selection, scrolling, tree expansion, review navigation, copy-to-clipboard, and
file dialogs. Local unsaved-buffer undo/redo and read-only toggles remain editor
state. Any later project read/write they trigger still goes through the action API.

The linked `&` control composes existing actions. It must not introduce a second
validation engine or alternate write path. Project linked actions still reach the
approval boundary; single-file linked actions still stop at the unsaved result.

## 8. State and snapshot correctness

- Maintain a project generation that changes on root transitions, even when
  returning to a previously visited root.
- Track source-tree, capture selection, exclusion policy, and capture-option revisions.
- Bind scans, previews, approvals and snapshots to relevant generations/revisions.
- Remove duplicated mutable fields from the UI. Transitional properties may delegate
  to the model, but must not become second sources of truth.
- Track dirty paths with their actual project scope; saving outside the selected
  root must not incorrectly certify or invalidate an unrelated project.
- Do not rely solely on maximum modification time: additions, deletions, same-time
  rewrites, and changed inclusion rules must be accounted for.
- Use current content fingerprints for destructive writes and compiled source data.
  Metadata caches are performance hints, not authorization to overwrite.
- Discover existing snapshots through a service and validate root/configuration and
  source information before making them exportable.
- Failed/cancelled capture never publishes an incomplete snapshot as current.
- Selection changes or file edits during capture prevent accepting that result as
  the current state, even if the historical capture itself completed successfully.

## 9. Performance and tree behavior

- Record baseline timings, filesystem work counts, visible widget counts, and
  cancellation response using generated fixtures outside the repository.
- Benchmark a small project and a reproducible large fixture (initial target:
  10,000 files with nested folders and exclusion matches).
- Use in-memory metadata keyed by root/generation and policy revision. Reuse stable
  derived values but re-enumerate as needed to discover additions and removals.
- Avoid assuming a parent directory mtime proves descendant file contents unchanged.
- Explicit rescan must discover filesystem changes. Provide a full verification path
  and fall back to it whenever cache validity is uncertain.
- Keep a complete logical capture model while lazily inserting Tk tree rows.
- Store selection inheritance by path/model; collapsing or never expanding a folder
  cannot change which descendants are captured.
- Preserve expanded paths, focus/selection, and scroll anchor where those paths remain.
- Batch Tk insertions and coalesce progress events to keep event processing responsive.
- Preserve current visible-file size semantics; document that excluded descendants
  are not counted in the displayed included-tree totals.
- Handle inaccessible folders and linked paths explicitly, including Windows junctions
  and cycles; show skipped reasons instead of silently following paths outside scope.

Initial acceptance targets on the recorded test machine: zero content reads during
a metadata-only scan; no eager descendant widget creation for collapsed folders;
no repeated recursive size traversal; cancellation acknowledged within one second
between ordinary filesystem calls; warmed refresh/render median no worse than the
baseline, with at least a 30% improvement in an identified affected workload. Record
measurements and limitations; revisit a target explicitly if evidence shows it is
unsuitable rather than quietly marking it passed.

## 10. Project patch review design

- File list: relative path, validation status, addition/deletion count, hunk count.
- Selected file views: original source, diff preview, full resulting text.
- Previous/next changed-file and previous/next hunk navigation with visible position.
- Highlight additions, removals and headers using shared dark-theme tokens.
- Show no-op files, empty results, final-newline changes and validation errors clearly.
- Keep JSON authoring and Add File; templates should not require users to retain an
  invalid example hash or nonexistent example file.
- Collect per-file validation results where safe so the user can fix all reported
  problems, while blocking Apply until the entire submitted manifest is valid.
- Bind rendered previews and approval to the exact immutable plan.
- Editing the manifest, indentation options, target root, or source invalidates it.
- Keep application all-or-nothing within the stated rollback limitations. Do not add
  per-hunk partial application in this pass. A rejected change is edited out of the
  manifest and the complete new manifest is revalidated.
- Minimum-size and keyboard checks must include all toolbar, status, approval and
  linked-action controls; long paths must not push controls out of view.

## 11. Backup and recovery design

- Use a reserved managed location, proposed `_projectmapper/backups/`, for scoped
  project backups, with unique operation/generation identifiers.
- For explicitly chosen standalone targets, define and display an explicit backup
  scope; do not guess an unrelated project's backup directory.
- Record relative target, original bytes/hash, source identity, supported mode,
  operation ID, creation time, and backup format version.
- Preserve existing backups; never overwrite an earlier generation or silently adopt
  arbitrary user `.bak` files as app-owned records.
- Validate backup integrity before presenting restoration as available.
- Restore preview compares current bytes with the selected generation. Approval binds
  to those current bytes and that backup; changed inputs require a new review.
- Preserve the pre-restore content as a new recovery generation before replacing it.
- Retention starts as an explicit preview/cleanup action with a keep-latest-N option.
  No automatic destructive pruning by default.
- Prune only verified app-owned records within the managed directory, never a generic
  `*.bak` glob. Protect records needed by unresolved recovery.
- Keep backup data excluded from snapshots, project-patch targeting, and vendor exports
  so recovery storage is not accidentally transformed or redistributed.
- Backup-disabled operation continues to work. Requested backup failure stops the
  intended mutation and produces a clear result.

## 12. Operation history and errors

- Add a compact dark-theme history view backed by the event stream, not independently
  assembled status strings in each tool.
- Show time, operation ID, action, origin, target/count, status, duration, and summary.
- Filters: action category, outcome, and path text. Details show affected files,
  validation issues, backup references and recovery outcomes.
- Group progress under its operation rather than inserting an unbounded row per update.
- Use a bounded session store; persistent history is deferred.
- Standardize errors through shared codes and human-readable messages. Keep useful
  diagnostic traces available without showing raw internals in routine user flows.
- External edits while an editor buffer is open mark that buffer stale without
  discarding unsaved work. Operation events trigger this behavior consistently.
- Listener or GUI callback exceptions are reported; do not swallow them silently.

## 13. Implementation phases and stop gates

### Phase 0 — Inventory, baseline and safety regressions

- [x] Audit all UI callbacks and complete the action matrix.
- [x] Record current tests, startup modes, vendor packaging and minimum-window behavior.
- [x] Diagnose permissions and move fixtures to per-run isolated temporary roots.
- [x] Ensure cleanup is registered before setup can fail; destroy Tk windows/timers
      and close SQLite/file handles deterministically.
- [x] Reproduce stale-snapshot, root-generation, capture-selection, approval and
      pre-replacement rollback issues with focused tests.
- [x] Fix confirmed defects before building on those paths.

Gate: a documented baseline, failures with established causes, and no known
data-loss regression left in the paths being extended.

### Phase 1 — Action API and observer foundation

- [x] Define contracts, error codes, action registry and state view.
- [x] Implement controller, dispatcher, operation IDs and lifecycle transitions.
- [x] Add scheduling, per-operation cancellation, duplicate request handling and events.
- [x] Implement trusted approval preparation/resolution and freshness rechecks.
- [x] Add a headless test client and two simultaneous event subscribers.
- [x] Migrate representative read, scan, and guarded write operations end to end.

Gate: these operations work without Tk, subscribers observe consistent outcomes,
and denied/stale approvals cannot write.

### Phase 2 — Service extraction and complete desktop migration

- [x] Extract exclusions, snapshot schema/capture, projections and vendor export.
- [x] Unify state, revisions and root generation; remove redundant UI state ownership.
- [x] Route all matrix actions through the seam, including capture options/selection.
- [x] Convert windows to adapters; bridge worker events onto the Tk thread.
- [x] Preserve compatibility imports temporarily where existing callers require them.
- [x] Remove unused duplicate helpers and verify direct-script/package startup.

Gate: inventory has no unexplained bypasses, core imports do not load Tk, and all
existing workflows pass regression checks through the dispatcher.

### Phase 3 — Tree performance

- [ ] Establish measured benchmark baselines and correctness fixtures.
- [ ] Implement safe metadata reuse and lazy widget population.
- [ ] Preserve model-based selection, navigation and scroll state.
- [ ] Verify changes, exclusions, inaccessible directories, links and cancellation.
- [ ] Record baseline versus final work counts and timings.

Gate: performance targets in section 9 are met or an explicit evidence-backed
adjustment is reviewed; logical scan/capture results remain equivalent.

### Phase 4 — Patch review

- [ ] Implement file review list, shared view components and hunk navigation.
- [ ] Improve manifest initialization/Add File and per-file validation feedback.
- [ ] Connect linked controls and approval to immutable validated plans.
- [ ] Test stale edits, empty replacements, no-ops and multi-file failures.
- [ ] Verify minimum-size layout, keyboard navigation and dark theme.

Gate: users can inspect every file/hunk and apply only the exact current approved plan.

### Phase 5 — Backup generations, restore and retention

- [ ] Define managed storage format, ownership and scope.
- [ ] Create unique generations through shared write services.
- [ ] Add list/preview/restore and approval-bound retention actions.
- [ ] Add UI controls using the same action seam.
- [ ] Verify collisions, corruption, external edits, restore failure and recovery protection.

Gate: restoration is verified, retention only touches approved app-owned records,
and failure never silently consumes the recovery material.

### Phase 6 — History and operational clarity

- [ ] Add bounded event-backed history and filters/detail view.
- [ ] Connect validation, apply, restore, rollback, capture and export events.
- [ ] Standardize error display and surface observer/callback failures.
- [ ] Verify two clients see the same operation and state transitions.

Gate: history explains what happened and what needs attention without exposing
file contents or duplicating authoritative state.

### Phase 7 — Full acceptance and documentation

- [ ] Run the complete suite with isolated fixtures and no unexplained failures.
- [ ] Run fault-injection and interleaving tests from the acceptance matrix below.
- [ ] Smoke-test every UI operation and keyboard/menu entry point.
- [ ] Test vendor export in a clean directory without `.parts/` or development files.
- [ ] Run and record performance/layout checks.
- [ ] Update end-user instructions and developer action/API guidance.
- [ ] Write final acceptance report listing evidence and any remaining limits.

Gate: every required stop condition is satisfied. A blocked check is recorded as
blocked; passing a small subset does not make the plan complete.

## 14. Acceptance matrix

| Scenario | Required evidence |
| --- | --- |
| Non-UI usage | Read, scan, selection change, validate, guarded save and export through the shared API without creating or importing Tk UI. |
| Multiple observers | Two subscribers see the same operation IDs and ordered transitions; one faulty subscriber does not fail the action. |
| Busy/duplicate requests | Conflicting operations are queued/rejected predictably; repeated request IDs do not duplicate writes. |
| Approval boundary | Deny/close, forged ordinary approval flag, reused decision and changed target all fail safely. |
| Root switching | Results from root A are rejected after A -> B -> A when their generation is obsolete. |
| Freshness | File edits, additions/deletions, capture selection, exclusions and binary options require correct recapture. |
| Existing snapshot | Startup can discover a valid compatible snapshot; incompatible/stale snapshots cannot be exported as current. |
| Single-file patch | Exact/floating matching, indentation, overlap, ambiguity, BOM, newline preservation, version collision and empty result. |
| Project patch | All files validated, stale plan refused, staging failure leaves targets untouched, only committed targets are rolled back. |
| Recovery conflict | External edit after a replacement is preserved and reported as recovery required. |
| Backup safety | Unique generations, corrupt backup refused, pre-restore recovery generation retained, unrelated `.bak` files untouched. |
| Failure injection | Read/write/chmod/replace/backup/rollback/cleanup failures produce truthful outcomes and preserve available originals. |
| Cancellation | Scan/compile cancellation does not publish incomplete state; cancellation during apply reaches safe recovery/completion. |
| Lazy tree | Selection covers unloaded descendants; collapsed widget population stays bounded; navigation survives refresh. |
| Editor synchronization | External/action-originated changes mark existing editor sessions stale without discarding unsaved buffers. |
| Diagnostics | No fixed-name overwrite, no imports from references, accurate failure reporting and owned-probe cleanup. |
| Packaging | Clean vendor app starts and runs representative actions with no `.parts/` or development runtime dependency. |

## 15. Global stop conditions

The implementation is complete only when:

1. Every application operation exposed by the UI has an explicit shared-action
   mapping; presentation-only exceptions are documented.
2. Domain rules, state and approvals run without Tk and are not duplicated in adapters.
3. Existing user workflows, schemas, theme and linked controls are preserved.
4. Stale plans, conflicting requests and denied approvals cannot mutate targets.
5. File write and recovery behavior meets the documented byte-preservation and
   failure-handling tests, with honest limits on external races and crashes.
6. Snapshot freshness is authoritative and covers capture configuration as well as files.
7. Per-file patch review, backup restore/retention, and event-backed history are usable.
8. Large-project behavior meets the recorded performance and responsiveness targets.
9. Full tests, GUI checks and standalone export checks pass with reproducible evidence.
10. `.parts/` was not written to, imported, packaged, or made required.
11. Documentation describes actual behavior and the final acceptance report records
    residual limitations. Incomplete gates are not labeled complete.

## 16. Verification record template

For each phase, record:

- Date and phase/checklist IDs.
- Files/behaviors changed and relevant decisions.
- Exact commands or GUI reproduction steps.
- Expected and observed outcomes; passed/failed/blocked status.
- Environment facts for permission failures and benchmark measurements.
- Follow-up fixes, remaining limitations and approved scope adjustments.

No implementation verification is claimed by this documentation-only update.

## 17. Decision log

External-review followthrough: reopen Phase 2; fix binary hashing and nested inherited
selection; route tool creation/reads/previews through actions; apply exactly the
displayed plan; move path safety below tools; verify the mutation lifecycle before
parking. Phase 3 must establish a complete logical tree and inherited selection
independent of rendered Tk nodes before lazy rendering. Tie snapshot captured bytes
to publication fingerprints to close the ABA gap; consider unchecked-file hashing
only after defining the required freshness semantics. Current evidence and remaining
gates are recorded in `.dev-log/02-review-followthrough.md`.

| Date | Decision | Status |
| --- | --- | --- |
| 2026-09-16 | Store development plans in `docs/`, with a short index and dated plan files. | Recorded in this documentation pass. |
| 2026-09-16 | Add a shared action seam before further UI/service extraction. | Included for review following the user's request. |
| 2026-09-16 | Keep actual CLI/MCP transports and cross-process communication out of this pass. | Proposed scope boundary from the review. |
| 2026-09-16 | Keep destructive approval enforcement below the UI and shared across callers. | Required design constraint. |
| 2026-09-16 | Retain complete-manifest project patch application; partial hunk selection is deferred. | Proposed simplification. |
| 2026-09-16 | Use bounded session history and explicit backup cleanup initially. | Proposed default; no persistent history or automatic pruning. |
| 2026-09-16 | Begin implementation after the plan review; keep CLI/MCP transports deferred. | Implemented through Phase 2; see `.dev-log/02-desktop-migration.md`. |
