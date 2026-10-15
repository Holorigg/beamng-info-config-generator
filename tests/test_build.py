import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from build_windows import app_metadata, build_environment, merge_checksum, package_portable
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

    def test_portable_archive_has_single_top_level_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "BeamNG-Info-Config-Generator"
            (bundle / "_internal").mkdir(parents=True)
            (bundle / "data").mkdir()
            (bundle / "app.exe").write_bytes(b"executable")
            (bundle / "_internal" / "library.dll").write_bytes(b"library")
            (bundle / "README.txt").write_text("English instructions", encoding="utf-8")
            (bundle / "LICENSE").write_text("License", encoding="utf-8")
            archive = root / "portable.zip"
            package_portable(bundle, archive)

            with zipfile.ZipFile(archive) as packaged:
                names = packaged.namelist()
            self.assertTrue(names)
            self.assertTrue(all(name.startswith("BeamNG-Info-Config-Generator/") for name in names))
            self.assertIn("BeamNG-Info-Config-Generator/app.exe", names)
            self.assertIn("BeamNG-Info-Config-Generator/_internal/library.dll", names)
            self.assertIn("BeamNG-Info-Config-Generator/README.txt", names)
            self.assertIn("BeamNG-Info-Config-Generator/LICENSE", names)
            self.assertIn("BeamNG-Info-Config-Generator/data/", names)
            self.assertFalse(any("mods_data" in name or "fixture" in name.lower() for name in names))

    def test_checksum_merge_preserves_existing_executable_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "SHA256SUMS.txt"
            manifest.write_text("abc123  beamng-infogen.exe\n", encoding="ascii")
            merge_checksum(manifest, "beamng-infogen-portable.zip", "def456")
            self.assertEqual(manifest.read_text(encoding="ascii"),
                             "abc123  beamng-infogen.exe\ndef456  beamng-infogen-portable.zip\n")
            merge_checksum(manifest, "beamng-infogen-portable.zip", "newhash")
            self.assertEqual(manifest.read_text(encoding="ascii"),
                             "abc123  beamng-infogen.exe\nnewhash  beamng-infogen-portable.zip\n")

    def test_runtime_hook_redirects_home_in_child_process(self):
        root = Path(__file__).resolve().parents[1]
        hook = root / "packaging" / "portable_hook.py"
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "bundle" / "app.exe"
            expected = executable.parent / "data"
            code = (
                "import os, runpy, sys; "
                f"sys.executable = {str(executable)!r}; "
                f"runpy.run_path({str(hook)!r}); "
                "from pathlib import Path; "
                f"assert Path.home().resolve() == Path({str(expected)!r}).resolve(); "
                "assert Path(os.environ['USERPROFILE']) == Path.home(); "
                "assert Path(os.environ['HOME']) == Path.home(); "
                "assert Path.home().is_dir()"
            )
            env = os.environ.copy()
            env["USERPROFILE"] = "outside-user-profile"
            env["HOME"] = "outside-home"
            subprocess.run([sys.executable, "-c", code], env=env, check=True)
