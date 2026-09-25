# ProjectMapper development documents

This folder contains development plans, architecture decisions, and implementation
verification records. End-user instructions remain in the root `README.md`.

## Active plan

- [Application hardening and shared action layer](plans/2026-09-16-application-hardening-and-action-layer.md)
- [Verified desktop action inventory](action-inventory.md)

The active plan includes the expected outcome, current gaps, action inventory,
interface contracts, phased implementation checklist, and completion criteria.
Implementation records live in the private `.dev-log/` journal, which is ignored
and never read by the application. Phase 2 is completed after the external-review
corrections and a 110-test acceptance run. Its corrected acceptance record is
`.dev-log/02-review-followthrough.md`. Phase 3 is also completed and parked: 124
tests passed, with measured lazy rendering and metadata scan improvements. Its
acceptance record is `.dev-log/03-logical-tree-and-rendering.md`. The plan was
revised on 2026-09-23 for public release: former Phases 4–7 are renumbered 5–8, with
v1.0.0 at Phase 8, and Phase 9 adds CLI and MCP adapters. Phase 4, release readiness,
is completed and parked (142 tests; tagged `v0.4.0`; `main` pushed to GitHub 2026-09-23). Its
record is `.dev-log/04-release-readiness.md`. Phase 5, project patch review, is
completed and parked (175 tests on Python 3.10/3.13/3.14); its record is
`.dev-log/05-project-patch-review.md`. Phase 6, backup generations, restore and
retention, is completed and parked (233 tests on Python 3.10/3.13/3.14); its record
is `.dev-log/06-backup-generations.md`. Phase 7, history and operational clarity, is
completed and parked (271 tests on Python 3.10/3.13/3.14); its record is
`.dev-log/07-history-and-clarity.md`. Phase 8, full acceptance, documentation and
v1.0.0, is open; its entry record is `.dev-log/08-acceptance-and-v1.md` (approved; steps 8.1–8.2
complete, 331 tests; 8.3 next). `ui-map.md` maps every desktop entry point to its test.

## Conventions

Current authority: root `README.md` for user behavior, the active plan for remaining
scope, and `action-inventory.md` for implemented action names. Dated tranche journals
are historical evidence for their recorded code states; their entry descriptions
are not statements of current defects.

Superseded snapshots, onboarding material and June vendor exports are archived under
`.dev-log/archive/2026-09-17-documentation-audit/`, with a historical-only notice and
a hash manifest. They are retained for ontological/history reference, never as
current implementation guidance. Legacy fixture directories are explicitly labeled
as non-authoritative residue. `.parts/` is disposable, read-only reference input;
it is not an archive, documentation authority or required application component.

- Use `docs/plans/YYYY-MM-DD-descriptive-name.md` for substantial development plans.
- Update an active plan in place as decisions are reviewed; record material changes
  in its decision log so accepted scope remains clear.
- Keep checkboxes unchecked until implementation and the associated checks are complete.
- Record verification commands, results, limitations, and deviations alongside the plan.
- Distinguish verified observations, proposed designs, and unresolved questions.
- Keep runtime state, generated snapshots, backups, and test fixtures out of this folder.
- Documentation must never depend on the disposable `.parts/` reference directory.
