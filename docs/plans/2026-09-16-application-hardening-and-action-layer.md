# ProjectMapper: application hardening and shared action layer

Date: 2026-09-16

Status: **Phases 0–3 completed and parked (Phase 3: 124 passing tests, measured
scan/render improvements; committed 2026-09-23 as `74c9b99`). Plan revised
2026-09-23 for release. Phase 4, release readiness, completed and parked
2026-09-23 with 142 passing tests on Python 3.10/3.13/3.14 and verified artifacts;
tagged `v0.4.0`; `main` pushed to GitHub 2026-09-23. Phase 5, project patch review,
completed and parked 2026-09-23 with 175 passing tests on Python 3.10/3.13/3.14.
Phase 6, backup generations, restore and retention, completed and parked 2026-09-24
with 233 passing tests on Python 3.10/3.13/3.14. Phase 7, history and
operational clarity, completed and parked 2026-09-24 with 271 passing tests on
Python 3.10/3.13/3.14. Phase 8, full acceptance, documentation and v1.0.0, completed
and parked 2026-09-25 with 335 passing tests on Python 3.10/3.13/3.14 (331 on 3.11/3.12
at step 8.4), verified release artifacts and the acceptance report
`docs/acceptance/v1.0.0.md`; tagged `v1.0.0`. With owner approval on 2026-09-25, `main`
and the tag were pushed and the GitHub release "ProjectMapper 1.0.0" published (wheel and
sdist attached; not on PyPI). Phase 9, CLI and MCP adapters, is open (entry awaiting owner
review, 2026-09-25).
Former Phases 4–7 are renumbered 5–8; Phase 9 adds CLI and MCP adapters after final
acceptance. See the decision log (section 17) and the dated `.dev-log/` journals.**

Implementation was authorized after the initial planning review. Later tranches remain
subject to their entry records, implementation/review cycles and acceptance gates.

Numbering note: journals dated before 2026-09-23 use the original numbering, in which
"Phase/Tranche 4" meant project patch review. Those references are historical.

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

The application is released publicly: an interim v0.4.0 once repository hygiene,
packaging and snapshot byte-binding are complete, and v1.0.0 at final acceptance.
After v1.0.0, a command-line client and a local stdio MCP server use the same action
layer. An agent can read, validate and propose changes but cannot approve its own
destructive operations. Approval stays with a trusted human adapter.

## 2. Current state and gap

Current as of Phase 3 acceptance (2026-09-17), revised 2026-09-23 for release scope. Historical entry observations and
repairs are retained in the dated tranche journals; they are not current defects.

| Area | Current state | Required difference |
| --- | --- | --- |
| Structure | Package `src/projectmapper/` (moved 2026-09-23, Phase 4). Tk presentation lives in `app.py` and `tree_view.py`; application services, core machinery and tools have separate modules. | Preserve these boundaries in later work. |
| Action routing | Desktop domain operations use Controller/Dispatcher; trusted approval is separate from ordinary requests. | Add later backup/history operations through the same seam. CLI/MCP adapters follow in Phase 9. |
| State | Controller owns ProjectState and LogicalTree; desktop compatibility properties delegate to them. | Preserve one authoritative owner as later views are added. |
| Scanning | Fresh metadata scans and batched lazy rendering are implemented; selection is independent of widgets. | Maintain measured performance and navigation/selection regressions. |
| Project patches | Phase 5 complete: all-files validation with per-file errors, review list, Source/Diff/Result views, hunk navigation, keyboard shortcuts, approval with per-file counts. | Keep complete-manifest application; per-hunk apply stays deferred. |
| Recovery | Phase 6 complete: managed backup generations (project store `_projectmapper/backups/`, per-user store for outside targets) with verified ownership and integrity; durable `recovery` generations on rollback conflict with truthful messages; restore via preview, approval and a `pre-restore` copy; approval-bound keep-N clean-up; a Backups window. The three entry defects (failing repeat saves, `.bak` blocking apply, lost recovery material) are fixed. | Resolved in Phase 8 (decision E2): the text editor's **Keep backup** covers Save and Save As overwrites. |
| History | Phase 7 complete:<br>- a per-operation, bounded (500), content-free session history with coalesced progress (`history.query`) and a History window<br>- listener, Tk callback, GUI-queue and worker failures surfaced as log line plus internal record<br>- one error-wording catalogue (18 codes)<br>- main log bounded to 2,000 lines<br>All four entry findings are fixed. | History stays session-only (persistence deferred by plan). |
| Main window layout | Phase 8 step 8.2: the action area has four short rows instead of two long ones; the tree's name column stretches; the status bar can no longer be squeezed out. The minimum size is the measured requested width × 560 px (647×560 at Tk scaling 1.33 on the Windows test machine). A test shows every button, checkbox and entry fully visible and unclipped at that size, at least 4 tree rows and 3 log lines. | None known; other scalings and platforms are unmeasured. |
| Testing | Phase 8 final: 335 tests pass on Python 3.10, 3.13 and 3.14 (exit codes captured; 331 on 3.11/3.12 at step 8.4); benchmark and layout probe recorded. Step 8.3: the suite runs with `--capture=sys` (`pytest.ini`, decision E4). This removes the intermittent Tk start-up failure: it came from pytest's default fd-level capture, not from the app. Unused imports are removed across `src/`, `tests/` and `tools/`. Two names are kept in `tools/text_toucher.py` as re-exports that a test imports; they are listed in `__all__`. pyflakes now reports only the star-import notices of the `import *` sections in `app.py`, `core/exports.py`, `core/snapshots.py` and `core/helpers.py`. Phase 7 acceptance: 271 regressions, plus two explicit benchmarks and a measured minimum-size layout probe. Development dependencies are declared in `pyproject.toml` (`.[dev]`). | Whole-application acceptance in Phase 8; coverage for Phase 9. |
| Snapshot freshness | Closed in Phase 4 (step 4.3). Previously the signature pass and the capture read were separate. A post-capture re-signature caught persistent changes, but A (signature) → B (captured) → A (recheck) published B as fresh. Captured text and blobs now come from the bytes whose digest is checked against the signature pass; a mismatch raises `source_changed`. | Keep the byte-binding regressions green. |
| Repository/release | Phase 4 complete (`v0.4.0` tagged and pushed 2026-09-23). Phase 8 step 8.4: version 1.0.0; CHANGELOG 1.0.0 section; classifiers per E3 (Windows; Python 3.10–3.14, each with a passing suite); README platform statement; `docs/developer-guide.md`. Wheel and sdist built in isolation and inspected. Fresh 3.10/3.14 installs, a GUI launch and a vendor export were verified in clean locations. macOS/Linux launch untested. | Tag `v1.0.0` at 8.5; GitHub release/PyPI only with owner approval; cross-platform CI post-1.0 (`docs/TODO.md`). |
| Transports | Action layer is transport-ready; no CLI or MCP adapter exists by decision. | Phase 9: CLI and stdio MCP adapters over public actions only. |
| Acceptance evidence | Phase 8 complete: `docs/acceptance/v1.0.0.md` records every section 15 condition 1–13 and every section 14 row for 1.0 with evidence (G1–G6 closed; every UI entry point driven by a test; E4 explained and eliminated from the suite; defects D1–D5 fixed). Recorded, not explained: one silent 3.10 run (Tranche 6), one baseline-copy layout failure (Tranche 7). | Phase 9 acceptance; deferred items in `docs/TODO.md`. |

### Historical baseline issues — resolved, retained for context only

The following list records the original entry concerns, not outstanding work.
Acceptance evidence is in `.dev-log/00-baseline-and-safety.md`,
`.dev-log/02-review-followthrough.md`, and `.dev-log/03-logical-tree-and-rendering.md`.

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
11. Release readiness: repository hygiene, standard packaging, snapshot byte-binding,
    changelog, and versioned releases (v0.4.0 interim, v1.0.0 at final acceptance).
12. After v1.0.0 acceptance: a CLI client and a local stdio MCP server over the public
    action layer, with approval held by a trusted human adapter.

### Deferred

- Attaching a CLI/MCP process to an already-running desktop instance (shared live
  state across processes). Each Phase 9 process hosts its own Controller.
- Network listeners, remote transports, remote authentication, and cross-process coordination.
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
  UI modules, or `projectmapper.app`.
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
Since Phase 4 the `src/` paths below are under the package directory `src/projectmapper/`.

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

The table below is the historical proposal and includes future operations; it is
not the implemented API contract. The completed desktop audit and actual action
names are in [the verified action inventory](../action-inventory.md). Use that
inventory for current integrations; retain this table only as planning context.

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

## 12A. Release readiness design

Added 2026-09-23. Sections 12A/12B are inserted rather than renumbered so existing
section references remain valid.

### Repository hygiene

- Record the `.parts/` removal already present in the working tree. The runtime never
  required the directory; its read-only/no-write protections stay in force if it reappears.
- Untrack `manual-fixture/x.txt` without deleting it locally (it is already ignored
  residue). Remove the Node `package-lock.json`, which has no role in this project.
- Runtime dependencies: none beyond the Python standard library with Tkinter. Remove
  the PyPI `tk` requirement. Declare development dependencies (pytest) explicitly and
  run the suite inside the project environment, not only a system interpreter.
- Correct stale launcher text. Do not delete or repermission legacy `tests/tmp*` fixtures.

### Packaging

- Proposed layout: move the package from `src/` (top-level import name `src`) to
  `src/projectmapper/`, the standard src-layout. An installed distribution must not
  publish a top-level package named `src`. Confirm or revise this at tranche entry
  with an evidence-backed decision before moving files.
- `pyproject.toml` (PEP 621) with a single version source, a `projectmapper` GUI
  entry point, `python -m projectmapper`, and a dev dependency group. Establish the
  minimum Python version from the code's actual syntax rather than assuming it.
- `setup_env.bat`/`run.bat` keep working for Windows users, using an editable install.
- Vendor export, diagnostics import checks and startup smoke tests follow the new
  layout. The vendor package still excludes `.parts/`, `.dev-log/`, caches and
  generated state.
- Build a wheel/sdist and verify installation and startup in a fresh virtual
  environment outside the repository.

### Snapshot byte-binding (ABA)

- Correction (4.3): a compile already re-ran the signature after capture, so a
  persistent A→B change was refused. The gap was A→B→A across the capture read.
- The capture read of each captured file computes its digest from the exact bytes
  stored (text or blob) and compares it with that file's digest from the signature
  pass. On mismatch, refuse publication with `source_changed`. Discard the scratch
  database, keep the prior published snapshot, and require a new compile.
- Unselected files keep their current signature treatment. Freshness semantics for
  unchecked files do not change without a separately recorded decision.
- Keep the signature algorithm unchanged, so an unchanged project's existing
  snapshots still verify. Bump the snapshot schema version only if stored structure changes.
- Regression: inject a change between the signature and capture passes. Prove that
  A→B is refused, and that A→B→A never yields a published snapshot containing B.

### Release artifacts and publication

- Single version source; `CHANGELOG.md`; README install/quick start and a statement
  of purpose; refreshed screenshot if the UI has changed.
- A fresh vendor export and a wheel installation each verified in clean directories.
- Tag `v0.4.0` locally at acceptance. Pushing, publishing a GitHub release, or
  uploading to a package index are outward-facing and each requires explicit owner
  approval at that time.

## 12B. CLI and MCP adapter design (Phase 9)

- Both are thin adapters. Each process composes its own Controller/Dispatcher and
  submits only public named actions. No domain rules move into an adapter.
- The trusted approval resolver is never exposed as a CLI flag, MCP tool, or payload
  field. Approval-required actions (delete, project apply, Save As overwrite, backup
  restore/prune) are resolved only by a trusted human adapter in that process, such as
  a blocking local confirmation dialog. Without one, they return `approval_required`
  and do not write. An agent-controlled channel, including non-TTY standard input,
  is never treated as a human approver.
- CLI: scan, inspect, compile, export, and patch/project-patch validation with
  structured JSON output and stable exit codes. Its write behavior follows the same
  approval rule.
- MCP: a local stdio server exposing tools with JSON schemas derived from action
  contracts, and resources for the project tree and snapshot projections. No network
  listener. Tool results carry bounded content; the event history remains content-free.
- Dependency decision at entry: a minimal standard-library JSON-RPC/stdio
  implementation or the official MCP SDK as an optional extra. The runtime GUI must
  remain free of third-party dependencies either way.
- Documentation: agent integration guide, including example client configuration and
  the approval model.

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

- [x] Establish measured benchmark baselines and correctness fixtures.
- [x] Implement safe metadata reuse and lazy widget population.
- [x] Preserve model-based selection, navigation and scroll state.
- [x] Verify changes, exclusions, inaccessible directories, links and cancellation.
- [x] Record baseline versus final work counts and timings.

Accepted 2026-09-17: 124 regression tests passed. On Windows 10/Python 3.13.6,
the 10,000-file nested fixture's scan median fell from 10.676s to 1.220s;
initial render median fell from 0.794s to 0.015s (10,201 to 201 widgets).
All 10,000 direct children render in batches, with a measured maximum heartbeat
gap of 58ms. No cross-scan metadata cache: each explicit rescan enumerates fresh
metadata, keeping change discovery straightforward. Selection for absent paths is
forgotten; newly discovered paths inherit retained ancestors. Detailed evidence,
commands and limits are in `.dev-log/03-logical-tree-and-rendering.md`.

Gate: performance targets in section 9 are met or an explicit evidence-backed
adjustment is reviewed; logical scan/capture results remain equivalent.

### Phase 4 — Release readiness and v0.4.0

Design: section 12A. Inserted 2026-09-23; later phases renumbered.

- [x] Repository hygiene: `.parts/` removal recorded, residue untracked/removed,
      corrected runtime and development dependencies, launcher text fixed.
- [x] Packaging: layout decision recorded; src-layout package, pyproject, entry point
      and version source; launchers, vendor export, diagnostics and tests updated.
- [x] Snapshot byte-binding with A→B and A→B→A regressions.
- [x] Changelog, README install/quick start, version 0.4.0.
- [x] Full suite in the project environment, benchmark, both launch modes, fresh wheel
      install and fresh vendor export in clean directories.
- [x] Local `v0.4.0` tag. Publication only with explicit owner approval (owner pushed `main` 2026-09-23).

Accepted 2026-09-23: 142 regression tests passed on Python 3.14.2 (`.venv`), 3.13.6 and
3.10.6. Wheel and sdist were built without warnings. Fresh wheel installs on 3.10 and
3.14 passed scan/compile/export and GUI launch. A fresh vendor export passed
`setup_env.bat`, `run.bat`, GUI launch and `pip install` in a clean directory. Snapshot
A→B→A publication was reproduced on the old compiler and is now refused. The
benchmark matches Tranche 3. Evidence and residual limits are in
`.dev-log/04-release-readiness.md`.

Gate: clean repository; installable package with no top-level `src` import; ABA gap
closed by regression evidence; all existing behavior and tests preserved; release
artifacts verified in clean locations. No outward publication without approval.

### Phase 5 — Patch review

- [x] Implement file review list, shared view components and hunk navigation.
- [x] Improve manifest initialization/Add File and per-file validation feedback.
- [x] Connect linked controls and approval to immutable validated plans.
- [x] Test stale edits, empty replacements, no-ops and multi-file failures.
- [x] Verify minimum-size layout, keyboard navigation and dark theme.

Gate: users can inspect every file/hunk and apply only the exact current approved plan.

Accepted 2026-09-23: 175 regression tests passed on Python 3.14.2, 3.13.6 and 3.10.6.
- **Validation:** every file is validated together; errors name file and hunk; a
  plan is issued only for a fully valid manifest.
- **Review:** per-file list, Source/Diff/Result views with highlighted diffs, and
  keyboard hunk/file navigation.
- **Layout:** a measured minimum-size check shows 0 problems in both patcher windows;
  screenshots were inspected on screen, and theme defects found there were fixed.
- **Unchanged:** all pre-existing apply, approval and rollback tests pass unchanged.

Evidence and residual limits are in `.dev-log/05-project-patch-review.md`.

### Phase 6 — Backup generations, restore and retention

- [x] Define managed storage format, ownership and scope.
- [x] Create unique generations through shared write services.
- [x] Add list/preview/restore and approval-bound retention actions.
- [x] Add UI controls using the same action seam.
- [x] Verify collisions, corruption, external edits, restore failure and recovery protection.

Gate: restoration is verified, retention only touches approved app-owned records,
and failure never silently consumes the recovery material.

Accepted 2026-09-24: 233 regression tests passed on Python 3.14.2, 3.13.6 and 3.10.6
(exit codes captured).
- **Entry defects fixed:** all three were reproduced before being fixed — repeated
  backed-up saves failing, an existing `.bak` blocking apply, and recovery material
  lost behind a false message.
- **Store:** managed generations in project and per-user scopes, with verified
  ownership and integrity.
- **Recovery and restore:** durable recovery generations; restore with preview,
  approval and a pre-restore copy.
- **Clean-up:** approval-bound, verified, non-recursive.
- **UI:** the Backups window was checked by measurement, keyboard traversal and an
  on-screen capture.
- **Carried forward:** the pre-existing main-window layout gap (section 2).

Evidence and residual limits are in `.dev-log/06-backup-generations.md`.

### Phase 7 — History and operational clarity

- [x] Add bounded event-backed history and filters/detail view.
- [x] Connect validation, apply, restore, rollback, capture and export events.
- [x] Standardize error display and surface observer/callback failures.
- [x] Verify two clients see the same operation and state transitions.

Gate: history explains what happened and what needs attention without exposing
file contents or duplicating authoritative state.

Accepted 2026-09-24: 271 regression tests passed on Python 3.14.2, 3.13.6 and 3.10.6
(exit codes captured).
- **History:** a per-operation, bounded, content-free session history that progress
  floods cannot evict (`history.query`).
- **Hidden failures surfaced:** listener failures, Tk callback exceptions,
  GUI-queue failures and worker crashes produce a log line plus an internal record.
- **Error wording:** one catalogue, with a test that scans the source syntax tree.
- **History window:** filters, details, a Backups link and live updates, checked by
  measurement, keyboard traversal and pixel-verified screenshots.
- **Cost:** no measurable overhead (a 3,000-file compile took 3.37s with the history
  versus 3.47s without).

Evidence and residual limits are in `.dev-log/07-history-and-clarity.md`.

### Phase 8 — Full acceptance, documentation and v1.0.0

- [x] Run the complete suite with isolated fixtures and no unexplained failures (E4; two recorded events in the report).
- [x] Run fault-injection and interleaving tests from the acceptance matrix below (G1–G6, step 8.1).
- [x] Smoke-test every UI operation and keyboard/menu entry point (step 8.2; `docs/ui-map.md`).
- [x] Test vendor export in a clean directory without `.parts/` or development files (steps 8.4, 8.5).
- [x] Run and record performance/layout checks (benchmark and 8-window layout probe, step 8.5).
- [x] Update end-user instructions and developer action/API guidance (README, `docs/developer-guide.md`).
- [x] Write final acceptance report listing evidence and any remaining limits (`docs/acceptance/v1.0.0.md`).

- [x] Update version, changelog and install documentation; verify wheel and vendor
      export in clean directories; tag `v1.0.0` locally. Publication requires
      explicit owner approval (not published).

Gate: every required stop condition for Phases 0–8 is satisfied. A blocked check is
recorded as blocked; passing a small subset does not make the plan complete.

### Phase 9 — CLI and MCP adapters

Design: section 12B. Opens only after Phase 8 is accepted.

- [ ] Entry decision: MCP implementation dependency and process/approval composition
      (entry record 2026-09-25: decisions F0–F6 pending; findings: actions are not
      confined to the project root, several writes need no approval in the core, and
      MCP revision 2026-07-28 removed the `initialize` handshake).
- [ ] CLI over public actions with JSON output, exit codes and approval rule.
- [ ] Local stdio MCP server: tools, resources, bounded results and schemas.
- [ ] Trusted approval adapter; prove agents cannot approve, forge or reuse decisions.
- [ ] Protocol conformance, denial/stale-plan, payload-bound and content-free-history tests.
- [ ] Agent integration guide; changelog; release as a minor version with owner approval.

Gate: an agent client can scan, read, compile, export and validate/propose patches
through MCP; every approval-required action either receives a trusted human decision
or makes no write; the desktop and tests remain green.

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
| Installation | A built wheel installs into a fresh environment outside the repository; `projectmapper` and `python -m projectmapper` start; no top-level `src` package is installed. |
| Snapshot byte-binding | A change injected between the signature and capture passes refuses publication; A→B→A never publishes B; the prior snapshot survives. |
| CLI/MCP (Phase 9) | Agent clients use only public actions; approval-required actions make no write without a trusted human decision; forged/reused approval and non-TTY input cannot approve; history carries no file contents. |

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
12. Snapshot publication is bound to the bytes actually captured.
13. The application installs and starts as a standard package; release artifacts are
    verified in clean locations; v0.4.0 and v1.0.0 are tagged at their gates, and
    anything published had explicit owner approval.
14. Phase 9: CLI and MCP adapters meet the section 12B approval rule and their gate.
    Conditions 1–13 define v1.0.0 and do not depend on Phase 9.

## 16. Verification record template

For each phase, record:

- Date and phase/checklist IDs.
- Files/behaviors changed and relevant decisions.
- Exact commands or GUI reproduction steps.
- Expected and observed outcomes; passed/failed/blocked status.
- Environment facts for permission failures and benchmark measurements.
- Follow-up fixes, remaining limitations and approved scope adjustments.

This template does not itself establish verification. Completed-phase evidence is
recorded in the acceptance journals linked above.

## 17. Decision log

Historical external-review direction (completed through Phase 3): reopen Phase 2; fix binary hashing and nested inherited
selection; route tool creation/reads/previews through actions; apply exactly the
displayed plan; move path safety below tools; verify the mutation lifecycle before
parking. Phase 3 must establish a complete logical tree and inherited selection
independent of rendered Tk nodes before lazy rendering. Outstanding: tie snapshot captured bytes
to publication fingerprints to close the ABA gap; consider unchecked-file hashing
only after defining the required freshness semantics. Current evidence and remaining
gates are recorded in `.dev-log/02-review-followthrough.md` and
`.dev-log/03-logical-tree-and-rendering.md`.

| Date | Decision | Status |
| --- | --- | --- |
| 2026-09-16 | Store development plans in `docs/`, with a short index and dated plan files. | Recorded in this documentation pass. |
| 2026-09-16 | Add a shared action seam before further UI/service extraction. | Implemented and accepted in Phases 1–2. |
| 2026-09-16 | Keep actual CLI/MCP transports and cross-process communication out of this pass. | Superseded 2026-09-23 for CLI/MCP (Phase 9); cross-process attachment remains deferred. |
| 2026-09-16 | Keep destructive approval enforcement below the UI and shared across callers. | Required design constraint. |
| 2026-09-16 | Retain complete-manifest project patch application; partial hunk selection is deferred. | Proposed simplification. |
| 2026-09-16 | Use bounded session history and explicit backup cleanup initially. | Proposed default; no persistent history or automatic pruning. |
| 2026-09-16 | Begin implementation after the plan review; keep CLI/MCP transports deferred. | Implemented through Phase 3. Corrected Phase 2 acceptance: `.dev-log/02-review-followthrough.md`; Phase 3: `.dev-log/03-logical-tree-and-rendering.md`. |
| 2026-09-23 | Revive the project for public release. Commit the parked Tranche 3 after re-verification (124 passed; benchmarks 2 passed). | Committed `74c9b99`. |
| 2026-09-23 | Insert Phase 4, release readiness (hygiene, packaging, snapshot byte-binding, v0.4.0), ahead of patch review; renumber former Phases 4–7 to 5–8. Tag v1.0.0 at Phase 8. | Owner decision. Pre-2026-09-23 journals keep the old numbering. |
| 2026-09-23 | Bring CLI and local stdio MCP adapters into this plan as Phase 9, after v1.0.0 acceptance. Each process hosts its own Controller; the trusted approval resolver is never exposed to agents. | Owner decision; supersedes the transport deferral. |
| 2026-09-23 | Record the working-tree removal of the disposable `.parts/_MonacoVIEWER.py` in Phase 4. `.parts/` protections remain. | Owner decision. |
| 2026-09-23 | Move the package to `src/projectmapper/` so an installed distribution does not publish a top-level `src` package. | Confirmed and implemented in Tranche 4 step 4.2; see `.dev-log/04-release-readiness.md`. |
| 2026-09-23 | Outward-facing publication (push, GitHub release, package index) needs explicit owner approval each time. Local tags are part of the gates. | Required constraint. |
| 2026-09-23 | Startup root is the optional command-line folder argument, otherwise the current working directory. It no longer defaults to the application's own source folder, which would be `site-packages` for an installed copy. Vendor export is available only from a source checkout. | Implemented in Tranche 4 step 4.2. |
| 2026-09-23 | Phase 5 design: validate every file together; navigate by diff hunks (3-line context groups), not manifest hunks; review panel beside the manifest; keyboard Alt+↑/↓, F8/Shift+F8, Ctrl+Enter; shared view components; empty starting manifest; per-file counts in approval. | Owner-approved entry; implemented and accepted in Tranche 5. |
| 2026-09-23 | `project_patch.validate` returns the full review. An invalid manifest is a **succeeded** action with `valid: false`, `errors` and per-file outcomes, and no `plan_id`; manifest-level errors (JSON, duplicates, unsafe or missing paths) still fail the action. Validation succeeded, and callers (desktop, future MCP) need the per-file data. | Implemented in Tranche 5 step 5.1; contract recorded in `docs/action-inventory.md`. |
| 2026-09-23 | Correction to the approved design text: Copy Schema previously returned an empty skeleton while the window pre-filled the full example (the cause of the Add File defect). Now the window starts empty and Copy Schema returns the full example; Add File drops an untouched example and uses a unique-line template. | Implemented in Tranche 5 step 5.3. |
| 2026-09-23 | Presentation: Keep .bak backups moves beside Apply (it was clipped at minimum size); disabled action buttons are greyed; editor scrollbars use a dark style. This reverses the 5.2 removal of an unused scrollbar style, which had been intended for these panes but never wired. | Implemented in Tranche 5 step 5.4; verified by measurement and on-screen capture. |
| 2026-09-24 | Phase 6 design: managed backup generations (manifest written last as commit marker; ownership = managed location + valid manifest + verified blobs); kinds `backup`, `pre-restore`, `recovery`; durable recovery generation on every rollback conflict with a message naming it; restore via preview and trusted approval; explicit keep-latest-N clean-up only, excluding recovery generations by default; `_projectmapper/` refused as a project-patch target. | Owner-approved entry (`.dev-log/06-backup-generations.md`). |
| 2026-09-24 | Decision A: sibling `<file>.bak` backups are replaced by managed generations; existing `.bak` files are never touched or adopted. | Owner decision. Supersedes the `.bak` behavior described in the README. |
| 2026-09-24 | Decision B: targets outside the mapper root back up to a per-user store (`%LOCALAPPDATA%\ProjectMapper\backups` on Windows; platform equivalents elsewhere; `PROJECTMAPPER_USER_BACKUPS` override), shown as a separate scope. Project targets use `<root>/_projectmapper/backups/`. | Owner decision; supersedes the proposed "disable outside root". |
| 2026-09-24 | Write engines stay store-agnostic: `PatchSession.save` and `ProjectPatchSession.apply_all` take `backup`/`recover` callables; the controller binds them to scoped stores. `_projectmapper` is refused as a project-patch target on the **absolute** path, so a patch root inside the output folder cannot reach the store. Accepted trade-off: a project that genuinely lives under a folder named `_projectmapper` cannot be project-patched. | Implemented in Tranche 6 step 6.2. |
| 2026-09-24 | Restore and retention rules:<br>- Restore plans are single-use and bound to generation, files, backup sha256 and current sha256; a partial restore is `recovery_required` and names the pre-restore generation.<br>- Keep-latest-N counts `backup` and `pre-restore` generations. `recovery` generations are removable only by explicit id. `incomplete`/`corrupt` directories are never eligible, since they may be unfinished or not ours.<br>- Removal re-verifies the manifest fingerprint, unlinks the manifest first and then only the recorded blobs, and removes the directory only if nothing else is in it. No recursive delete, because older Python `rmtree` may follow junctions.<br>- Restore refuses targets inside `_projectmapper/`. | Implemented in Tranche 6 step 6.3. |
| 2026-09-24 | Backups window: a single instance opened from the main window. Clean Up applies keep-N to the chosen store; **Delete Selected** (the explicit-id path) is the only UI route that removes a recovery generation. Incomplete or corrupt generations are shown but never actionable. | Implemented in Tranche 6 step 6.4. |
| 2026-09-24 | Found at 6.4 and **carried forward, not fixed**: the main window has no minimum size and its button/control rows do not wrap. Measured at the pre-6.4 commit, Open Output Folder, Exclusions and Rescan are already clipped at 1024×700 (more at 900×650). The new Backups… button adds one clipped control, at 900×650 only. | Main-window layout goes to the Phase 8 layout checks; tracked in section 2. |
| 2026-09-24 | Phase 7 design:<br>- A per-operation `OperationHistory` subscriber, owned by the controller: progress coalesced, 500 operations, finished ones evicted first, content-free.<br>- A read-only `history.query` action. The history does not record its own queries.<br>- Hidden failures surfaced as a log line plus an `internal` history record.<br>- One error-wording catalogue; codes unchanged.<br>- Main log bounded, progress not logged per line.<br>- A History window. | Owner-approved entry (`.dev-log/07-history-and-clarity.md`). |
| 2026-09-24 | Decision C: History opens from a "History…" button in the log panel header; the main button row is untouched and its layout fix stays in Phase 8. Decision D: hidden failures produce a concise log line and a history record only — no pop-ups, no status-bar badge. | Owner decisions. |
| 2026-09-24 | Failure classes in background tasks: a `PatchError` (a routine action failure, already a failed operation in History) is one concise log line with no traceback; any other exception is an `internal.worker` problem record holding the traceback. Dispatcher `on_observer_error` hook, Tk-wide `report_callback_exception` and GUI-queue failures also record `internal` problems. History-listener and announcer failures are swallowed deliberately: recording them could loop back into the same failing listener. | Implemented in Tranche 7 step 7.2. |
| 2026-09-24 | Error wording:<br>- One catalogue, `application/errors.py`, with 18 codes and labels, enforced by a syntax-tree scan of the source.<br>- The desktop shows "Label: detail".<br>- **Contract refinement, deliberate:** an unexpected `ValueError` from a handler maps to `invalid_input` instead of `action_failed`. Engine rejections (`PatchError`, JSON and Unicode errors) are input problems, and "Operation failed: Invalid project patch JSON" misled.<br>- Trade-off: a genuine programming `ValueError` would also read as "Invalid request", but its message is still shown and history keeps it.<br>- No code was added or removed. Code expressions stay inline so the scan can see them. | Implemented in Tranche 7 step 7.3. |
| 2026-09-24 | Event addition: `accepted` events carry a whitelisted target summary (`path`, `root`, `folder`, `generation`, `scope`; strings ≤4,096 characters). Failed operations previously had no target in History, because only success payloads named paths. Content-bearing fields (text, manifest, patch) are excluded by construction. The History window reads through `history.query`, updates live through `OperationHistory.subscribe` debounced to 250 ms, and unsubscribes on close or destroy. | Implemented in Tranche 7 step 7.4. |
| 2026-09-24 | Phase 8 scope: close acceptance-evidence gaps G1–G6 with tests; map every UI operation and entry point to a check; fix the main-window layout with a measured minimum-size test; clear pyflakes warnings; release preparation; a tracked acceptance report at `docs/acceptance/v1.0.0.md`. | Owner-approved entry (`.dev-log/08-acceptance-and-v1.md`). |
| 2026-09-24 | Decisions:<br>- **E2:** the text editor gains a backup option for 1.0.<br>- **E3:** 1.0 states Windows as the tested platform, with macOS/Linux expected to work but untested; classifiers match; cross-platform CI is the first post-1.0 item.<br>- **E4:** the intermittent Tk start-up read failure must be **explained or eliminated before v1.0.0**; a recorded rate alone is not acceptance. | Owner decisions. |
| 2026-09-24 | Defects found by the G1–G6 evidence tests:<br>- **D1:** `snapshot.require` never checked `snapshot_schema_version`, so a foreign-format snapshot exported as current. It now refuses any version other than `SNAPSHOT_SCHEMA_VERSION` (`stale_snapshot`) and reports missing or unreadable snapshots as such.<br>- **D2:** scratch-file cleanup in `finally`/`except` blocks could raise over the primary error. A shared `core.writes.discard_scratch` never raises, and all five sites use it.<br>- Accepted residual: a failed cleanup may leave a `.patch-*`/`.projectmapper-*` scratch file behind silently. | Implemented in Tranche 8 step 8.1. |
| 2026-09-25 | Main-window layout (step 8.2):<br>- The action area has four rows: snapshot and export buttons; tools (Open Output Folder and Export Vendor App on the left, Diagnostics and Backups… on the right); the three option checkboxes; selection and exclusion controls. **Open Output Folder moves** from the right end of the first row to the start of the second. No control, command, colour or linked behaviour changes.<br>- "Hide pattern:", its entry and Add now read left to right. They were packed right to left, which reversed them on screen.<br>- The tree name column shrinks to 200 px and stretches; the status bar is packed before the pane, so a short window shrinks the pane first.<br>- Minimum size = the measured requested width × 560 px (enough for the path row, several tree rows, every action row and a few log lines). Measured 647×560 at Tk scaling 1.33 on Windows. The test requires the width to be at most 800 px. | Implemented in Tranche 8 step 8.2; `tests/test_ui_smoke.py` `MainWindowLayoutTests`. |
| 2026-09-25 | Decision E2 implemented: the text editor has a **Keep backup** checkbox (off by default), used by Save and by a Save As that overwrites an existing file. **Additive contract change:** `text.save_as` accepts an optional `backup` flag. When the target exists and the overwrite is approved, its previous bytes become a `text.save_as` backup generation first, and a failed backup stops the write. A new file has nothing to back up, so the flag is ignored. The Backups window's "keep newest" box is now a themed `ttk.Spinbox` (`Review.TSpinbox`). | Implemented in Tranche 8 step 8.2. |
| 2026-09-25 | UI completeness evidence lives in the tracked `docs/ui-map.md`: every control, key binding, menu entry and close box, its shared action (or "presentation"), and a test that drives the real widget or handler. Dialogs, the OS file browser and the vendor export are patched so tests stay in their fixture. | Step 8.2; referenced by the acceptance report. |
| 2026-09-25 | **E4 resolved** (owner accepted): the intermittent Tk start-up read failure is caused by swapping the process's standard handles around Tk interpreter creation. pytest's default `--capture=fd` does this around every test. Evidence:<br>- 0 failures in 22,000 roots without a swap, against 5 in 7,000 with one, using plain Python and no project code.<br>- A minimal pytest file with no project code reproduces it.<br>- The full suite with `--capture=sys` had 0 start-up failures in 16 runs, against 17 failing runs of 20 with fd capture.<br>- It happens on Tcl 8.6.12 and 8.6.15, on Python 3.10, 3.13 and 3.14.<br>- The application never swaps OS-level standard handles (under `pythonw` it only rebinds `sys.stdout`/`sys.stderr` once), and one-root launches measured 0 in 18,000.<br>- **Decision:** `pytest.ini` sets `--capture=sys`. Recorded limit: the Tcl-internal mechanism, and whether Defender's filter takes part, are not established. External checks (another machine, a Defender exclusion, a Process Monitor trace) are optional and were not required for 1.0. | Owner decision; implemented in Tranche 8 step 8.3. |
| 2026-09-25 | Hygiene: every pyflakes unused-import warning is removed. The Phase 8 entry counted 13 (per-file runs); a whole-tree run found 41 in `src/` and `tests/`: 39 removed and 2 kept. Each was checked first for importers, `patch` targets and star-import consumers. `file_name` and `create_text_file` stay in `tools/text_toucher.py` as re-exports (`tests/test_text_toucher.py` imports them there), declared in `__all__`. Star-import notices remain by design of the existing `import *` sections. | Implemented in Tranche 8 step 8.3. |
| 2026-09-25 | Defect D3 (a test defect, found in 8.3): a smoke test delivered Return with `event_generate`, which reaches only the focused window. A late delivery reached the real error dialog on the owner's desktop and blocked the run. `tests/test_ui_smoke.py` now calls bindings through Tcl (`fire_binding`) and fails any test that would open a real message box or file dialog (`guard_modals`). | Fixed in Tranche 8 step 8.3. |
| 2026-09-25 | Deferred work is tracked in `docs/TODO.md`: cross-platform CI (E3); the Tcl-internal mechanism and Defender involvement behind E4, with a self-contained reproducer and investigation steps; the two recorded test-environment events; the star-import notices. | Owner request ("note to investigate as a TODO"). |
| 2026-09-25 | Release preparation (step 8.4): `APP_VERSION` 1.0.0. Classifiers follow E3: `Operating System :: Microsoft :: Windows`; the X11 environment classifier is removed because macOS/Linux are untested; Python 3.10–3.14 are listed because the suite passed on each (3.11.9 and 3.12.10 were run for this); `Development Status :: 5 - Production/Stable`. Developer contract documented in `docs/developer-guide.md`, with its headless example and approval rules executed against the code. | Implemented in Tranche 8 step 8.4. |
| 2026-09-25 | **Defect D4 found while documenting (decision pending):** when a file changes between a project-patch preview and its apply, the apply is correctly refused and nothing is written. But the refusal is a `PatchError` (a `ValueError`), which the dispatcher reports as `invalid_input` ("Invalid request: Project patch stopped: Source changed after validation: a.py"). Single-file saves report the same situation as `source_changed`. Related: path-safety refusals (`PathSafetyError`, linked paths, `.parts`) also report `invalid_input`, not `unsafe_path`. `docs/developer-guide.md` describes the current behaviour. | Owner decision: fix (2026-09-25); see the next row. |
| 2026-09-25 | **D4 fixed** (owner: "fix D4"). **Deliberate error-code contract change for 1.0:** `core/paths.py` gains two `PathSafetyError` subclasses that name their code: `UnsafePathError` (`unsafe_path`), raised by `validate_target` for linked paths and the `.parts` folder, and `SourceChangedError` (`source_changed`), raised at the four "Source changed" sites in the project patcher. `apply_all` keeps the failure's type when it re-raises. The dispatcher reports those two codes for engine errors that carry them, and keeps its previous mapping otherwise (malformed JSON and a manifest path outside the root stay `invalid_input`). Messages are unchanged. Three regression tests (`NamedEngineCodeTests`) fail on the old code (`invalid_input`) and pass now. | Implemented in Tranche 8 step 8.4. |
| 2026-09-25 | Main-window balance (owner: "shrink the log"): the log's requested height goes from 10 to 5 lines. At the default 1200×850 the tree grows from 371 px to 423 px and the log shrinks from 177 px to 125 px (about 8 lines). The minimum size is unchanged (647×560), and the pane divider still adjusts. The README screenshot (`assets/Screenshots/Screenshot_ex01.PNG`, previously v0.3.0 showing another project) is replaced with v1.0.0 on this repository (1216×889). `*.lnk` was hidden for that session only. | Owner decision; implemented in Tranche 8 step 8.4. |
| 2026-09-25 | Defect D5 (found by the final layout probe, step 8.5): at the text editor's fixed 700 px minimum, 8.2's **Keep backup** checkbox was squeezed to 51 px of the 105 px its text needs. The editor's minimum width is now its toolbar's measured width (754 px here), never below 700. `EditorLayoutTests` checks the toolbar at the minimum size. The probe checked 8 windows at their minimum and default sizes, with 0 problems afterwards. | Fixed in Tranche 8 step 8.5. |
| 2026-09-25 | Phase 8 accepted: `docs/acceptance/v1.0.0.md`. Tranche 8 parked; `v1.0.0` tagged locally at the parking commit. Publication (push, GitHub release, package index) awaits explicit owner approval. | Tranche 8 close. |
| 2026-09-25 | Published with owner approval ("push main and the tag, and create the GitHub release"): `main` fast-forwarded `8270af2..fb4ebc7`; tag `v1.0.0` → `fb4ebc7`; GitHub release "ProjectMapper 1.0.0" (Latest) with `projectmapper-1.0.0-py3-none-any.whl` (sha256 `5fbbee01…`) and `projectmapper-1.0.0.tar.gz` (sha256 `f8c73a09…`). These were rebuilt from the tagged commit; all 112 archive members are byte-identical to the build verified in clean locations from `2d7fd1b` (only archive timestamps differ). Downloaded assets match the published checksums. Not published to PyPI. | Owner decision. |
