# ProjectMapper: project transforms (structural + content changesets)

Date: 2026-10-02

Status (2026-10-03): **Decisions D1–D7 recorded 2026-10-02; none open. Phase 9 is
accepted and released. Cross-platform CI remains the active next item; Phase 10
implementation has not started.**
Proposed as Phase 10, following the
conventions of `2026-09-16-application-hardening-and-action-layer.md` (entry record,
implementation/review cycle, stop gate per step, dated `.dev-log/` journal).

## 0. Handoff: resume here (any agent)

Current status (2026-10-03; refreshed after hosted CI run `37125335567`):

- **Work order:** Phase 9 is complete and v1.1.0 is tagged and pushed. Per decision F0,
  cross-platform CI is the next work item; Phase 10 follows it. Runs `37121817805` through
  `37124673080` identified and fixed platform-specific behavior, fixture paths, toolbar
  sizing, Aqua metrics, and an approval-denial hang. Latest run `37125335567` passed Linux
  and Windows on Python 3.10/3.13/3.14 and macOS 3.14. macOS 3.10/3.13 passed denied
  restore, minimum-size layout and spinbox theme tests, then emitted no further test output
  after 32% until canceled at six minutes. Tracebacks in runs `37126035883`,
  `37126599081`, `37127134972`, `37128227007`, `37128773406`, and `37129275742` found
  hidden-parent Tk event-loop waits in Backups, exclusions, History, Project Patcher review,
  New File context-menu and lazy-tree tests. The affected setups now keep parent roots
  viewable; hosted verification is pending and cross-platform acceptance remains open.
  - Steps 9.1–9.5 (adapter foundation, CLI, MCP, approval boundary, documentation,
    acceptance and release preparation) are complete. Evidence is in
    `.dev-log/09-cli-and-mcp.md` and `docs/acceptance/v1.1.0.md`.
  - Phase 9's source of truth is `docs/plans/2026-09-16-application-hardening-and-action-layer.md`
    (Phase 9, section 12B) and `.dev-log/09-cli-and-mcp.md` ("Revised steps").
- **Phase 9 must anticipate Phase 10** without implementing it:
  - 9.2 CLI help and 9.3 MCP descriptions/schemas for `project_patch.*` are written so they
    can be extended to manifest v2 (§3.8 E).
  - 9.4's Settings window is laid out so `ask_before_structural_writes` can sit beside
    `ask_before_single_file_writes` (D2).
  - 9.4's approval popup is built so it can later show a per-op checklist with Approve
    selected / Approve all / Deny all (D2). A single-decision popup is fine for Phase 9,
    but don't hard-code one yes/no into the request shape if avoidable.
- **Phase 10 begins at 10.0 after CI**: write `.dev-log/10-project-transforms.md` as the entry
  record (template: earlier tranche entries) and copy D1–D7 into the main plan's decision
  log (section 17).
- **Everything decided is in this file:** design (§3), user-facing text and docs (§3.8),
  ordered steps with gates (§4), and owner decisions (§5). Nothing is open.
- **9.2 gate completed:** after the line-ending fix, the full 378-test suite passes on
  Windows Python 3.10, 3.13 and 3.14. LF is enforced by `.gitattributes`, `.editorconfig`
  and `tests/test_line_endings.py`. Detailed evidence is in `.dev-log/09-cli-and-mcp.md`.
- **Tooltips:** all controls or none. Step 10.6a covers every existing control (§3.8 C).
- **Working rules** (from `.dev-log/README.md`):
  - Gated steps; evidence recorded per step.
  - Suites on 3.10/3.13/3.14, run one after another with exit codes captured.
  - Byte-scan changed text files.
  - Tests never open real dialogs.
  - No push or release without owner approval.

How the owner wants it to feel (from the conversation; use it to judge UI choices):

- The single-file Tokenizing Patcher stays the quick right-click path.
- Project transforms are the global tool.
- Never a hard block between the two: offer an upgrade to the Project Patcher instead.
- Everything previewed, everything undoable, from one place (Backups).
- Agents work freely on safe ops, and a human confirms every deletion, one at a time or
  all at once.

## 1. Expected outcome

One project patch can create, edit, rename, move and delete files, and create, rename,
move and delete folders, as one ordered, reviewed, all-or-nothing changeset. It has a
single preview, a single approval and a single undo. The Tokenizing Patcher (single file)
stays as the fast path for editing one file. Every structural action in the tree (rename,
move, new folder, delete) runs through the same engine, so they all get the same
validation, backup and undo. Later, moves generate their own reference fix-ups (imports,
paths) as derived patch ops that the user can switch off.

## 2. Current state (read from the code, 2026-10-02)

| Capability | Where | State |
|---|---|---|
| Single-file hunk patch | `tools/patcher.py` `apply_patch_text`, `PatchSession` | Solid. Byte-preserving, BOM- and line-ending-aware, guarded save, optional `_suffix` version copy. |
| Multi-file patch | `tools/project_patcher.py` `ProjectPatchSession` | Content edits only. Manifest `{"version":1,"files":[{path,sha256?,hunks}]}`. Reviews every file, stages, backs up, `os.replace`s, rolls back, recovery store. Refuses duplicate paths (casefold), `.parts`, `_projectmapper`, `..`, absolute paths. |
| Create file | `core/files.py` `create_text_file` | Single file, exclusive (`os.link`), extension presets. Not part of any changeset. |
| Delete file | `controller._delete` | Single file, approval, stat-identity recheck. **No backup is taken.** Not exposed to agents. |
| Rename / move file | — | **Missing.** |
| Folder create / rename / move / delete | — | **Missing** (only `_projectmapper` output `mkdir`). |
| Backups | `core/backups.py` `BackupStore` | Content-only generations (target key → bytes). Restoring rewrites bytes and **cannot undo a move or create**. |
| Plans / approval | `controller._store_plan`, `ApprovalPlan`, dispatcher | Plans bound to `state.generation`. Approval message built from `DiffFile` stats. |
| Freshness | `core/state.py` `mark_dirty`, tree rescan | Paths are recorded. Selection (`LogicalTree.selection`) is keyed by `str(path)`, so moved paths lose their capture state. |
| Agents | `adapters/session.py` `EXPOSED`/`NOT_EXPOSED` | A test fails if a new action is unclassified. `project_patch.apply` is exposed with forced backup + human approval. |

Conclusion: the edit path is mature. Structural ops, a changeset-level undo, and the
link between the two are new work. The existing staging/rollback/recovery patterns in
`apply_all` are the template for everything below.

## 3. Design

### 3.1 Manifest v2

```json
{
  "version": 2,
  "description": "Move utils under core",
  "ops": [
    {"op": "mkdir",    "path": "src/core"},
    {"op": "move_dir", "from": "src/utils", "to": "src/core/utils"},
    {"op": "move",     "from": "src/core/utils/helpers.py", "to": "src/core/utils/text.py", "sha256": "…"},
    {"op": "create",   "path": "src/core/__init__.py", "content": ""},
    {"op": "patch",    "path": "src/core/utils/text.py", "sha256": "…", "hunks": [ … ]},
    {"op": "delete",   "path": "old/legacy.py", "sha256": "…"},
    {"op": "delete_dir", "path": "old"}
  ]
}
```

- Op set: `patch`, `create`, `delete`, `move` (`rename` accepted as an alias), `mkdir`,
  `move_dir` (`rename_dir` alias), `delete_dir` (empty by default; `"recursive": true`
  expands to per-file `delete` ops so each file is backed up and shown).
- **v1 stays valid.** `{"files":[…]}` is normalized to `patch` ops. All v1 review output must
  stay identical, so existing tests and saved manifests keep working.
- **Path semantics are sequential.** Each op's paths refer to the tree as it stands after
  the previous ops. This is the only rule users need to learn.
- `sha256` is optional on every op that reads an existing file (`patch`, `delete`, `move`),
  and checked if present.
- Additional optional per-op fields: `description`, and later `derived_from` (index of the op
  that caused it, §3.7).

### 3.2 Virtual tree (simulation)

New `core/vtree.py`: an overlay on the real filesystem, keyed by casefolded relative path.

- A node is a file (bytes, mode, origin key, current sha) or a dir. Deletions are tombstones.
  A miss is read lazily from disk. Moves rewrite keys (for dirs, every descendant by prefix).
- Each op is applied in order. Problems are collected per op with the op's index, and never
  raised on the first error. This keeps the current review behaviour: review everything,
  and produce a plan only when all ops are valid.
- Conflict checks:
  - Target missing or already a tombstone.
  - Destination exists. This includes **case-only collisions on Windows**: `A.py`→`a.py` is
    a legal rename, while `a.py` onto an existing different `A.py` is not.
  - `move_dir` into itself or its own descendant.
  - Op on the project root itself.
  - Paths under `.parts`, `_projectmapper`, or the version-control folders `.git`, `.hg`
    and `.svn` (D5).
  - `patch` on a non-UTF-8/binary file.
  - Overlapping hunks (existing engine).
  - `delete_dir` not empty without `recursive`.
- Warnings (shown, not blocking): destination matched by the exclusion policy (the file
  will vanish from the tree), extension change on a move, deletion of a file that other
  ops already patched.
- Output: the ordered op list with resolved absolute paths, a "before" fingerprint for every
  touched path, and the final content of every touched file. This output is the plan and the
  preview data.

### 3.3 Executor (journaled transaction)

New `core/transaction.py`. Replaces the body of `ProjectPatchSession.apply_all`; its
contract stays: all or nothing, `backup` before the first change, `recover` when rollback
can't restore.

1. **Recheck** every "before" fingerprint (sha256 + stat identity, as `_delete` does).
2. **Back up** every original whose bytes will be lost (`patch`, `delete`, overwritten
   content) into one generation, *before* any change (§3.4).
3. **Run ops in order**, appending the inverse of each to an in-memory journal:
   - `patch`: `stage_bytes` + recheck + `os.replace`; inverse writes original bytes.
   - `create`: stage + exclusive `os.link`; inverse unlinks after checking the bytes.
   - `move`: no-replace rename. Windows `os.rename` already refuses an existing target.
     POSIX needs `os.link`+`unlink` for files and an explicit check for dirs. A case-only
     rename on Windows goes through a temporary name. Inverse renames back.
   - `delete`: **rename into a quarantine** at `_projectmapper/.pending/<operation_id>/`
     (same volume, so it's atomic). Inverse renames it back. The quarantine is purged
     only after commit.
   - `mkdir`, `move_dir`, `delete_dir` (empty): plain fs calls with direct inverses.
4. **On any failure**, replay the journal in reverse. Anything that can't be restored goes
   to `recover`, exactly as today. Raise a typed `RecoveryRequiredError` instead of the
   controller matching `"Recovery required" in str(exc)` (controller line 607).
5. **On success**, purge the quarantine and return the forward and inverse changesets.

Windows risk to test explicitly: renaming a folder while a file in it is open (editor
window, Explorer, antivirus) raises `PermissionError` partway through. This must roll back
cleanly.

### 3.4 Backups and undo

The backup manifest moves to **version 2**. It still accepts v1 when reading. A new
optional `changeset` record holds the forward ops and the inverse ops. New kind:
`changeset`.

- Undoing a changeset generation runs its **inverse changeset through the same engine**:
  preview, recheck that the current state matches the post-apply fingerprints, approval,
  transaction. If files were edited since then, the preview reports `source_changed` per
  path rather than overwriting.
- Content-only generations keep restoring exactly as now.
- `file.delete` is routed through the engine as a one-op changeset, so **deletes get a
  backup and an undo** (it has neither today).

### 3.5 Actions, state, adapters

- `project_patch.validate` / `.apply` accept v1 and v2. `patch.schema` with `project`
  returns a v2 example.
- New thin actions that build one-op changesets and go through the same plan/approval:
  `file.rename`, `file.move`, `folder.create`, `folder.rename`, `folder.move`,
  `folder.delete`. Undo is handled by `backup.preview` / `backup.restore` on changeset
  generations (D4); there is no separate undo action.
- `_changed` marks both old and new paths dirty. `LogicalTree.remap(old, new)` moves
  selection keys (prefix rewrite for dirs) so capture checkboxes survive a move.
- Dispatcher `TARGET_KEYS` gains `from`/`to`. History `category_of` already splits on the
  first dot. `errors.py` gains any new codes (`conflict`), and the error-wording test must
  list them.
- Adapters: every new action must be classified (test-enforced). Agent access to
  destructive ops is decision D2.

### 3.6 Review UI and entry points

- **Project Patcher window** (`project_patcher_ui.py`):
  - The file list becomes an op list with badges (`~` patch, `+` create, `−` delete, `→`
    move, folder variants).
  - A move shows `old → new` plus any content diff. A create diff is all-added; a delete
    diff is all-removed.
  - The approval message lists counts by kind and **lists destructive ops first**.
- **Main toolbar:** add "Project Transform…", which opens the Project Patcher at the
  project root. It's the global tool.
- **Tree context menu** (`app.on_file_context_menu`):
  - Files: Rename…, Move…, and Delete (now with backup).
  - Folders: New Folder…, Rename…, Move…, Delete Folder….
  - Each builds a one-op changeset and shows a compact review.
  - "Tokenizing Patcher…" stays for single files. "Project Patcher…" is available from
    file, folder and empty-space selections and always opens at the project root.
- **Single → project upgrade:** if JSON pasted into the Tokenizing Patcher has `files` or
  `ops`, show a banner with "Open in Project Patcher". Also add a button that carries the
  current hunks + sha256 into a v2 manifest (reusing `_add_entry` logic). No hard warning
  or block.
- **Open tool windows:** when a changeset moves or deletes a file that is open in a
  Patcher or Text Editor window, that window shows "moved to …" / "deleted" and disables
  Save. Today Save would hit a bare `OSError`.

### 3.7 Reference fix-ups (derived ops)

After structural ops are simulated, a deriver scans text files in the virtual tree. It
respects exclusions and only reads UTF-8 files. For each `move`/`move_dir` it emits `patch`
ops with `derived_from` set.

- First target: Python. That covers `import a.b`, `from a.b import`, relative imports, and
  `__init__` package moves.
- Second target: plain path string literals that match the old relative path.
- Each derived hunk is generated with enough context to match exactly once, and is
  verified against the virtual-tree contents. A derived hunk that can't be made unique is
  reported, not guessed.
- The UI groups derived ops under their cause, with a toggle per op and one per group.
  Derived ops are on by default (decision D6).
- The deriver interface is per language, so other languages can be added later.

### 3.8 User-facing text, help and documentation (owner requirement, 2026-10-02)

Every user-visible surface that describes patches, manifests or file operations must be
updated in the same step as the behaviour it describes. A step is not done while any text
still describes the old behaviour. Verified inventory, 2026-10-02:

**A. Example JSON and the "Copy Schema" buttons**
- `controller._schema` (`patch.schema` action) returns `EXAMPLE_MANIFEST` from
  `tools/project_patcher.py` when `project` is true. It must become a **v2 example that
  shows every op type**, each with a `description`, and still be accepted by
  `project_patch.validate` as a no-op-safe template. Also update `EXAMPLE_ENTRY` and
  `SKELETON_MANIFEST`, and the `_add_entry` cleanup that strips the untouched example
  entry.
- `tools/project_patcher_ui.py` "Copy Schema" button (line ~45), and its status text
  "Example project patch copied." (line ~241).
- `tools/patcher_ui.py` has its **own** `SCHEMA` constant (line ~25), used as the initial
  editor text, separate from `controller._schema`'s single-file example. Make one source of
  truth: the window reads `patch.schema` for both, or both import a shared constant. The
  single-file schema itself does not change (single-file stays hunk-only), but the two
  copies must not drift.
- Consider a full machine-readable JSON Schema (draft 2020-12) for manifest v2 next to the
  example, for agents. It can be reused by the MCP tool's `inputSchema` (Phase 9.3 lands
  first; Phase 10 updates it).

**B. Window labels, buttons and status lines**
- `project_patcher_ui.py`:
  - Panel heading `PROJECT PATCH MANIFEST`.
  - Buttons "Add File…", "Load Patch JSON", "Validate / Preview", "Apply Project Patch".
  - Navigation "◀ File / File ▶ / ◀ Hunk / Hunk ▶". These become op/hunk navigation: "File"
    is wrong for a folder op.
  - Every `status.set(...)` string. They say "file(s)" where they must now say "op(s)" or
    "change(s)", with counts by kind. Lines ~55, 257, 273, 305, 321, 330–345, 361–380.
  - The close-confirmation `messagebox` text.
- `patcher_ui.py`: the status texts stay single-file, plus the new upgrade banner and the
  "Open in Project Patcher" button (§3.6).
- `app.py` `on_file_context_menu`: new menu labels and their disabled-state labels, e.g.
  "Rename… (select a file or folder)", matching the existing "(select a file)" pattern.
  Also the new toolbar button "Project Transform…" and `log_message` texts in
  `file_transformed` ("Moved", "Renamed", "Created folder", …).
- Approval dialogs: the `ApprovalPlan` `title`/`message` for project apply. Add the
  destructive per-op approval window (D2) and the compact one-op review for tree actions.
- Backups window (`tools/backups_ui.py`): how a `changeset` generation is listed and
  previewed ("Undo transform" wording rather than "Restore files"), and the kind label.
- History window (`tools/history_ui.py`): labels for the new actions and categories
  (`folder.*`).
- Settings window (built in Phase 9.4): label and help text for
  `ask_before_structural_writes` next to `ask_before_single_file_writes`.

**C. Tooltips: every control, existing and new (owner decision, 2026-10-02)**

Owner rule: "If we add any tooltips we update all controls to match." Tooltips are
all-or-nothing. They arrive in one step that covers every control in the app, and every
later step adds them for its own controls.

- **Helper.** The app has **no tooltip helper today** (`tools/ui_base.py`). Add a `ToolTip`
  helper to `ui_base.py` with:
  - a hover delay of about 500 ms;
  - dark-theme colours from the shared palette;
  - hide on leave, click and focus-out;
  - no keyboard-focus stealing;
  - `wraplength` for long text.
  Tests must not depend on real pointer hover; they call the helper's show/hide directly,
  in the style of `DesktopCase.fire_binding`.
- **One registry.** All tooltip text lives in one module (e.g. `tools/tooltips.py`, a dict
  keyed by a stable control id). Wording is then reviewed in one place, and a test can
  check coverage.
- **Coverage.** Every interactive control in every window gets a tooltip. `docs/ui-map.md`
  already lists every control per window, so it is the checklist:
  - main window: path row, tree, every action-row button and checkbox, exclusion
    controls, and context-menu entries via the status line, since Tk menus have no hover
    tips;
  - Exclusions window;
  - Text editor;
  - New Text File;
  - Tokenizing Patcher, including both Copy Schema buttons;
  - Project Patcher;
  - Backups;
  - History;
  - the Settings window and approval popup (Phase 9.4).
- **Content rule.** One or two plain sentences saying what the control does and anything
  non-obvious. Examples: "The file is not changed until Save Result", "Linked: one click
  validates and applies". Name the keyboard shortcut when there is one.
- **Coverage test.** Walk each window's widget tree after construction. Every `Button`,
  `Checkbutton`, `Entry`, `Spinbox`, `Combobox` and `Treeview` must have a registered tooltip
  id, or be on an explicit, commented exemption list (e.g. purely decorative labels). A new
  control without a tooltip then fails the suite.
- **When.** Existing controls are done in **step 10.6a** (new, below), before Phase 10's
  new UI. Steps 10.6, 10.7 and 10.8 then add tooltips for their own controls, and the
  coverage test keeps them honest.

**D. Error wording**
- `application/errors.py` `LABELS`: new codes (e.g. `conflict`) need labels. The
  error-wording test enforces that every raised code has one.
- Engine messages in `core/vtree.py` and `core/transaction.py` must name the op index and
  kind ("Op 4 (move): destination exists: src/a.py"), matching the existing
  "Hunk N: …" style.

**E. Agent-facing descriptions**
- Adapter `NOT_EXPOSED` reasons and any `EXPOSED` additions (`adapters/session.py`).
- MCP tool descriptions and input schemas (Phase 9.3) for `project_patch.*` and every new
  action. They must state the D2 rules in one line each: non-destructive applies
  directly, deletes need per-op human approval, edits follow the owner's setting.
- CLI help text (Phase 9.2) for the same actions.

**F. Documentation**
- Root `README.md`:
  - "Project Patches" becomes "Project Transforms": manifest v2, op table, sequential
    path rule, review, undo.
  - "Deleting Files": deletes now have a backup and an undo.
  - "Backups": changeset generations and undo.
  - New subsection for tree rename/move/folder actions.
  - The settings section.
- `docs/ui-map.md`: every new entry point mapped to its test.
- `docs/action-inventory.md`: every new action.
- `docs/developer-guide.md`: Approvals (per-op destructive approval and the D2 matrix),
  Error codes (count changes), Actions.
- `docs/README.md`: current state and active plan links.
- `CHANGELOG.md`: v1.2.0 entry.
- Agent integration guide (Phase 9.5 creates it; Phase 10 extends it).

**Gate (applies to 10.5, 10.6, 10.7, 10.8, 10.9):** each step's journal record includes a
"Text audit" list of every string, tooltip, schema and doc section it changed. 10.9 adds a
whole-repo search for stale wording (`files list`, `"files":` in examples, "file(s)" in
project-patch contexts, "Project Patcher" vs "Project Transform") and records the result.

## 4. Implementation cascade

Each step has a stop gate: full suite green on Python 3.10/3.13/3.14, pyflakes clean, a
review, and a journal entry. Every step depends only on the ones above it.

### 10.0 — Entry record and decisions
Write the Phase 10 entry after Phase 9 acceptance (D1) and copy D1–D7 into the decision
log. Nothing else starts before this.

### 10.1 — Foundation (no behaviour change)
- Move `ProjectPatchSession._resolve` into `core/paths.resolve_in_root(root, relative)`,
  adding the version-control folder refusal (D5).
- Add `core/changeset.py`: op dataclasses, parser, v1→v2 normalizer, inverse-op
  definitions.
- Gate: existing tests unchanged and green. v1 manifests normalize to equivalent `patch`
  ops. Parser tests cover every malformed shape.

### 10.2 — Virtual tree and validator
- Add `core/vtree.py` with conflict and warning rules from §3.2.
- Re-base `ProjectPatchSession.review` on it, keeping the v1 outcome dict shape (the UI
  and adapters read it).
- Gate: v1 review output byte-identical on existing fixtures. A conflict-matrix test
  covers each refusal, including case-only collisions, move-into-self, and sequential path
  semantics.

### 10.3 — Executor
- Add `core/transaction.py` (§3.3), the quarantine, a no-replace rename helper, and
  `RecoveryRequiredError`.
- `apply_all` delegates to it. Update the controller to catch the typed error.
- Gate: fault-injection tests in the style of `test_safety_regressions.py`. Fail at every
  op index and check full rollback. Fail during rollback and check the recovery generation.
  Test a locked folder rename on Windows. Test POSIX overwrite refusal.

### 10.4 — Backups v2 and undo
- Backup manifest v2 with the `changeset` record and the new kind. Make `_validate`
  accept v1 and v2.
- Undo = inverse changeset through 10.2 + 10.3.
- Route `file.delete` through the engine.
- Gate: v1 generations still list, preview and restore. Undo a mixed changeset round-trip
  to byte- and tree-identical state. Undo after an external edit is refused per path.

### 10.5 — Controller, actions, state, adapters
- v2 in `project_patch.*` and `patch.schema`.
- Add the new actions from §3.5, `LogicalTree.remap`, and dual-path dirty marking.
- Update `TARGET_KEYS`, the new error codes, and the adapter classification per D2,
  including the per-op destructive approval and the `ask_before_structural_writes`
  setting.
- Text (§3.8): `patch.schema` v2 example and the single `SCHEMA` source (A); `errors.py`
  labels (D); adapter reasons and the CLI/MCP descriptions and schemas (E);
  `docs/action-inventory.md` and developer-guide Approvals/Error codes (F).
- F3 amendment (D2): Phase 9's "project apply always asks" becomes "asks unless the
  changeset is non-destructive only and `ask_before_structural_writes` is false".
  Update the adapter session docstring, the developer guide and the session tests to match.
- Gate: action tests per new action. The adapter classification test passes. Selection
  survives move/rename. History records structural ops with both paths.

### 10.6a — Tooltips for every existing control
- `ToolTip` helper, the tooltip text registry, and tooltips for every control listed in
  `docs/ui-map.md` (§3.8 C).
- Coverage test over every window.
- `docs/ui-map.md` gains a tooltip column, and the README notes that hovering shows help.
- Gate: the coverage test passes for every window. UI smoke tests stay green, and no test
  opens a real tooltip window. Owner reviews the wording list (the registry file) before
  the step is parked.

### 10.6 — Review UI
- Op list, badges, move/create/delete diffs, destructive-first approval text.
- v2 schema template, and "Add file" producing `patch` ops.
- Text (§3.8): all Project Patcher labels, navigation and status lines (B); the
  destructive approval window wording (B); the `ToolTip` helper and tooltips for the new
  controls and badges, registered and covered by the 10.6a test (C); Backups and History wording for changeset generations (B).
- Gate: `test_project_review_window.py` and `test_review_views.py` extended. UI smoke
  tests still fit the minimum window.

### 10.7 — Desktop entry points
- Context-menu items, the toolbar "Project Transform…", the compact one-op review, and the
  single → project upgrade banner and button.
- Open-window notification on move/delete.
- Text (§3.8): context-menu and toolbar labels, `log_message` texts, the upgrade banner,
  tooltips (B, C); the settings label (B); `docs/ui-map.md` and the README sections (F).
- Gate: UI smoke tests for each entry point. A rename from the tree is undoable from
  Backups.

### 10.8 — Reference fix-ups (Python)
- Deriver interface, Python import deriver, and path-literal deriver.
- Derived-op grouping and toggles in the review UI, with tooltips explaining
  "derived" (C) and a README paragraph (F).
- Gate: fixture project where a package move is validated, applied and imported cleanly
  (the moved project's tests run). Non-unique sites are reported, not patched.

### 10.9 — Acceptance and release
Acceptance report (`docs/acceptance/v1.2.0.md`), developer guide, README, CHANGELOG,
vendor export. Run the whole-repo stale-wording search from §3.8 and record it. Tag only
with owner approval.

## 5. Decisions (owner, 2026-10-02)

- **D1 — Sequencing with Phase 9. Decided:** Phase 9 finishes first. Phase 10 opens after
  Phase 9's acceptance.
- **D2 — Agent access to structural ops. Decided:** agents may send every op type.
  Approval depends on the op class:

  | Class | Ops | Approval for adapter origins |
  |---|---|---|
  | Non-destructive | `mkdir`, `create`, `move`/`rename`, `move_dir`/`rename_dir` | None beyond the adapter's existing rules. Nothing is lost: creates are exclusive, moves never replace, and everything is in the undo record. |
  | Content edit | `patch` | Unchanged from Phase 9: the existing approval rules and owner settings apply. D2 does not loosen them. |
  | Destructive | `delete`, `delete_dir` (and each file a `recursive` delete expands to) | A human approves each op. The approval window lists every destructive op with a checkbox and its preview, plus **Approve selected**, **Approve all** and **Deny all**. |

  Partial approval: denied ops are removed and the changeset is **simulated again**. Later
  ops may depend on a denied delete (for example a `move` onto the freed name). If the
  reduced changeset is invalid, the whole apply is refused with the reasons and nothing is
  written. The approval is bound to the re-validated plan, never to the original.
  Implementation goes in 10.5 (session classification and approval request shape) and 10.6
  (approval window). `ApprovalRequest` gains a per-op list; the approver returns the
  approved op indexes.

  Non-destructive prompt (owner, 2026-10-02): **relaxed by default, with a toggle.**
  - A new owner setting, `ask_before_structural_writes`, defaults to `false`. It is one
    entry in `core/settings.py` `FLAGS`, beside `ask_before_single_file_writes`, with the
    same per-key fallback and validation.
  - `false` (default): a changeset of only non-destructive ops applies with no prompt.
  - `true`: such a changeset gets one summary approval (op list + preview) before it
    applies.
  - The setting never affects the destructive per-op approval or the content-edit rule.
  - The desktop exposes it next to the existing single-file setting.
  - Tests cover both values and an invalid value falling back to `false`.
- **D3 — Delete mechanics. Decided:** quarantine at `_projectmapper/.pending/<operation_id>/`,
  purged after commit.
- **D4 — Undo surface. Decided:** one place. Backups' preview and restore understand
  changeset generations. There are no separate `changeset.undo*` actions; §3.5 and 10.4
  use `backup.preview`/`backup.restore`.
- **D5 — Version-control folders. Decided:** refuse any op whose source or destination is
  inside, or is, `.git/`, `.hg/` or `.svn/`. The project root itself is also refused. Files
  such as `.gitignore` and `.gitattributes` are ordinary files and stay allowed.
- **D6 — Derived fix-ups default. Decided:** on (pre-checked) in the review, always
  visible, grouped under their cause, and switchable per op or per group. In the agent
  path, derived ops are `patch` ops and follow the content-edit rule in D2.
- **D7 — Manifest version. Decided:** `version: 2` with `ops`; v1 `files` stays accepted.

## 6. Out of scope (for now)

- Drag-and-drop moves in the tree. They would feed the same one-op path once 10.7 exists.
- Non-Python reference derivers.
- Binary file content ops (moves and deletes of binaries are in scope; patching them is not).
- Cross-volume moves (everything is inside one project root).
