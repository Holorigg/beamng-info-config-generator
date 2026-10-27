import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from lupa.lua51 import LuaRuntime

from rls_contracts import OVERHAUL_LAYOUT, RlsInstallation
from rls_patch import (
    LUA_EXTENSION,
    MANIFEST,
    OWNER,
    PATCH_NAME,
    install_patch,
    read_patch,
    set_patch_enabled,
)


class PatchLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.mods = Path(self.temporary.name)
        self.rls_archive = self.mods / "repo" / "rls.zip"
        self.rls_archive.parent.mkdir()
        self._write_rls_archive()
        self.installation = RlsInstallation(
            path=str(self.rls_archive), version="2.7.2", config={}, pool_hash="pool-hash", supported=False,
        )

    def _write_rls_archive(self, config_lua="M.getContractVehicleModels = function() return {} end"):
        with zipfile.ZipFile(self.rls_archive, "w") as archive:
            archive.writestr("lua/ge/extensions/gameplay/fre/config.lua", config_lua)
            archive.writestr("gameplay/fre/freProgression.config.json", "{}")
            archive.writestr("lua/ge/extensions/gameplay/events/freContracts/vehiclePool.lua", "return {}")

    def install(self, model_keys, installation=None):
        return install_patch(self.mods, installation or self.installation, model_keys)

    def tearDown(self):
        self.temporary.cleanup()

    def test_install_read_enable_disable_and_dated_backups(self):
        enabled = self.install(["Car_A", "car_a", "Van-1"])
        self.assertEqual(enabled, self.mods / PATCH_NAME)
        self.assertEqual(read_patch(self.mods)["models"], ["car_a", "van-1"])
        self.assertTrue(read_patch(self.mods)["enabled"])
        self.assertEqual(list(self.mods.glob(f"{PATCH_NAME}.*.bak")), [])

        original = enabled.read_bytes()
        disabled = set_patch_enabled(self.mods, False)
        self.assertEqual(disabled, self.mods / (PATCH_NAME + ".disabled"))
        self.assertFalse(read_patch(self.mods)["enabled"])
        backups = list(self.mods.glob(f"{PATCH_NAME}.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertRegex(backups[0].name, rf"^{PATCH_NAME}\.\d{{8}}-\d{{6}}-\d{{6}}\.bak$")

        disabled_bytes = disabled.read_bytes()
        enabled = set_patch_enabled(self.mods, True)
        self.assertEqual(enabled, self.mods / PATCH_NAME)
        self.assertTrue(read_patch(self.mods)["enabled"])
        backups = list(self.mods.glob(f"{PATCH_NAME}.*.bak"))
        self.assertEqual(len(backups), 2)
        self.assertIn(disabled_bytes, [path.read_bytes() for path in backups])

        updated = self.install(["New_Model"])
        self.assertEqual(updated, enabled)
        self.assertEqual(read_patch(self.mods)["models"], ["new_model"])
        self.assertEqual(len(list(self.mods.glob(f"{PATCH_NAME}.*.bak"))), 3)

    def test_update_preserves_intentionally_disabled_state(self):
        self.install(["first"])
        disabled = set_patch_enabled(self.mods, False)
        previous = disabled.read_bytes()

        result = self.install(["second"])

        self.assertEqual(result, disabled)
        self.assertTrue(disabled.exists())
        self.assertFalse((self.mods / PATCH_NAME).exists())
        self.assertFalse(read_patch(self.mods)["enabled"])
        self.assertEqual(read_patch(self.mods)["models"], ["second"])
        self.assertIn(previous, [path.read_bytes() for path in self.mods.glob(f"{PATCH_NAME}.*.bak")])

    def test_unknown_version_is_permitted_and_recorded_unverified(self):
        installation = RlsInstallation(
            path=str(self.rls_archive), version="", config={},
            pool_hash=self.installation.pool_hash, supported=False,
        )
        self.install(["vehicle"], installation)
        patch = read_patch(self.mods)
        self.assertEqual(patch["rlsVersion"], "")
        self.assertEqual(patch["rlsPoolHash"], hashlib.sha256(b"return {}").hexdigest())
        self.assertFalse(patch["verifiedRules"])

    def test_verified_rules_require_source_pool_hash_to_match_known_hash(self):
        source_hash = hashlib.sha256(b"return {}").hexdigest()
        installation = RlsInstallation(
            path=str(self.rls_archive), version="2.7.2", config={},
            pool_hash="stale-discovery-hash", supported=True,
        )

        with patch.dict("rls_patch.KNOWN_POOL_HASHES", {}, clear=True):
            self.install(["vehicle"], installation)
            unverified = read_patch(self.mods)
        self.assertEqual(unverified["rlsPoolHash"], source_hash)
        self.assertFalse(unverified["verifiedRules"])

        with patch.dict("rls_patch.KNOWN_POOL_HASHES", {source_hash: "2.7.2"}, clear=True):
            self.install(["vehicle"], installation)
        verified = read_patch(self.mods)
        self.assertEqual(verified["rlsPoolHash"], source_hash)
        self.assertTrue(verified["verifiedRules"])

    def test_rls_28_overhaul_layout_installs_and_records_layout(self):
        archive_path = self.mods / "repo" / "rls_28.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(OVERHAUL_LAYOUT.config_lua,
                             "M.getContractVehicleModels = function() return {} end")
            archive.writestr(OVERHAUL_LAYOUT.progression, "{}")
            archive.writestr(OVERHAUL_LAYOUT.pool, "return {}")
        installation = RlsInstallation(
            path=str(archive_path), version="2.8.0", config={}, pool_hash="pool-hash",
            supported=False, layout=OVERHAUL_LAYOUT,
        )
        self.install(["vehicle"], installation)
        data = read_patch(self.mods)
        self.assertEqual(data["models"], ["vehicle"])
        self.assertEqual(data["rlsLayout"], "2.8")
        self.assertEqual(data["rlsPoolHash"], hashlib.sha256(b"return {}").hexdigest())

    def test_legacy_installation_still_reads_legacy_members(self):
        self.install(["vehicle"])
        self.assertEqual(read_patch(self.mods)["rlsLayout"], "2.7")

    def test_invalid_model_keys_are_rejected(self):
        for keys in ([], [""], ["two words"], ["bad/key"], ["café"], [None], [1]):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                self.install(keys)
        self.assertFalse((self.mods / PATCH_NAME).exists())

    def test_unknown_enabled_or_disabled_file_collision_is_refused(self):
        for name in (PATCH_NAME, PATCH_NAME + ".disabled"):
            with self.subTest(name=name):
                path = self.mods / name
                path.write_bytes(b"unmanaged contents")
                with self.assertRaises(ValueError):
                    self.install(["vehicle"])
                self.assertEqual(path.read_bytes(), b"unmanaged contents")
                path.unlink()

    def test_both_enabled_and_disabled_files_are_reported_as_a_collision(self):
        (self.mods / PATCH_NAME).write_bytes(b"enabled collision")
        (self.mods / (PATCH_NAME + ".disabled")).write_bytes(b"disabled collision")
        with self.assertRaisesRegex(ValueError, "Both enabled and disabled"):
            read_patch(self.mods)

    def test_install_never_writes_rls_or_vehicle_archives(self):
        vehicle = self.mods / "vehicle.zip"
        with zipfile.ZipFile(vehicle, "w") as archive:
            archive.writestr("sentinel.bin", b"vehicle archive bytes")
        originals = {path: hashlib.sha256(path.read_bytes()).digest()
                     for path in (self.rls_archive, vehicle)}

        self.install(["vehicle"])
        set_patch_enabled(self.mods, False)
        self.install(["replacement"])

        self.assertEqual({path: hashlib.sha256(path.read_bytes()).digest() for path in originals}, originals)
        self.assertFalse(list(self.rls_archive.parent.glob("rls.zip.*.bak")))
        self.assertFalse(list(self.mods.glob("vehicle.zip.*.bak")))
        with zipfile.ZipFile(vehicle) as archive:
            self.assertEqual(archive.read("sentinel.bin"), b"vehicle archive bytes")

    def test_install_refuses_source_missing_contract_model_api(self):
        self._write_rls_archive("local M = {}\nreturn M")
        with self.assertRaisesRegex(ValueError, "contract model API"):
            self.install(["vehicle"])
        self.assertFalse((self.mods / PATCH_NAME).exists())

    def test_install_does_not_change_source_archive_hash(self):
        before = hashlib.sha256(self.rls_archive.read_bytes()).digest()
        self.install(["vehicle"])
        self.assertEqual(hashlib.sha256(self.rls_archive.read_bytes()).digest(), before)

    def test_read_rejects_an_unmanaged_patch(self):
        path = self.mods / PATCH_NAME
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(MANIFEST, json.dumps({"owner": "someone-else", "schema": 1, "models": []}))
        with self.assertRaisesRegex(ValueError, "Unrecognized contract patch"):
            read_patch(self.mods)


class LuaRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.globals = self.lua.globals()
        self.manifest_exists = True
        self.config_file_exists = True
        self.logs = []
        self.data = {"owner": OWNER, "schema": 1, "models": ["CAR_A", "car_b", "Car_B"],
                     "verifiedRules": True}
        self.config = self.lua.table()
        self.base = self.lua.table_from(["Car_A", "Van"])
        self.base_calls = 0

        self.config_file = "/lua/ge/extensions/gameplay/fre/config.lua"
        self.required = []

        def file_exists(_fs, path):
            if path == "/settings/infogen_rls_contracts.json":
                return self.manifest_exists
            if path == self.config_file:
                return self.config_file_exists
            return False

        def json_read_file(_path):
            return self.lua.table_from({
                "owner": self.data["owner"],
                "schema": self.data["schema"],
                "models": self.lua.table_from(self.data["models"]),
                "verifiedRules": self.data.get("verifiedRules", True),
            })

        self.globals.FS = self.lua.table_from({"fileExists": file_exists})
        self.globals.jsonReadFile = json_read_file
        self.globals.log = lambda *args: self.logs.append(args)
        def require(name):
            self.required.append(name)
            return self.config

        self.globals.require = require
        self.config.getContractVehicleModels = self.lua.eval(
            "function(callback) return function(...) return callback(...) end end"
        )(lambda *_args: self._base_models())
        self.original_getter = self.config.getContractVehicleModels
        self.extension = self.lua.execute(LUA_EXTENSION)

    def _base_models(self):
        self.base_calls += 1
        return self.base

    def _update_to_attach(self):
        self.extension.onUpdate(0.5)

    @staticmethod
    def _list(lua_table):
        return [lua_table[index] for index in range(1, len(lua_table) + 1)]

    def _lua_equal(self, left, right):
        return self.lua.eval("function(a, b) return a == b end")(left, right)

    def test_update_threshold_delays_install_and_wrapper_preserves_base(self):
        original = self.config.getContractVehicleModels
        self.extension.onUpdate(0.49)
        self.assertTrue(self._lua_equal(self.config.getContractVehicleModels, original))

        self.extension.onUpdate(0.01)
        wrapper = self.config.getContractVehicleModels
        self.assertNotEqual(wrapper, original)
        result = wrapper("ignored")
        self.assertEqual(self._list(result), ["Car_A", "Van", "car_b"])
        self.assertEqual(self._list(self.base), ["Car_A", "Van"])
        self.assertEqual(self.base_calls, 1)

    def test_each_call_returns_a_fresh_copy_without_mutating_base(self):
        self._update_to_attach()
        wrapper = self.config.getContractVehicleModels
        first = wrapper()
        first[1] = "changed"
        second = wrapper()
        self.assertNotEqual(first, second)
        self.assertEqual(self._list(second), ["Car_A", "Van", "car_b"])
        self.assertEqual(self._list(self.base), ["Car_A", "Van"])

    def test_empty_base_uses_rls_fallback_without_additions(self):
        self.base = self.lua.table()
        self._update_to_attach()
        result = self.config.getContractVehicleModels()
        self.assertEqual(len(result), 0)
        self.assertEqual(self._list(self.base), [])

    def test_unload_restores_original_only_while_our_wrapper_is_installed(self):
        original = self.config.getContractVehicleModels
        self._update_to_attach()
        wrapper = self.config.getContractVehicleModels
        self.extension.onExtensionUnloaded()
        self.assertTrue(self._lua_equal(self.config.getContractVehicleModels, original))
        self.assertNotEqual(wrapper, original)

        self._update_to_attach()
        foreign = lambda: self.lua.table()
        self.config.getContractVehicleModels = foreign
        self.extension.onExtensionUnloaded()
        self.assertEqual(self.config.getContractVehicleModels, foreign)

    def test_missing_manifest_detaches_without_error(self):
        self._update_to_attach()
        self.manifest_exists = False
        self.extension.onUpdate(0.5)
        self.assertTrue(self._lua_equal(self.config.getContractVehicleModels, self.original_getter))
        self.assertEqual(len(self.logs), 1)

    def test_legacy_config_module_is_required_for_rls_27(self):
        self._update_to_attach()
        self.assertEqual(self.required, ["gameplay/fre/config"])

    def test_overhaul_config_module_is_required_for_rls_28(self):
        self.config_file = "/lua/ge/extensions/overhaul/events/freConfig.lua"
        self._update_to_attach()
        self.assertEqual(self.required, ["overhaul/events/freConfig"])
        self.assertEqual(self._list(self.config.getContractVehicleModels()), ["Car_A", "Van", "car_b"])

    def test_no_rls_config_file_is_a_noop(self):
        self.config_file_exists = False
        original = self.config.getContractVehicleModels
        self._update_to_attach()
        self.assertTrue(self._lua_equal(self.config.getContractVehicleModels, original))
        self.assertEqual(self.logs, [])

    def test_missing_getter_logs_once_and_does_not_error(self):
        self.config.getContractVehicleModels = None
        self._update_to_attach()
        self.extension.onUpdate(0.5)
        self.assertIsNone(self.config.getContractVehicleModels)
        self.assertEqual(len(self.logs), 1)

    def test_reloaded_config_module_gets_a_new_wrapper(self):
        self._update_to_attach()
        old_config = self.config
        old_wrapper = old_config.getContractVehicleModels
        new_config = self.lua.table()
        new_base = self.lua.table_from(["Other"])
        new_config.getContractVehicleModels = self.lua.eval(
            "function(callback) return function(...) return callback(...) end end"
        )(lambda: new_base)
        self.config = new_config

        self.extension.onUpdate(0.5)

        self.assertIsNot(old_config, new_config)
        self.assertFalse(self._lua_equal(new_config.getContractVehicleModels, old_wrapper))
        self.assertEqual(self._list(new_config.getContractVehicleModels()), ["Other", "car_a", "car_b"])
        self.assertEqual(self._list(old_config.getContractVehicleModels()), ["Car_A", "Van"])

    def test_on_update_does_not_rewrap_when_another_wrapper_covers_ours(self):
        self._update_to_attach()
        external_wrapper = self.lua.eval(
            "function(callback) return function(...) return callback(...) end end"
        )(self.config.getContractVehicleModels)
        self.config.getContractVehicleModels = external_wrapper

        self.extension.onUpdate(0.5)

        self.assertTrue(self._lua_equal(self.config.getContractVehicleModels, external_wrapper))
        self.assertEqual(self._list(external_wrapper()), ["Car_A", "Van", "car_b"])
        self.assertEqual(self.base_calls, 1)

    def test_invalid_manifest_data_does_not_install_wrapper(self):
        self.data["owner"] = "not-ours"
        original = self.config.getContractVehicleModels
        self._update_to_attach()
        self.assertTrue(self._lua_equal(self.config.getContractVehicleModels, original))


if __name__ == "__main__":
    unittest.main()
