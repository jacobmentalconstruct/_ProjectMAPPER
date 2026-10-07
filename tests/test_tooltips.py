"""Every desktop control has registered, usable hover help."""

import tkinter as tk
from unittest.mock import patch

from projectmapper.adapters.session import ApprovalRequest
from projectmapper.adapters.approval_ui import show_approval
from projectmapper.tools.ui_base import missing_tooltips
from tests.test_ui_smoke import DesktopCase


class TooltipCoverageTests(DesktopCase):
    def test_every_window_control_has_a_registered_tooltip(self):
        settings = self.app.open_settings()
        self.app.manage_exclusions_popup()
        exclusions = self.app.exclusions_popup
        editor = self.app.open_text_editor(self.a)
        editor.show_find_replace()
        windows = [
            self.root,
            settings.top,
            exclusions.top,
            editor.top,
            editor.find_window,
            self.app.open_text_toucher(self.folder).top,
            self.app.open_tokenizing_patcher(self.a).top,
            self.app.open_project_patcher(self.folder).top,
            self.app.open_backups().top,
            self.app.open_history().top,
        ]
        self.addCleanup(lambda: [window.destroy() for window in windows[1:]
                                 if window.winfo_exists()])

        for window in windows:
            with self.subTest(window=window.title() if window is not self.root else "main"):
                self.assertEqual(missing_tooltips(window), [])

    def test_tooltip_popup_shows_and_hides_without_pointer_events(self):
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)

        button = next(widget for widget in walk(self.root) if widget.winfo_class() == "Button")
        tooltip = button._projectmapper_tooltip
        tooltip.show()
        self.assertIsNotNone(tooltip.window)
        self.assertTrue(tooltip.window.winfo_exists())
        tooltip.hide()
        self.assertIsNone(tooltip.window)

    def test_approval_window_buttons_have_tooltips(self):
        request = ApprovalRequest("text.save", "test", "Save file?", "Save src/a.py?",
                                  ("src/a.py",), "")
        found = []

        def inspect_and_close(_root, window):
            def walk(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from walk(child)
            found.extend(widget._projectmapper_tooltip_id for widget in walk(window)
                         if getattr(widget, "_projectmapper_tooltip_id", None))
            window.destroy()

        with patch.object(tk.Misc, "wait_window", inspect_and_close):
            self.assertFalse(show_approval(request, 30))
        self.assertCountEqual(found, ["approval.deny", "approval.approve"])
