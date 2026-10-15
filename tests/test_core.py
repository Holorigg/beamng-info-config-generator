import json
import os
import tempfile
import threading
import tracemalloc
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

import json_utils
from generator import generate, fix, validate
from scanner import scan_mods_folder, load_thumbnail
from storage import OperationCancelled, write_text_atomic
from zip_handler import write_many_to_zip


VALID = {"Configuration": "Touring", "Config Type": "Factory", "Drivetrain": "RWD",
         "Transmission": "Manual", "Fuel Type": "Gasoline", "Value": 18000}


class JsonTests(unittest.TestCase):
    def test_string_content_survives_relaxed_json(self):
        text = '{"Description": "literal ,} and ,] and https://example.org", // comment\n"Value": 10,}'
        self.assertEqual(json_utils.loads(text)["Description"], "literal ,} and ,] and https://example.org")

    def test_missing_comma_and_nested_fields(self):
        text = '{"name": "hello"\n"parts": {"one":"two"}\n"values": [1,2,]\n"flag":true}'
        self.assertEqual(json_utils.loads(text), {"name": "hello", "parts": {"one": "two"}, "values": [1, 2], "flag": True})

    def test_bom_and_cp1251(self):
        self.assertEqual(json_utils.load_bytes(b'\xef\xbb\xbf{"a":1}'), {"a": 1})
        self.assertEqual(json_utils.load_bytes('{"name":"\u041c\u0430\u0448\u0438\u043d\u0430"}'.encode("cp1251"))["name"], "\u041c\u0430\u0448\u0438\u043d\u0430")

    def test_non_object_root_rejected(self):
        for value in ("[]", "null", "123", '"text"'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                json_utils.loads(value)

    def test_price_and_required_text_validation(self):
        for value in (0, -1, None, True, "NaN", float("inf"), {}):
            self.assertIn("Value", validate({**VALID, "Value": value}))
        for value in (" ", False, 0, []):
            self.assertIn("Configuration", validate({**VALID, "Configuration": value}))

    def test_fix_preserves_unknown_fields(self):
        data = {**VALID, "Value": "NaN", "Drivetrain": " ", "Years": {"min": 2000}, "paints": ["blue"]}
        result = fix(data, "sport", {}, {})
        self.assertEqual(result["Years"], {"min": 2000})
        self.assertEqual(result["paints"], ["blue"])
        self.assertFalse(validate(result))

    def test_generated_price_positive_and_in_range(self):
        for low, high in ((1, 249), (251, 260), (123, 123), (900, 100)):
            for _ in range(40):
                value = generate("sport", {}, {"price_min": low, "price_max": high})["Value"]
                self.assertGreater(value, 0)
                self.assertLessEqual(value, max(low, high))
                self.assertGreaterEqual(value, min(low, high))


class ZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "mod.zip"
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.comment = b"archive comment"
            archive.writestr("vehicles/", b"")
            info = zipfile.ZipInfo("vehicles/car/keep.bin", (2020, 1, 2, 3, 4, 6))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.comment = b"entry comment"
            info.external_attr = 0o100644 << 16
            archive.writestr(info, b"keep" * 10000)
            archive.writestr("vehicles/car/info_a.json", json.dumps(VALID))

    def tearDown(self):
        self.temp.cleanup()

    def test_append_does_not_read_payloads(self):
        with patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("payload read")):
            write_many_to_zip(self.path, {"vehicles/car/info_b.json": "{}"})
        with zipfile.ZipFile(self.path) as archive:
            self.assertEqual(archive.read("vehicles/car/info_b.json"), b"{}")
            self.assertEqual(archive.comment, b"archive comment")

    def test_replacement_modes_preserve_entries_and_metadata(self):
        for mode in ("auto", "disk", "ram"):
            with self.subTest(mode=mode):
                write_many_to_zip(self.path, {"vehicles/car/info_a.json": '{"Value":200}',
                                              "vehicles/car/info_b.json": "{}"}, mode=mode)
                with zipfile.ZipFile(self.path) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(archive.namelist().count("vehicles/car/info_a.json"), 1)
                    self.assertEqual(archive.read("vehicles/car/keep.bin"), b"keep" * 10000)
                    info = archive.getinfo("vehicles/car/keep.bin")
                    self.assertEqual(info.date_time, (2020, 1, 2, 3, 4, 6))
                    self.assertEqual(info.comment, b"entry comment")
                    self.assertEqual(info.external_attr, 0o100644 << 16)
                    self.assertEqual(archive.comment, b"archive comment")
                    self.assertTrue(archive.getinfo("vehicles/").is_dir())

    def test_append_failure_restores_original_bytes(self):
        original = self.path.read_bytes()
        actual_write = zipfile.ZipFile.writestr
        calls = []
        def fail_second(archive, *args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("simulated full disk")
            return actual_write(archive, *args, **kwargs)
        with patch.object(zipfile.ZipFile, "writestr", fail_second), self.assertRaises(OSError):
            write_many_to_zip(self.path, {"new1.json": "{}", "new2.json": "{}"})
        self.assertEqual(self.path.read_bytes(), original)

    def test_disk_failure_and_cancellation_preserve_original(self):
        original = self.path.read_bytes()
        with patch("zip_handler._copy_zip_entry", side_effect=OSError("disk full")), self.assertRaises(OSError):
            write_many_to_zip(self.path, {"vehicles/car/info_a.json": "{}"})
        self.assertEqual(self.path.read_bytes(), original)
        cancel = threading.Event()
        def progress(*args):
            cancel.set()
        with self.assertRaises(OperationCancelled):
            write_many_to_zip(self.path, {"vehicles/car/info_a.json": "{}"}, cancel=cancel, progress=progress)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.root.glob("*.tmp.zip")))

    def test_append_cancel_rolls_back_committed_members(self):
        original = self.path.read_bytes()
        actual_write = zipfile.ZipFile.writestr
        cancel = threading.Event()
        def cancel_after_write(archive, *args, **kwargs):
            result = actual_write(archive, *args, **kwargs)
            cancel.set()
            return result
        with patch.object(zipfile.ZipFile, "writestr", cancel_after_write), self.assertRaises(OperationCancelled):
            write_many_to_zip(self.path, {"one.json": "{}", "two.json": "{}"}, cancel=cancel)
        self.assertEqual(self.path.read_bytes(), original)

    def test_zip64_streaming_headers(self):
        with patch.object(zipfile, "ZIP64_LIMIT", 1024):
            write_many_to_zip(self.path, {"vehicles/car/info_a.json": "{}"}, mode="disk")
            with zipfile.ZipFile(self.path) as archive:
                self.assertEqual(archive.read("vehicles/car/keep.bin"), b"keep" * 10000)

    def test_corrupt_archive_never_overwritten(self):
        self.path.write_bytes(b"not a zip")
        with self.assertRaises(zipfile.BadZipFile):
            write_many_to_zip(self.path, {"new.json": "{}"})
        self.assertEqual(self.path.read_bytes(), b"not a zip")

    def test_duplicate_replacements_have_one_result(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.path, "a") as archive:
                archive.writestr("vehicles/car/info_a.json", "{}")
        write_many_to_zip(self.path, {"vehicles/car/info_a.json": '{"fixed":true}'})
        with zipfile.ZipFile(self.path) as archive:
            self.assertEqual(archive.namelist().count("vehicles/car/info_a.json"), 1)
            self.assertEqual(archive.read("vehicles/car/info_a.json"), b'{"fixed":true}')

    def test_optional_backup_and_new_archive(self):
        original = self.path.read_bytes()
        write_many_to_zip(self.path, {"new.json": "{}"}, backup=True)
        self.assertEqual(next(self.root.glob("*.bak")).read_bytes(), original)
        path = self.root / "created.zip"
        write_many_to_zip(path, {"hello.json": "{}"})
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(archive.read("hello.json"), b"{}")

    def test_streaming_memory_is_bounded(self):
        with zipfile.ZipFile(self.path, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            with archive.open("large.bin", "w") as stream:
                for _ in range(64):
                    stream.write(b"x" * (1024 * 1024))
        tracemalloc.start()
        try:
            write_many_to_zip(self.path, {"vehicles/car/info_a.json": "{}"}, mode="disk")
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 12 * 1024 * 1024)


class ScannerTests(unittest.TestCase):
    def test_windows_junction_cycle_scans_roots_once(self):
        if os.name != "nt":
            self.skipTest("Windows directory junction test")

        import _winapi

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "mod.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("vehicles/car/base.pc", '{"parts":{}}')

            junction = root / "repo"
            _winapi.CreateJunction(str(root), str(junction))
            try:
                result = scan_mods_folder(str(root))
                self.assertEqual(len(result), 1)
                self.assertEqual(len(next(iter(result.values()))), 1)
            finally:
                junction.rmdir()

    def test_nested_aliases_are_scanned_once_without_directory_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            nested = repo / "unpacked"
            nested.mkdir(parents=True)
            archive_path = nested / "mod.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("vehicles/car/base.pc", '{"parts":{}}')

            try:
                (nested / "alias.zip").symlink_to(archive_path)
                (nested / "repo").symlink_to(repo, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation unavailable: {exc}")

            result = scan_mods_folder(str(root))
            self.assertEqual(len(result), 1)
            self.assertEqual(len(next(iter(result.values()))), 1)

    def test_nested_containers_lazy_thumbnails_and_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repo").mkdir()
            path = root / "repo" / "mod.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("vehicles/car/config_sport.pc", '{"parts":null}')
                archive.writestr("vehicles/car/info_config_sport.json", json.dumps(VALID))
                archive.writestr("vehicles/car/config_sport.png", b"thumbnail")
                archive.writestr("vehicles/car/broken.pc", "[]")
                archive.writestr("vehicles/car/bad.pc", '{"parts":{}}')
                archive.writestr("vehicles/car/info_bad.json", '{"broken":')
            (root / "repo" / "corrupt.zip").write_bytes(b"bad")
            issues = []
            result = scan_mods_folder(str(root), issues=issues)
            entries = list(result.values())[0]
            self.assertEqual(len(entries), 2)
            entry = next(e for e in entries if e.config_name == "config_sport")
            self.assertEqual(entry.status, "ok")
            self.assertIsNone(entry.thumbnail)
            self.assertEqual(entry.pc_content, {})
            self.assertEqual(load_thumbnail(entry), b"thumbnail")
            self.assertTrue(next(e for e in entries if e.config_name == "bad").parse_error)
            self.assertEqual(len(issues), 3)

    def test_single_extracted_mod(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "vehicles" / "car"
            folder.mkdir(parents=True)
            (folder / "sport.pc").write_text('{"parts":{}}')
            (folder / "info_sport.json").write_text(json.dumps(VALID))
            result = scan_mods_folder(str(root))
            self.assertEqual(list(result.values())[0][0].status, "ok")

    def test_no_thumbnail_payload_read_during_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mod.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("vehicles/car/base.pc", '{"parts":{}}')
                archive.writestr("vehicles/car/base.png", b"image" * 10000)
            original_read = zipfile.ZipFile.read
            def metadata_only(archive, name, *args, **kwargs):
                self.assertFalse(str(name).endswith(".png"))
                return original_read(archive, name, *args, **kwargs)
            with patch.object(zipfile.ZipFile, "read", metadata_only):
                scan_mods_folder(directory)

    def test_scan_cancellation(self):
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as root, self.assertRaises(OperationCancelled):
            scan_mods_folder(root, cancel=cancel)

    def test_atomic_folder_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "info.json"
            path.write_text("original")
            with patch("storage.os.replace", side_effect=OSError("locked")), self.assertRaises(OSError):
                write_text_atomic(path, "new")
            self.assertEqual(path.read_text(), "original")
            self.assertFalse(list(Path(directory).glob("*.tmp")))
