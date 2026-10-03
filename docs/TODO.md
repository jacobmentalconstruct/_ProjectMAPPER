# Remaining engineering work

These follow-up items remain after v1.1.0. Each names what is known, what is not, and a
starting point. Decisions behind them are in the plan's decision log
(`plans/2026-09-16-application-hardening-and-action-layer.md`, section 17).

## 1. Cross-platform CI (in progress; decision E3)

The v1.1.0 suite was run on Windows with Python 3.10, 3.13 and 3.14. macOS and Linux
remain unverified. Decision F0 put this after Phase 9, which is now complete. The GitHub
Actions matrix is in `.github/workflows/tests.yml` for Windows, macOS and Linux on Python
3.10, 3.13 and 3.14; it also checks Tk window creation and uses Xvfb on Linux. First hosted
run `37121817805` exposed platform issues and was cancelled after collecting logs: Linux
had a clipped History toolbar and an unfriendly file-collision message; Windows had a lazy
tree test that expanded a folder before it was rendered; macOS exposed combobox popdown
styling and font-metric layout assumptions. Follow-up run `37122836384` passed Linux on
Python 3.10, 3.13 and 3.14. Windows still failed the lazy-tree test because the test
fixture used an unresolved temporary path; macOS 3.14 also measured the main window at
811 px and found two toolbar controls clipped at fixed test widths. Windows was cancelled
after capturing failures because macOS 3.10/3.13 stopped producing output after
`test_backups.py` and before the CLI test file. The next run passed Linux and Windows on all
three Python versions; macOS 3.14 still clipped controls in Backups and Project Patcher,
and macOS 3.10/3.13 repeated the same stall. These follow-up changes use resolved fixture
paths, measured minimum window widths, a larger Aqua allowance for native button metrics,
an 820 px compact-screen threshold matching the measured 811 px minimum, and a Project
Patcher minimum width based on both side-by-side panes. macOS jobs now emit per-test
verbose progress. That isolated the 3.10/3.13 stall to denial of a backup restore; denied
approvals now settle immediately rather than scheduling a cancelled continuation on the
worker. The item remains open until all hosted jobs pass and
platform-specific failures are resolved. Keep platform classifiers and tested-platform
claims conservative until then.

## 2. Tk start-up failure under standard-handle swapping (decision E4)

**Known (2026-09-25):**
- On Windows, creating a Tk interpreter shortly after the process's standard handles have
  been swapped (`os.dup2` onto fds 1/2, as pytest's default `--capture=fd` does) sometimes
  fails. Forms seen:
  - "couldn't read file …/init.tcl: No error"
  - "no such file or directory" for an existing `tk8.6/*.tcl`
  - `invalid command name "tcl_findLibrary"`
- Measured: 5 failures in 7,000 roots with a swap, 0 in 22,000 without. It happens on
  Tcl 8.6.12 and 8.6.15, with Python 3.10, 3.13 and 3.14. It reproduces with no
  ProjectMapper code.
- Worked around for the test suite with `--capture=sys` in `pytest.ini`. The application
  never swaps OS-level handles.

**Not known:**
- The Tcl-internal mechanism: why a handle swap makes later `CreateFileW`/`ReadFile` calls
  on library files fail.
- Whether antivirus file-system filtering (Windows Defender here) takes part.
- Whether it happens on other Windows machines.

**Starting point.** This reproducer has no pytest and no project code. It shows about 2
failures per 3,000 iterations on the development machine:

```python
import gc, os, tempfile, tkinter as tk
failures = 0
for i in range(3000):
    tmp = tempfile.TemporaryFile(buffering=0)
    saved = {fd: os.dup(fd) for fd in (1, 2)}
    for fd in (1, 2):
        os.dup2(tmp.fileno(), fd)
    try:
        gc.collect()
        root = tk.Tk(); root.withdraw(); root.update(); root.destroy()
    except tk.TclError as exc:
        failures += 1
        print(str(exc).splitlines()[0])
    finally:
        for fd, copy in saved.items():
            os.dup2(copy, fd); os.close(copy)
        tmp.close()
print("failures:", failures)
```

Then, one change at a time:
1. Run it on another Windows machine or in Windows Sandbox. This separates this machine
   from Tcl/Windows in general.
2. As administrator, temporarily exclude the Python install folders from Defender and
   rerun. This tests whether the antivirus filter takes part.
3. Record a Process Monitor trace filtered on `*.tcl`, to see the Windows result code
   behind the failing open or read.
4. If it is Tcl's, reduce it to a Tcl-only script (`tclsh` with redirected standard
   handles) and report it upstream (core.tcl-lang.org tickets).

Before removing the workaround, run the full suite repeatedly under `--capture=fd`.

## 3. Two recorded, unexplained test-environment events

Low priority; neither has recurred.
- **Tranche 6 silent 3.10 run:** one invocation produced no output, with its exit code
  masked by a pipe. That process ended before its first test result without any pytest
  report, which is an abnormal start-up termination. Exit codes are now always captured,
  so a recurrence would show the code.
- **Tranche 7 baseline-copy layout failure:** `test_patcher.py::test_controls_fit_minimum_window`
  failed once, in a `git archive` copy under load. The test measures after a single
  `root.update()`. It could wait for the geometry to settle (for example, until the
  window reports the requested size) if it ever recurs.

## 4. Star-import notices

pyflakes reports only notices from the existing `import *` sections in `app.py`,
`core/exports.py`, `core/snapshots.py` and `core/helpers.py`. Replacing them with explicit
imports would let pyflakes pass cleanly. Several tests import names through
`projectmapper.app`, so keep those names available.
