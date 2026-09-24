"""Hidden failures become visible: concise log line plus an internal history record (decision D)."""

import contextlib
import io
from pathlib import Path
import threading
import tkinter as tk
import unittest

from tests.support import temporary_directory, tk_root
from projectmapper.app import ProjectMapperApp
from projectmapper.tools.patcher import PatchError


class SurfacingTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(temporary_directory(self).name).resolve()
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root, self.folder)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)

    def drain(self):
        while not self.app.gui_queue.empty():
            self.app.gui_queue.get_nowait()()

    def log(self):
        return self.app.widgets["log_box"].get("1.0", "end-1c")

    def internal(self):
        return self.app.controller.history.query(category="internal")

    def assert_concise(self, fragment):
        log = self.log()
        self.assertIn(fragment, log)
        self.assertIn("see History", log)
        self.assertNotIn("Traceback", log, "tracebacks belong in history details, not the log")

    def run_worker(self, target, name="demo_task"):
        done = threading.Event()
        self.app.run_threaded_action(lambda: (target(), None)[1], name)
        for _ in range(100):
            if name not in self.app.running_tasks:
                break
            done.wait(0.02)
        self.drain()

    # --- entry finding 1: listener failures -----------------------------

    def test_listener_failure_is_logged_and_recorded(self):
        self.app.controller.dispatcher.subscribe(lambda event: 1 / 0)
        self.app.action("state.get")
        self.drain()
        (record,) = self.internal()[:1]
        self.assertEqual((record["category"], record["status"]), ("internal", "failed"))
        self.assertEqual(record["action"], "internal.listener")
        self.assertIn("ZeroDivisionError", record["detail"])
        self.assert_concise("event listener failed")

    def test_failing_hook_never_breaks_actions(self):
        self.app.controller.dispatcher.subscribe(lambda event: 1 / 0)
        self.app.controller.dispatcher.on_observer_error = lambda trace: [][1]
        self.assertEqual(self.app.controller.execute("state.get").status, "succeeded")

    # --- entry finding 2: Tk callback exceptions -------------------------

    def test_tk_callback_exception_reaches_log_and_history_not_stderr(self):
        button = tk.Button(self.root, command=lambda: [][1])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.root.tk.call(button._w, "invoke")
        self.drain()
        self.assertNotIn("IndexError", stderr.getvalue())
        (record,) = self.internal()[:1]
        self.assertEqual(record["action"], "internal.ui_callback")
        self.assertIn("IndexError", record["detail"])
        self.assert_concise("IndexError")

    def test_tool_window_callbacks_are_covered_too(self):
        window = self.app.open_backups()
        self.addCleanup(window.top.destroy)
        button = tk.Button(window.top, command=lambda: {}["missing"])
        self.root.tk.call(button._w, "invoke")
        self.drain()
        self.assertIn("KeyError", self.internal()[0]["detail"])

    def test_gui_queue_callback_failure_is_recorded(self):
        self.app.gui_queue.put(lambda: None.missing)
        self.app.process_gui_queue()
        self.assertEqual(self.internal()[0]["action"], "internal.ui_queue")
        self.assertIn("AttributeError", self.internal()[0]["detail"])

    # --- worker tasks: routine failures vs crashes -----------------------

    def test_worker_crash_is_one_log_line_with_trace_in_history(self):
        def crash():
            raise RuntimeError("unexpected state")
        self.run_worker(crash)
        self.assertNotIn("CRASH", self.log())
        self.assert_concise("demo_task failed")
        record = self.internal()[0]
        self.assertEqual(record["action"], "internal.worker")
        self.assertIn("RuntimeError: unexpected state", record["detail"])

    def test_routine_action_failure_is_concise_and_not_internal(self):
        def refused():
            raise PatchError("The file changed on disk. Preview again.")
        self.run_worker(refused)
        log = self.log()
        self.assertIn("demo_task: The file changed on disk", log)
        self.assertNotIn("CRASH", log)
        self.assertNotIn("Traceback", log)
        self.assertEqual(self.internal(), [])

    # --- the main log ---------------------------------------------------

    def test_log_is_bounded(self):
        for number in range(2100):
            self.app.log_message(f"message {number}")
        lines = self.log().splitlines()
        self.assertLessEqual(len(lines), 2000)
        self.assertIn("message 2099", lines[-1])
        self.assertNotIn("message 0]", self.log())

    def test_progress_is_not_logged_line_by_line(self):
        for number in range(60):
            (self.folder / f"f{number:02}.txt").write_bytes(b"x\n")
        self.app.action("project.scan")
        self.app.action("snapshot.compile")
        self.drain()
        self.assertNotIn("Captured", self.log())
        compile_record = self.app.controller.history.query(category="snapshot")[0]
        self.assertGreater(compile_record["progress_count"], 3)


if __name__ == "__main__":
    unittest.main()
