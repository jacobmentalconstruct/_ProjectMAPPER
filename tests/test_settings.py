"""Per-user settings: defaults, validation and round trips (decision F5)."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.support import temporary_directory
from projectmapper.core.settings import Settings, load_settings, save_settings, settings_path


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory(self)
        self.path = Path(self.temp.name) / "ProjectMapper" / "settings.json"

    def test_missing_file_gives_the_recommended_defaults(self):
        settings = load_settings(self.path)
        self.assertEqual(settings, Settings())
        self.assertEqual((settings.max_result_bytes, settings.max_resource_bytes), (256 * 1024, 1024 * 1024))
        self.assertTrue(settings.ask_before_single_file_writes)
        self.assertEqual(settings.problems, ())

    def test_round_trip(self):
        saved = save_settings({"max_result_bytes": 65536, "ask_before_single_file_writes": False}, self.path)
        loaded = load_settings(self.path)
        self.assertEqual(loaded, saved)
        self.assertEqual(loaded.max_result_bytes, 65536)
        self.assertFalse(loaded.ask_before_single_file_writes)
        self.assertEqual(loaded.max_resource_bytes, 1024 * 1024)

    def test_saving_an_invalid_value_writes_nothing(self):
        for values in ({"max_result_bytes": 10}, {"max_result_bytes": True},
                       {"ask_before_single_file_writes": "no"}, {"colour": "red"}):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    save_settings(values, self.path)
                self.assertFalse(self.path.exists())

    def test_bad_values_fall_back_one_by_one_and_are_reported(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"max_result_bytes": 999_999_999, "approval_timeout_seconds": 30,
                                         "ask_before_single_file_writes": 1, "extra": 1}), encoding="utf-8")
        settings = load_settings(self.path)
        self.assertEqual(settings.max_result_bytes, 256 * 1024)
        self.assertEqual(settings.approval_timeout_seconds, 30)
        self.assertTrue(settings.ask_before_single_file_writes)
        self.assertEqual(len(settings.problems), 3)

    def test_unreadable_or_malformed_file_never_stops_the_app(self):
        self.path.parent.mkdir(parents=True)
        for content in ("{not json", "[1, 2]", ""):
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                settings = load_settings(self.path)
                self.assertEqual(settings.to_dict(), Settings().to_dict())
                self.assertEqual(len(settings.problems), 1)

    def test_location_is_per_user_and_can_be_overridden(self):
        with patch.dict(os.environ, {"PROJECTMAPPER_SETTINGS": str(self.path)}):
            self.assertEqual(settings_path(), self.path)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.temp.name)}), \
                patch("projectmapper.core.settings.sys.platform", "win32"):
            os.environ.pop("PROJECTMAPPER_SETTINGS", None)
            self.assertEqual(settings_path(), self.path)


if __name__ == "__main__":
    unittest.main()
