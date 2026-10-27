import json
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path
from types import SimpleNamespace

import rls_contracts
from rls_contracts import (
    RlsInstallation,
    VehicleModel,
    collect_models,
    diagnose,
    discover_rls,
    model_key,
)


def progression_config(**overrides):
    config = {
        "contractVehicleModels": ["car", "blocked", "streetonly"],
        "contracts": {},
        "disciplines": [
            {"id": "drift", "contracts": {"vehicleBlacklist": [],
                                             "contractVehicleConfigTypeWhitelist": ["DriftOnly"]}},
            {"id": "drag", "contracts": {"vehicleBlacklist": []}},
            {"id": "roadracing", "contracts": {
                "vehicleBlacklist": [],
                "contractVehicleConfigTypeWhitelist": ["Race"],
            }},
        ],
    }
    config.update(overrides)
    return config


def entry(pc_path, source_path, *, info=None, source="zip"):
    return SimpleNamespace(
        pc_path=str(pc_path),
        source_path=str(source_path),
        source=source,
        info_content=info,
    )


def write_rls_zip(path, *, config=None, pool=b"test vehicle pool", extra=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(rls_contracts.PROGRESSION_PATH,
                         json.dumps(config if config is not None else progression_config()))
        archive.writestr(rls_contracts.POOL_PATH, pool)
        for name, value in (extra or {}).items():
            archive.writestr(name, value)


class RlsDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "mods"
        self.root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_finds_zip_and_unpacked_installations_deterministically_excluding_exact_ourpatch(self):
        write_rls_zip(self.root / "z_rls_2.7.2.zip")
        write_rls_zip(self.root / "ourpatch_custom.zip")
        write_rls_zip(self.root / "infogen_rls_contracts.zip")
        unpacked = self.root / "unpacked" / "RLS unpacked"
        (unpacked / Path(rls_contracts.PROGRESSION_PATH)).parent.mkdir(parents=True)
        (unpacked / Path(rls_contracts.POOL_PATH)).parent.mkdir(parents=True)
        (unpacked / rls_contracts.PROGRESSION_PATH).write_text(
            json.dumps(progression_config()), encoding="utf-8")
        (unpacked / rls_contracts.POOL_PATH).write_bytes(b"unverified pool")

        installations = discover_rls(self.root)

        self.assertEqual([Path(item.path).name for item in installations],
                         ["ourpatch_custom.zip", "RLS unpacked", "z_rls_2.7.2.zip"])
        self.assertEqual([item.version for item in installations], ["", "", "2.7.2"])
        self.assertTrue(all(isinstance(item.config, dict) for item in installations))

    def test_unknown_hash_and_version_are_warnings_not_discovery_blockers(self):
        archive = self.root / "rls_custom.zip"
        write_rls_zip(archive)

        installation, = discover_rls(self.root)

        self.assertFalse(installation.supported)
        self.assertTrue(installation.issue)
        self.assertEqual(installation.config["contractVehicleModels"], [
            "car", "blocked", "streetonly",
        ])
        rows = diagnose(installation, [VehicleModel("car", ("Race",), ())])
        self.assertEqual(len(rows), 1)
        self.assertIn("estimate", rows[0].race)

    def test_version_can_be_read_from_mod_info(self):
        archive = self.root / "rls.zip"
        write_rls_zip(archive, extra={"mod_info/mod_info.json": b'{"version":"2.7.2"}'})

        installation, = discover_rls(self.root)

        self.assertEqual(installation.version, "2.7.2")

    def test_rls_28_overhaul_layout_is_detected_with_version_file(self):
        layout = rls_contracts.OVERHAUL_LAYOUT
        archive = self.root / "rls_career_overhaul.zip"
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr(layout.progression, json.dumps(progression_config()))
            zf.writestr(layout.pool, b"test vehicle pool")
            zf.writestr(layout.version_file, b'{"version_string": "2.8.0"}')

        installation, = discover_rls(self.root)

        self.assertIs(installation.layout, layout)
        self.assertEqual(installation.version, "2.8.0")
        self.assertFalse(installation.supported)
        self.assertEqual(installation.config["contractVehicleModels"], ["car", "blocked", "streetonly"])

    def test_known_hashes_mark_each_verified_version_supported(self):
        for pool_hash, version in rls_contracts.KNOWN_POOL_HASHES.items():
            with self.subTest(version=version), unittest.mock.patch(
                    "rls_contracts.hashlib.sha256",
                    return_value=SimpleNamespace(hexdigest=lambda value=pool_hash: value)):
                for item in self.root.iterdir():
                    item.unlink()
                write_rls_zip(self.root / f"rls_{version}.zip")
                installation, = discover_rls(self.root)
                self.assertTrue(installation.supported)
                self.assertEqual(installation.issue, "")

    def test_rule_source_and_reported_version_mismatch_warns(self):
        pool_hash = rls_contracts.KNOWN_POOL_SHA256
        with unittest.mock.patch("rls_contracts.hashlib.sha256",
                                 return_value=SimpleNamespace(hexdigest=lambda: pool_hash)):
            write_rls_zip(self.root / "rls_2.8.0.zip")
            installation, = discover_rls(self.root)
        self.assertTrue(installation.supported)
        self.assertIn("matches RLS 2.7.2", installation.issue)

    def test_unpacked_overhaul_folder_is_detected(self):
        layout = rls_contracts.OVERHAUL_LAYOUT
        folder = self.root / "unpacked" / "rls"
        for member, data in ((layout.progression, json.dumps(progression_config()).encode()),
                             (layout.pool, b"pool")):
            target = folder / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        installation, = discover_rls(self.root)
        self.assertIs(installation.layout, layout)

    def test_malformed_zip_is_skipped(self):
        (self.root / "broken.zip").write_bytes(b"not a zip archive")

        self.assertEqual(discover_rls(self.root), [])

class ModelCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_public_model_key_normalizes_absolute_nested_config_path(self):
        nested = self.root / "vehicles" / "ETK800" / "configs" / "track" / "config.pc"
        self.assertEqual(model_key(entry(nested, self.root, source="folder")), "etk800")
        self.assertIsNone(model_key(entry(self.root / "vehicles" / "машина" / "config.pc",
                                          self.root, source="folder")))

    def test_folder_model_info_is_read_at_vehicle_model_root_and_types_are_aggregated(self):
        mod = self.root / "mod"
        nested_config_dir = mod / "vehicles" / "car" / "configs" / "race"
        nested_config_dir.mkdir(parents=True)
        (mod / "vehicles" / "car" / "info.json").write_text(json.dumps({
            "aggregates": {"Config Type": {"Race": True, "Street": True}},
            "Type": "Car",
        }), encoding="utf-8")
        first = nested_config_dir / "race.pc"
        second = nested_config_dir / "street.pc"
        scanned = [
            entry(first, mod, info={"Config Type": "Race"}, source="folder"),
            entry(second, mod, info={"Config Type": "Street"}, source="folder"),
        ]

        models = collect_models(scanned)

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].key, "car")
        self.assertEqual(models[0].config_types, ("Race", "Street"))
        self.assertFalse(models[0].issue)

    def test_duplicate_sources_and_missing_model_info_are_reported(self):
        first_zip = self.root / "first.zip"
        second_zip = self.root / "second.zip"
        for path in (first_zip, second_zip):
            with zipfile.ZipFile(path, "w") as archive:
                if path == first_zip:
                    archive.writestr("vehicles/car/info.json", json.dumps({"Type": "Car"}))
        entries = [
            entry("vehicles/car/config.pc", first_zip, info={"Config Type": "Street"}),
            entry("vehicles/car/other.pc", second_zip, info=None),
        ]

        model, = collect_models(entries)

        self.assertIn("multiple archives", model.issue)
        self.assertIn("Model info missing", model.issue)
        self.assertIn("vanilla-based", model.issue)

    def test_model_exclusion_uses_model_type_category_and_class(self):
        archive = self.root / "types.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("vehicles/trailer/info.json", json.dumps({"Type": "Trailer"}))
            zf.writestr("vehicles/prop/info.json", json.dumps({"Category": "Static Prop"}))
            zf.writestr("vehicles/car/info.json", json.dumps({"Class": "Road"}))
        entries = [entry(f"vehicles/{key}/config.pc", archive, info={})
                   for key in ("trailer", "prop", "car")]

        models = {model.key: model for model in collect_models(entries)}

        self.assertTrue(models["trailer"].excluded)
        self.assertTrue(models["prop"].excluded)
        self.assertFalse(models["car"].excluded)


class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.installation = RlsInstallation(
            path="rls.zip", version="2.7.2", config=progression_config(),
            pool_hash=rls_contracts.KNOWN_POOL_SHA256, supported=True,
        )

    def test_patched_models_remain_in_global_pool_and_only_race_whitelist_filters(self):
        models = [
            VehicleModel("patched", ("DriftOnly",), ("cars.zip",)),
            VehicleModel("streetonly", ("Street",), ("cars.zip",)),
            VehicleModel("racemodel", ("Race",), ("cars.zip",)),
        ]
        self.installation.config["contractVehicleModels"].append("racemodel")

        rows = {row.model.key: row for row in diagnose(
            self.installation, models, patched_models={"patched"})}

        self.assertEqual(rows["patched"].drift, "In pool")
        self.assertEqual(rows["patched"].drag, "In pool")
        self.assertEqual(rows["patched"].race, "Needs Race config")
        self.assertEqual(rows["streetonly"].drift, "Needs Driftonly config")
        self.assertEqual(rows["streetonly"].race, "Needs Race config")
        self.assertEqual(rows["racemodel"].race, "In pool")

    def test_per_discipline_whitelists_are_case_insensitive_and_applied_to_any_discipline(self):
        model = VehicleModel("car", ("street",), ("cars.zip",))

        row, = diagnose(self.installation, [model])

        self.assertEqual(row.drift, "Needs Driftonly config")
        self.assertEqual(row.race, "Needs Race config")
        self.installation.config["disciplines"][2]["contracts"][
            "contractVehicleConfigTypeWhitelist"] = ["street"]
        row, = diagnose(self.installation, [model])
        self.assertEqual(row.drift, "Needs Driftonly config")
        self.assertEqual(row.race, "In pool")

    def test_global_whitelist_is_inherited_but_global_blacklist_is_not(self):
        self.installation.config["contracts"] = {
            "vehicleBlacklist": ["blocked"],
            "contractVehicleConfigTypeWhitelist": ["Common"],
        }
        self.installation.config["disciplines"][0]["contracts"][
            "vehicleBlacklist"] = ["driftblocked"]
        self.installation.config["disciplines"][0]["contracts"][
            "contractVehicleConfigTypeWhitelist"] = ["Common"]
        self.installation.config["disciplines"][2]["contracts"][
            "contractVehicleConfigTypeWhitelist"] = ["Common"]
        self.installation.config["contractVehicleModels"].append("driftblocked")
        models = [
            VehicleModel("blocked", ("Common",), ()),
            VehicleModel("driftblocked", ("Common",), ()),
        ]

        rows = {row.model.key: row for row in diagnose(self.installation, models)}

        self.assertEqual(rows["blocked"].drift, "In pool")
        self.assertEqual(rows["blocked"].drag, "In pool")
        self.assertEqual(rows["blocked"].race, "In pool")
        self.assertEqual(rows["driftblocked"].drift, "Blacklisted")
        self.assertEqual(rows["driftblocked"].drag, "In pool")

    def test_empty_configured_list_falls_back_to_all_supplied_known_models(self):
        self.installation.config["contractVehicleModels"] = []
        model = VehicleModel("not-listed-in-config", ("Race", "DriftOnly"), ())

        row, = diagnose(self.installation, [model])

        self.assertEqual((row.drift, row.drag, row.race), ("In pool", "In pool", "In pool"))

    def test_missing_model_metadata_makes_config_type_eligibility_unverified(self):
        model = VehicleModel(
            "car", (), (), "Model info missing; common for vanilla-based configuration packs")

        row, = diagnose(self.installation, [model])

        self.assertEqual(row.drift, "Config type unverified")
        self.assertEqual(row.race, "Config type unverified")

    def test_excluded_model_precedes_pool_and_type_checks(self):
        model = VehicleModel("car", ("Street",), (), excluded=True)

        row, = diagnose(self.installation, [model])

        self.assertEqual((row.drift, row.drag, row.race),
                         ("Excluded model", "Excluded model", "Excluded model"))

    def test_unknown_hash_and_version_keep_diagnosis_with_warning(self):
        installation = RlsInstallation(
            path="unknown.zip", version="", config=progression_config(),
            pool_hash="0" * 64, supported=False, issue="unverified source",
        )
        model = VehicleModel("car", ("Race",), ())

        row, = diagnose(installation, [model])

        self.assertIn("estimate", row.drift)
        self.assertIn("estimate", row.race)


if __name__ == "__main__":
    unittest.main()
