# Legacy fixture directories

Existing `tmp*` subdirectories under `tests/` are old temporary test residue,
retained for historical context only. They are not maintained test inputs or current
acceptance evidence. Some have restrictive permissions; this documentation cleanup
does not alter those permissions or claim to have inspected every file.

Maintained tests are the Python test modules and shared support code. Current runs
use isolated temporary directories. The legacy `tmp*` directories are ignored by Git.
