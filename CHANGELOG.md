# Changelog

All notable changes to ProjectMapper. Versions follow [PEP 440](https://peps.python.org/pep-0440/).

## Unreleased

### Added

- **Project patch review**: a per-file list with status, +/− and hunk counts;
  Source / Diff / Result views; diff-hunk navigation with a position indicator and
  highlighting in all three views; keyboard shortcuts (Alt+↑/↓, F8/Shift+F8, Ctrl+Enter).
- Colour-highlighted diffs in both patchers. Lines are classified by hunk line counts,
  so content such as `--- comment` is never shown as a file header.

### Changed

- Project patch validation reports every file's problems at once, each naming its
  file and hunk; Apply is still available only when the whole manifest is valid.
  `project_patch.validate` returns the full review (`valid`, `errors`, per-file
  outcomes) and issues a plan only when valid.
- The approval dialog lists per-file and total +/− counts.
- New Project Patcher windows start with an empty manifest; **Copy Schema** copies the
  full example; **Add File…** replaces an untouched example and uses a unique-line
  hunk template instead of the whole file.
- **Keep .bak backups** moved beside Apply. Disabled action buttons are greyed, and
  editor scrollbars follow the dark theme.

- Backups are managed **generations** instead of sibling `.bak` files. Project files
  back up to `_projectmapper/backups/`; files outside the project root go to a
  per-user store. The options are now labelled **Keep backup** / **Keep backups**.
  Existing `.bak` files are never touched.
- Files inside `_projectmapper/` can no longer be project-patch targets.
- Headless backup actions: list, preview (current vs backup), restore with approval
  (saving a pre-restore copy first), and approval-bound clean-up of old generations.
- Session **operation history** (`history.query`): one record per operation from any
  client, with outcome, duration, approval, affected paths, errors and backup
  references; progress is counted, not listed, so it cannot push other operations out.
- **Backups window** (main window → **Backups…**): generation list with integrity
  status, Current / Diff / Backup comparison, Restore File / Restore All Files,
  Clean Up (keep newest N) and Delete Selected. Recovery messages point to it.

- The main log keeps its most recent 2,000 lines, and progress updates go to the
  status bar instead of one log line each.

### Fixed

- Errors raised inside window callbacks were written to stderr, which the installed
  app (`pythonw`) discards. They are now logged in one line and recorded in History
  with the traceback. Event-listener failures and worker crashes are handled the
  same way.
- Routine action failures in background tasks (for example a compile refused
  because a file changed) were logged as `CRASH` with a full traceback; they are now
  one concise line.
- A second backed-up save of the same file failed (`WinError 183`, `.bak` exists).
- Any existing `.bak` file, even one the user made, blocked a whole project apply
  with backups on.
- After a failed rollback, the message claimed the original was "retained in this
  session", but it was discarded. Originals are now saved durably in a `recovery`
  generation that the message names; if that fails, the message says so.
- **Add File…** on a new Project Patcher window produced a manifest that failed
  validation on the built-in example entry.
- **Keep .bak backups** and the review position were cut off at the minimum window size.

## 0.4.0 — 2026-09-23

The first release since the single-file 0.3.0 snapshot compiler. ProjectMapper now
works in both directions: it hands a project to a reviewer or agent, and it applies
the returned changes safely.

### Added

- **Tokenizing Patcher**: apply JSON search/replace hunks to one file. Hunks are
  matched exactly, then whitespace-tolerant, and inherit indentation; ambiguity and
  overlap are rejected. Preview, apply to result, then save, optionally as a version
  or with a `.bak`. Linked **&** Validate/Apply controls.
- **Project Patcher**: a multi-file manifest in the same hunk schema. Every file is
  validated first and shown as a combined diff; application requires an explicit
  approval of that exact preview. Rollback restores only files this operation replaced.
- **Text editor** with guarded saves, find/replace, read-only mode and stale-source
  detection; **New Text File** (TextTOUCHER) with exclusive creation; **Delete File**
  with blocking, default-deny approval.
- **Exclusions manager**: built-in, custom and `.gitignore` rules with per-rule
  enable/disable and batch actions.
- **Diagnostics**: import, root, output-writability, SQLite and reference-isolation checks.
- A headless **action layer**. Every desktop operation runs through one dispatcher,
  with structured results, ordered events, per-operation cancellation, duplicate-request
  protection, and approvals that ordinary requests cannot forge.
- Standard packaging: `pip install .` provides the `projectmapper` command and
  `python -m projectmapper`, with an optional project-folder argument and `--version`.

### Changed

- Large projects: fresh metadata scans read each entry once. The tree renders lazily
  in batches, and selection is kept in a model independent of rendered rows, so
  unopened folders are still captured correctly. On a 10,000-file fixture, scan
  went from 10.7s to 1.2s and first render from 0.79s to 0.015s.
- Snapshot freshness covers file contents, selection, exclusion rules and capture
  options, and is tied to a project generation so results from an earlier root are
  rejected.
- On startup the mapper opens the folder given on the command line, otherwise the
  current directory. It no longer opens its own source folder.
- The source moved to `src/projectmapper/`. `run.bat` still launches from a checkout
  or vendor export.

### Fixed

- A file that changed during capture and then changed back (A→B→A) could be
  published as a fresh snapshot containing B. Captured bytes are now bound to the
  snapshot signature; such a compile is refused and the previous snapshot is kept.
- Cancelled or failed compiles no longer replace or delete the previous snapshot.
- Backups never overwrite an existing file; project-patch rollback no longer
  overwrites later external edits.
- `requirements.txt` no longer installs the unrelated PyPI `tk` package. ProjectMapper
  has no third-party runtime dependencies.

### Requirements

Python 3.10 or newer with Tkinter (included with the python.org installers).

## 0.3.0 — 2026-06

Single-file snapshot compiler: project tree, selection, SQLite snapshot, and Markdown
tree/filedump exports; blank-slate vendor export.
