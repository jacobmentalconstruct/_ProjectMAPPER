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
`.dev-log/02-review-followthrough.md`. Phase 3 is next.

## Conventions

- Use `docs/plans/YYYY-MM-DD-descriptive-name.md` for substantial development plans.
- Update an active plan in place as decisions are reviewed; record material changes
  in its decision log so accepted scope remains clear.
- Keep checkboxes unchecked until implementation and the associated checks are complete.
- Record verification commands, results, limitations, and deviations alongside the plan.
- Distinguish verified observations, proposed designs, and unresolved questions.
- Keep runtime state, generated snapshots, backups, and test fixtures out of this folder.
- Documentation must never depend on the disposable `.parts/` reference directory.
