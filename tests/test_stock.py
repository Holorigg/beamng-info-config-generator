import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import game_paths
import stock


def make_game(root: Path) -> Path:
    game = root / "BeamNG.drive"
    vehicles = game / "content" / "vehicles"
    vehicles.mkdir(parents=True)
    with zipfile.ZipFile(vehicles / "sedan.zip", "w") as archive:
        archive.writestr("vehicles/sedan/info.json", json.dumps({
            "Brand": "Ibishu", "Body Style": "Sedan", "InsuranceClass": "dailyDriver",
            "Region": "northAmerica", "Years": {"min": 1988, "max": 1991}, "defaultPaintName1": "Blue",
        }))
        for name, value, power, kind in (("base", 20200, 100, "Factory"), ("lx", 30100, 140, "Factory"),
                                         ("race", 90000, 300, "Race")):
            archive.writestr(f"vehicles/sedan/{name}.pc", "{}")
            archive.writestr(f"vehicles/sedan/info_{name}.json", json.dumps({
                "Config Type": kind, "Value": value, "Power": power, "Weight": 1300}))
        archive.writestr("vehicles/sedan/info_orphan.json", json.dumps({"Value": 999999}))
    (game / "integrity.json").write_text('{"buildinfo": "x", "version": "0.40.3.0"}')
    return game


class StockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = make_game(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_suggestions_use_model_fields_and_factory_medians(self):
        values = stock.suggestions(self.game, "sedan")
        self.assertEqual(values["Value"], 25000)
        self.assertEqual(values["Power"], 120)
        self.assertEqual(values["Weight"], 1300)
        self.assertEqual(values["Years"], {"min": 1988, "max": 1991})
        self.assertEqual(values["InsuranceClass"], "dailyDriver")
        self.assertEqual(values["_configs"], 3)
        self.assertEqual(values["_label"], "Ibishu sedan")

    def test_unknown_model_or_game_returns_nothing(self):
        self.assertEqual(stock.suggestions(self.game, "custom_mod_car"), {})
        self.assertEqual(stock.suggestions("", "sedan"), {})
        self.assertTrue(stock.is_stock_model(self.game, "sedan"))
        self.assertFalse(stock.is_stock_model(self.game, "missing"))

    def test_game_detection_reads_steam_libraries(self):
        steam = Path(self.temp.name) / "Steam"
        library = Path(self.temp.name) / "Library"
        (library / "steamapps" / "common").mkdir(parents=True)
        os.rename(self.game, library / "steamapps" / "common" / "BeamNG.drive")
        (steam / "steamapps").mkdir(parents=True)
        escaped = str(library).replace("\\", "\\\\")
        (steam / "steamapps" / "libraryfolders.vdf").write_text(
            f'"libraryfolders"\n{{\n "1"\n {{\n  "path"  "{escaped}"\n }}\n}}\n')
        with patch.object(game_paths, "_steam_roots", return_value=[steam]):
            found = game_paths.detect_game_dir()
        self.assertEqual(Path(found), library / "steamapps" / "common" / "BeamNG.drive")
        self.assertEqual(game_paths.game_version(found), "0.40.3.0")
        with patch.object(game_paths, "_steam_roots", return_value=[Path(self.temp.name) / "none"]):
            self.assertEqual(game_paths.detect_game_dir(), "")


class StockEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        import app as app_module
        from scanner import scan_mods_folder
        self.app_module = app_module
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.game = make_game(root)
        settings = root / "settings.json"
        settings.write_text(json.dumps({"game_dir": str(self.game)}))
        self.patches = [patch.object(app_module, "SETTINGS_FILE", settings),
                        patch.object(app_module, "confirm_bulk",
                                     side_effect=lambda _parent, _title, pairs, *args: (pairs, False))]
        for item in self.patches:
            item.start()
        for model in ("sedan", "custom"):
            folder = root / "mods" / f"{model}_pack" / "vehicles" / model
            folder.mkdir(parents=True)
            (folder / "street.pc").write_text("{}")
        self.window = app_module.App()
        self.window.mods_data = scan_mods_folder(str(root / "mods"))
        self.entries = {e.pc_path.replace("\\", "/").split("/vehicles/")[1].split("/")[0]: e
                        for es in self.window.mods_data.values() for e in es}

    def tearDown(self):
        self.window._form_dirty = self.window._json_dirty = False
        self.window.close()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_stock_button_state_and_fill(self):
        self.window._activate_entry(self.entries["custom"])
        self.assertFalse(self.window.stock_btn.isEnabled())
        self.window._activate_entry(self.entries["sedan"])
        self.assertTrue(self.window.stock_btn.isEnabled())
        self.window._fill_from_stock()
        self.assertEqual(self.window.w_price_min.text(), "25000")
        self.assertEqual(self.window.w_power.text(), "120")
        self.assertEqual(self.window.w_year_min.text(), "1988")
        self.assertEqual(self.window.w_region.value(), ["northAmerica"])

    def test_generated_files_use_stock_values_only_for_stock_models(self):
        self.window._generate_all_missing()
        sedan = self.entries["sedan"].info_content
        custom = self.entries["custom"].info_content
        self.assertEqual(sedan["Value"], 25000)
        self.assertEqual(sedan["Years"], {"min": 1988, "max": 1991})
        self.assertNotIn("Years", custom)
        self.window._settings["use_stock_data"] = False
        data = self.window._with_stock(self.entries["sedan"], {"Value": 1}, {})
        self.assertEqual(data, {"Value": 1})

    def test_fix_uses_stock_price_only_when_price_is_invalid(self):
        entry = self.entries["sedan"]
        entry.info_content = {"Value": 0}
        self.assertEqual(self.window._stock_price_fix(entry, {"Value": 12345})["Value"], 25000)
        entry.info_content = {"Value": 8000}
        self.assertEqual(self.window._stock_price_fix(entry, {"Value": 8000})["Value"], 8000)

    def test_missing_game_asks_for_folder(self):
        from PySide6.QtWidgets import QMessageBox
        self.window._settings["game_dir"] = ""
        self.window._detected_game = ""
        self.window._activate_entry(self.entries["sedan"])
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                patch.object(self.app_module, "choose_game_dir", return_value=str(self.game)) as choose:
            self.window._fill_from_stock()
        choose.assert_called_once()
        self.assertEqual(self.window._settings["game_dir"], str(self.game))
        self.assertEqual(self.window.w_power.text(), "120")


if __name__ == "__main__":
    unittest.main()
