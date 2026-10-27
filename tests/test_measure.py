import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

import measure
from storage import OperationCancelled

# A probe result recorded from BeamNG.drive 0.40.3 for the stock etk800 854_190d_A.
ETK_PROBE = {
    "weight": 1644.03, "power": 192.79, "torque": 404.77, "powerRPM": 4001, "torqueRPM": 2368,
    "powerBand": [3790, 4210], "torqueBand": [1640, 2860], "turbo": True, "supercharger": False,
    "nitrous": False, "gearboxes": ["automaticGearbox"], "layout": "RWD", "electric": False,
    "storages": [{"type": "fuelTank", "energy": "diesel"}],
}


def entry(pc_path, source_path, source="zip", name="cfg"):
    return SimpleNamespace(pc_path=pc_path, source_path=str(source_path), source=source, config_name=name)


class ConversionTests(unittest.TestCase):
    def test_probe_converts_like_stock_info_files(self):
        info = measure.to_info(ETK_PROBE)
        self.assertEqual(info["Power"], 192)
        self.assertEqual(info["Torque"], 405)
        self.assertEqual(info["Weight"], 1645)
        self.assertEqual(info["PowerPeakRPM"], 3800)
        self.assertEqual(info["TorquePeakRPM"], "1650 - 2850")
        self.assertEqual((info["Drivetrain"], info["Transmission"], info["Fuel Type"], info["Induction Type"]),
                         ("RWD", "Automatic", "Diesel", "Turbo"))
        self.assertEqual(info["Propulsion"], "ICE")
        self.assertAlmostEqual(info["Weight/Power"], 1645 / 192, places=3)

    def test_electric_and_supercharged_variants(self):
        ev = measure.to_info({"weight": 1800, "power": 300, "torque": 400, "electric": True,
                              "storages": [{"type": "electricBattery"}], "gearboxes": ["electricGearbox"]})
        self.assertEqual((ev["Fuel Type"], ev["Propulsion"]), ("Battery", "Electric"))
        self.assertNotIn("Induction Type", ev)
        self.assertEqual(ev["Transmission"], "Other")
        sc = measure.to_info({"power": 400, "supercharger": True, "nitrous": True,
                              "storages": [{"type": "fuelTank", "energy": "gasoline"}, {"type": "n2oTank"}]})
        self.assertEqual((sc["Induction Type"], sc["Fuel Type"]), ("SC + N2O", "Gasoline"))

    def test_chassis_without_driven_wheels_has_no_drivetrain(self):
        info = measure.to_info({"power": 277.8, "layout": "4x0", "gearboxes": {}})
        self.assertNotIn("Drivetrain", info)
        self.assertNotIn("Transmission", info)

    def test_trailer_without_engine_only_reports_weight(self):
        self.assertEqual(measure.to_info({"weight": 812.2, "power": 0, "torque": 0, "layout": "Other"}),
                         {"Weight": 815})

    def test_config_key_and_matching(self):
        zipped = entry("vehicles/etk800/854_190d_A.pc", "a.zip")
        folder = entry(str(Path("C:/mods/x/vehicles/car/Sport Edition.pc")), "C:/mods/x", "folder")
        self.assertEqual(measure.config_key(zipped), ("etk800", "854_190d_A"))
        self.assertEqual(measure.config_key(folder), ("car", "Sport Edition"))
        self.assertIsNone(measure.config_key(entry("other/file.pc", "a.zip")))
        document = {"results": [{"model": "ETK800", "config": "854_190d_a", "data": ETK_PROBE},
                                {"model": "car", "config": "Sport Edition", "error": "spawn: bad"}]}
        measured, errors = measure.match_results([zipped, folder, entry("vehicles/van/a.pc", "b.zip")], document)
        self.assertEqual(measured[id(zipped)]["Power"], 192)
        self.assertEqual(len(errors), 2)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / "mods" / "car pack.zip"
        self.archive.parent.mkdir()
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("vehicles/car/base.pc", "{}")
        self.folder = self.root / "mods" / "unpacked" / "van"
        (self.folder / "vehicles" / "van").mkdir(parents=True)
        (self.folder / "vehicles" / "van" / "work.pc").write_text("{}")
        self.entries = [entry("vehicles/car/base.pc", self.archive),
                        entry(str(self.folder / "vehicles" / "van" / "work.pc"), self.folder, "folder")]

    def tearDown(self):
        self.temp.cleanup()

    def test_prepare_links_mods_and_writes_addon_job(self):
        session = measure.prepare(self.entries, base_dir=self.root)
        mods = session.user / "current" / "mods"
        self.assertEqual((mods / "car pack.zip").read_bytes(), self.archive.read_bytes())
        self.assertTrue((mods / "unpacked" / "van" / "vehicles" / "van" / "work.pc").is_file())
        with zipfile.ZipFile(mods / measure.ADDON_NAME) as addon:
            job = json.loads(addon.read(measure.JOB_PATH))
            names = set(addon.namelist())
        self.assertEqual(job["configs"], [{"model": "car", "config": "base"}, {"model": "van", "config": "work"}])
        self.assertIn("lua/ge/extensions/infogenMeasure.lua", names)
        self.assertTrue(measure.cleanup(session))
        self.assertFalse(session.root.exists())
        # Removing the temporary folder must never touch the linked originals.
        self.assertTrue(self.archive.is_file())
        self.assertTrue((self.folder / "vehicles" / "van" / "work.pc").is_file())

    def test_wait_reads_results_and_stops_on_cancel(self):
        session = measure.prepare(self.entries[:1], base_dir=self.root)
        session.result_path.parent.mkdir(parents=True)
        session.result_path.write_text(json.dumps({"done": True, "results": [{"model": "car"}]}))
        seen = []
        result = measure.wait(session, progress=lambda done, total, text: seen.append((done, total)), poll=0.01)
        self.assertTrue(result["done"])
        self.assertEqual(seen[-1], (1, 1))
        session.result_path.write_text(json.dumps({"done": False, "results": []}))
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(OperationCancelled):
            measure.wait(session, cancel, poll=0.01)
        measure.cleanup(session)

    def test_game_closing_early_is_reported_with_its_log(self):
        session = measure.prepare(self.entries[:1], base_dir=self.root)
        session.process = SimpleNamespace(poll=lambda: 16777218, returncode=16777218)
        (session.user / "current" / "beamng.log").write_text("line one\nfatal problem\n")
        with self.assertRaisesRegex(RuntimeError, r"exit code 16777218(.|\n)*fatal problem"):
            measure.wait(session, poll=0.01)
        session.result_path.parent.mkdir(parents=True)
        session.result_path.write_text(json.dumps({"done": False, "results": [{"model": "car"}]}))
        self.assertEqual(len(measure.wait(session, poll=0.01)["results"]), 1)
        measure.cleanup(session)

    def test_portable_profile_redirect_is_undone_for_the_game(self):
        env = {"USERPROFILE": "D:/portable/data", "HOME": "D:/portable/data", "PATH": "x",
               "BEAMNG_INFOGEN_ORIGINAL_USERPROFILE": "C:/Users/me", "BEAMNG_INFOGEN_ORIGINAL_HOME": ""}
        game = measure.game_environment(env)
        self.assertEqual(game["USERPROFILE"], "C:/Users/me")
        self.assertNotIn("HOME", game)
        self.assertNotIn("BEAMNG_INFOGEN_ORIGINAL_USERPROFILE", game)
        self.assertEqual(measure.game_environment({"USERPROFILE": "C:/Users/me"}), {"USERPROFILE": "C:/Users/me"})

    def test_nothing_measurable_is_rejected(self):
        with self.assertRaises(ValueError):
            measure.prepare([entry("misc/file.pc", self.archive)], base_dir=self.root)


class LuaTests(unittest.TestCase):
    def test_addon_lua_compiles(self):
        from lupa.lua51 import LuaRuntime
        runtime = LuaRuntime()
        compile_lua = runtime.eval("function(code) local f, err = loadstring(code); return f ~= nil, err end")
        for code in (measure.MOD_SCRIPT, measure.GE_EXTENSION):
            ok, error = compile_lua(code)
            self.assertTrue(ok, error)
        probe = measure.GE_EXTENSION.split("local vehicleProbe = [[", 1)[1].split("]]", 1)[0]
        ok, error = compile_lua(probe)
        self.assertTrue(ok, error)


if __name__ == "__main__":
    unittest.main()
