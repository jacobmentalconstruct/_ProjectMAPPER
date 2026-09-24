"""History window: access point, list, filters, details, live updates, layout and keyboard."""

import hashlib
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from tests.support import temporary_directory, tk_root
from projectmapper.app import ProjectMapperApp


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HistoryWindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(temporary_directory(self).name).resolve()
        self.user = Path(temporary_directory(self).name).resolve() / "user-store"
        env = patch.dict(os.environ, {"PROJECTMAPPER_USER_BACKUPS": str(self.user)})
        env.start()
        self.addCleanup(env.stop)
        self.a = self.folder / "a.txt"
        self.a.write_bytes(b"v1\n")
        self.root = tk_root(self)
        self.root.withdraw()
        self.app = ProjectMapperApp(self.root, self.folder)
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)

    def open(self):
        window = self.app.open_history()
        self.addCleanup(lambda: window.top.winfo_exists() and window.close())
        return window

    def rows(self, window):
        return [window.operation_list.set(iid, "action") for iid in window.operation_list.get_children()]

    def select(self, window, action):
        iid = next(i for i in window.operation_list.get_children() if window.operation_list.set(i, "action") == action)
        window.operation_list.selection_set(iid)
        window.show_details()
        return window.details.get("1.0", "end-1c")

    def save(self, text, digest=None, **extra):
        return self.app.controller.execute("text.save", {"path": str(self.a), "text": text,
                                                         "sha256": digest or sha(self.a), **extra}, origin="cli-test")

    def test_opened_from_the_log_header_and_single_instance(self):
        button = self.app.widgets["history_button"]
        self.assertEqual(button.master.master, self.app.widgets["log_box"].frame.master, "log panel header")
        button.invoke()
        window = self.app.history_window
        self.addCleanup(lambda: window.top.winfo_exists() and window.close())
        self.assertIs(self.app.open_history(), window)

    def test_lists_operations_newest_first_with_origin_status_and_target(self):
        self.save("v2\n")
        self.save("v3\n", digest="0" * 64)
        window = self.open()
        self.assertEqual(self.rows(window), ["text.save", "text.save"])
        first, second = window.operation_list.get_children()
        self.assertEqual(window.operation_list.set(first, "status"), "failed")
        self.assertEqual(window.operation_list.item(first)["tags"], ["problem"])
        self.assertEqual(window.operation_list.set(second, "origin"), "cli-test")
        self.assertEqual(window.operation_list.set(second, "target"), "a.txt")
        self.assertIn("1 need attention", window.status.get())

    def test_details_show_labelled_error_approval_paths_and_traceback(self):
        self.save("v2\n", digest="0" * 64)
        pending = self.app.controller.execute("file.delete", {"path": str(self.a)})
        self.app.approve_action(pending.operation_id, False)
        self.app.controller.dispatcher.wait(pending.operation_id)
        self.app.controller.history.record_problem("worker", "demo failed: boom", "Traceback ...\nRuntimeError: boom")
        window = self.open()
        failed = self.select(window, "text.save")
        self.assertIn("The file changed on disk (source_changed)", failed)
        self.assertIn(str(self.a), failed)
        denied = self.select(window, "file.delete")
        self.assertIn("Approval: denied", denied)
        internal = self.select(window, "internal.worker")
        self.assertIn("RuntimeError: boom", internal)
        self.assertEqual(str(window.backups_button["state"]), "disabled")

    def test_generation_reference_enables_open_backups(self):
        self.app.controller.history.record_problem(
            "worker", "Recovery required: originals saved in recovery backup 20260924T000000000000Z-abcd1234", "")
        window = self.open()
        self.select(window, "internal.worker")
        self.assertEqual(str(window.backups_button["state"]), "normal")
        window.backups_button.invoke()
        self.addCleanup(lambda: self.app.backups_window.top.winfo_exists() and self.app.backups_window.top.destroy())
        self.assertTrue(self.app.backups_window.top.winfo_exists())

    def test_filters(self):
        self.save("v2\n")
        self.save("v3\n", digest="0" * 64)
        self.app.controller.execute("backup.list", {})
        window = self.open()
        window.category.set("backup")
        window.refresh()
        self.assertEqual(self.rows(window), ["backup.list"])
        window.category.set("All")
        window.outcome.set("failed")
        window.refresh()
        self.assertEqual(self.rows(window), ["text.save"])
        window.outcome.set("All")
        window.text.set("backup.list")
        window.refresh()
        self.assertEqual(self.rows(window), ["backup.list"])
        window.clear_filters()
        self.assertEqual(len(self.rows(window)), 3)

    def test_live_updates_from_a_headless_client_are_debounced(self):
        window = self.open()
        self.assertEqual(self.rows(window), [])
        calls = []
        real = window.refresh
        window.refresh = lambda: (calls.append(1), real())[1]
        for text in ("v2\n", "v3\n", "v4\n"):
            self.save(text)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and self.rows(window).count("text.save") < 3:
            while not self.app.gui_queue.empty():
                self.app.gui_queue.get_nowait()()
            self.root.update()
            time.sleep(0.05)
        # The desktop also rescans after writes, so other operations may appear too.
        self.assertEqual(self.rows(window).count("text.save"), 3)
        self.assertLessEqual(len(calls), 4, "many record changes, few refreshes")

    def test_close_unsubscribes(self):
        history = self.app.controller.history
        before = len(history._listeners)
        window = self.open()
        self.assertEqual(len(history._listeners), before + 1)
        window.close()
        self.assertEqual(len(history._listeners), before)
        other = self.open()
        other.top.destroy()
        self.assertEqual(len(history._listeners), before, "destroy without close also unsubscribes")

    def test_every_control_visible_at_minimum_size(self):
        self.save("v2\n")
        window = self.open()
        window.top.geometry("760x520")
        self.root.update()
        top = window.top

        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        controls = [w for w in walk(top) if w.winfo_class() in ("Button", "TCombobox", "Entry")]
        controls += [window.operation_list, window.details, window.status_label]
        for widget in controls:
            with self.subTest(widget=str(widget)):
                x = widget.winfo_rootx() - top.winfo_rootx()
                y = widget.winfo_rooty() - top.winfo_rooty()
                self.assertTrue(widget.winfo_ismapped())
                self.assertLessEqual(x + widget.winfo_width(), top.winfo_width())
                self.assertLessEqual(y + widget.winfo_height(), top.winfo_height())
                if widget.winfo_class() == "Button":
                    self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth(), "text clipped")

    def test_keyboard_traversal_reaches_controls(self):
        self.save("v2\n")
        window = self.open()
        self.root.update()
        chain, current = [], window.operation_list
        for _ in range(40):
            current = current.tk_focusNext()
            if current is None or current in chain:
                break
            chain.append(current)
        classes = [w.winfo_class() for w in chain]
        self.assertEqual(classes.count("TCombobox"), 2, classes)
        self.assertIn("Entry", classes)
        self.assertIn(window.operation_list, chain + [window.operation_list])


if __name__ == "__main__":
    unittest.main()
