import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import vocabulary
from analyzer import analyze
from generator import generate
from parser import _detect_fuel


class VocabularyTests(unittest.TestCase):
    def test_generated_defaults_use_game_terms(self):
        data = generate("base", {"Fuel Type": "Electric"}, {"induction": "Natural"})
        self.assertEqual(data["Fuel Type"], "Battery")
        self.assertEqual(data["Propulsion"], "Electric")
        self.assertEqual(data["Induction Type"], "NA")
        self.assertNotIn("InsuranceClass", data)

    def test_generated_insurance_class_is_optional(self):
        data = generate("base", {}, {"insurance_class": "prestige"})
        self.assertEqual(data["InsuranceClass"], "prestige")
        self.assertEqual(data["Propulsion"], "ICE")

    def test_electric_engines_detect_as_battery(self):
        self.assertEqual(_detect_fuel({"car_engine": "car_engine_electric"}), "Battery")
        self.assertEqual(_detect_fuel({"car_engine": "car_engine_hybrid"}), "Gasoline")

    def test_canonical_leaves_unknown_values(self):
        self.assertEqual(vocabulary.canonical("Induction Type", "Supercharger"), "SC")
        self.assertEqual(vocabulary.canonical("Induction Type", "Twin Turbo + N2O"), "Twin Turbo + N2O")
        self.assertEqual(vocabulary.canonical("Body Style", "Natural"), "Natural")

    def test_analyzer_flags_legacy_editor_values(self):
        entry = SimpleNamespace(status="ok", parse_error=None, info_path=None, config_name="base",
                                info_content={"Induction Type": "Natural", "Fuel Type": "Battery"})
        warnings = analyze({"mod": [entry]})["mod"][0]["warnings"]
        self.assertTrue(any('"Natural"' in item and '"NA"' in item for item in warnings))
        self.assertFalse(any("Fuel Type" in item for item in warnings))


class EditorFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        import app as app_module
        from scanner import scan_mods_folder
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.settings = patch.object(app_module, "SETTINGS_FILE", root / "settings.json")
        self.settings.start()
        folder = root / "mods" / "example" / "vehicles" / "car"
        folder.mkdir(parents=True)
        (folder / "base.pc").write_text("{}")
        self.info = folder / "info_base.json"
        self.info.write_text(json.dumps({
            "Configuration": "Base", "Config Type": "Factory", "Drivetrain": "RWD",
            "Transmission": "Manual", "Fuel Type": "Gasoline", "Value": 12000,
            "Induction Type": "Natural", "Years": {"min": 1990, "max": 1995},
            "InsuranceClass": "commercial",
        }))
        self.window = app_module.App()
        self.window.mods_data = scan_mods_folder(str(root / "mods"))
        self.entry = next(e for es in self.window.mods_data.values() for e in es)
        self.window._activate_entry(self.entry)

    def tearDown(self):
        self.window._form_dirty = self.window._json_dirty = False
        self.window.close()
        self.settings.stop()
        self.temp.cleanup()

    def saved(self):
        self.assertTrue(self.window._save_current())
        return json.loads(self.info.read_text())

    def test_existing_values_load_without_silent_rewrites(self):
        self.assertEqual(self.window.w_induction.currentText(), "Natural")
        self.assertEqual(self.window.w_insurance.currentData(), "commercial")
        self.assertEqual((self.window.w_year_min.text(), self.window.w_year_max.text()), ("1990", "1995"))
        data = self.saved()
        self.assertEqual(data["Years"], {"min": 1990, "max": 1995})
        self.assertEqual(data["InsuranceClass"], "commercial")

    def test_clearing_optional_fields_removes_them(self):
        self.window.w_year_min.clear()
        self.window.w_year_max.clear()
        self.window.w_insurance.setCurrentIndex(self.window.w_insurance.findData(""))
        data = self.saved()
        self.assertNotIn("Years", data)
        self.assertNotIn("InsuranceClass", data)

    def test_single_year_and_battery_propulsion(self):
        self.window.w_year_min.setText("2001")
        self.window.w_year_max.clear()
        self.window.w_fuel.setCurrentText("Battery")
        data = self.saved()
        self.assertEqual(data["Years"], {"min": 2001, "max": 2001})
        self.assertEqual(data["Propulsion"], "Electric")

    def test_custom_combo_value_is_kept(self):
        self.window.w_config_type.setCurrentText("Showroom")
        self.assertEqual(self.saved()["Config Type"], "Showroom")


if __name__ == "__main__":
    unittest.main()
