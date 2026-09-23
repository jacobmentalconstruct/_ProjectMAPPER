# Changelog

All notable changes to ProjectMapper. Versions follow [PEP 440](https://peps.python.org/pep-0440/).

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
