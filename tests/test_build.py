import os
from pathlib import Path
import unittest
from unittest.mock import patch

from build_windows import app_metadata, build_environment
from main import smoke_check


class BuildTests(unittest.TestCase):
    def test_build_does_not_inherit_external_dll_or_plugin_paths(self):
        with patch.dict(os.environ, {"PATH": "unrelated-dll-directory",
                                     "QT_PLUGIN_PATH": "unrelated-plugins",
                                     "QT_QPA_PLATFORM": "offscreen",
                                     "PYTHONPATH": "unrelated-modules"}):
            env = build_environment()
            self.assertNotIn("unrelated-dll-directory", env["PATH"])
            self.assertNotIn("QT_PLUGIN_PATH", env)
            self.assertNotIn("QT_QPA_PLATFORM", env)
            self.assertNotIn("PYTHONPATH", env)
            self.assertEqual(os.environ["PATH"], "unrelated-dll-directory")
            self.assertIn(str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"), env["PATH"])

    def test_smoke_roundtrip_uses_temporary_files(self):
        smoke_check()

    def test_binary_metadata_matches_application(self):
        from about import APP_AUTHOR, APP_NAME, APP_VERSION
        root = Path(__file__).resolve().parents[1]
        metadata = app_metadata(root)
        self.assertEqual(metadata, {"APP_AUTHOR": APP_AUTHOR, "APP_NAME": APP_NAME, "APP_VERSION": APP_VERSION})
        self.assertRegex(metadata["APP_VERSION"], r"^\d+\.\d+\.\d+$")
