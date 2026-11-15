import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import app as app_module
import updates
from about import PROJECT_URL


def release(tag, url=None):
    return updates.release_from_api({"tag_name": tag, "html_url": url or f"{PROJECT_URL}/releases/tag/{tag}"})


class VersionTests(unittest.TestCase):
    def test_numeric_comparison(self):
        self.assertTrue(updates.is_newer("v1.10.0", "1.9.9"))
        self.assertTrue(updates.is_newer("v1.4.6", "1.4.5"))
        self.assertFalse(updates.is_newer("v1.4.5", "1.4.5"))
        self.assertFalse(updates.is_newer("v1.4.4", "1.4.5"))
        self.assertFalse(updates.is_newer("nightly", "1.4.5"))

    def test_only_project_release_pages_are_opened(self):
        self.assertEqual(release("v2.0.0", "https://example.org/x")["url"], updates.RELEASES_URL)
        self.assertEqual(release("v2.0.0")["url"], f"{PROJECT_URL}/releases/tag/v2.0.0")
        self.assertIsNone(updates.release_from_api({"tag_name": "v2.0.0", "prerelease": True}))


class UpdateBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings_patch = patch.object(app_module, "SETTINGS_FILE", Path(self.temp.name) / "settings.json")
        self.settings_patch.start()
        self.window = app_module.App()

    def tearDown(self):
        self.window.close()
        self.settings_patch.stop()
        self.temp.cleanup()

    def test_new_version_shows_and_skip_is_remembered(self):
        newer = release("v99.0.0")
        self.window._on_update_result(newer, manual=False)
        self.assertFalse(self.window.update_bar.isHidden())
        self.window._skip_update()
        self.assertTrue(self.window.update_bar.isHidden())
        self.assertEqual(app_module._load_settings()["skipped_update"], "v99.0.0")
        self.window._on_update_result(newer, manual=False)
        self.assertTrue(self.window.update_bar.isHidden())
        self.window._on_update_result(release("v99.0.1"), manual=False)
        self.assertFalse(self.window.update_bar.isHidden())

    def test_current_version_and_disabled_check_stay_quiet(self):
        self.window._on_update_result(release(f"v{app_module.APP_VERSION}"), manual=True)
        self.assertTrue(self.window.update_bar.isHidden())
        self.window._settings["check_updates"] = False
        with patch.object(updates.UpdateCheck, "start", side_effect=AssertionError("network")):
            self.window.check_for_updates()


if __name__ == "__main__":
    unittest.main()
