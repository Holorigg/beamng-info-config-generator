import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, QItemSelectionModel
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QMessageBox

import app as app_module
from app import App, make_dark_style
from scanner import scan_mods_folder
from workers import TaskDialog
from about import AboutDialog, APP_AUTHOR, APP_VERSION, PROJECT_URL
from ui_icons import app_icon, icon, resource_path
from test_core import VALID


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        if os.name == "nt" and cls.qt.platformName() == "offscreen":
            for name in ("segoeui.ttf", "segoeuib.ttf", "cour.ttf"):
                QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / name))
        cls.qt.setStyle("Fusion")
        cls.qt.setStyleSheet(make_dark_style())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings_patch = patch.object(app_module, "SETTINGS_FILE", self.root / "settings.json")
        self.settings_patch.start()
        # Bulk previews are modal; accept them unchanged in tests.
        self.bulk_patch = patch.object(app_module, "confirm_bulk",
                                       side_effect=lambda _parent, _title, pairs, *args: (pairs, False))
        self.bulk_preview = self.bulk_patch.start()
        folder = self.root / "mods" / "example" / "vehicles" / "car"
        folder.mkdir(parents=True)
        for name in ("touring", "base", "race"):
            (folder / f"{name}.pc").write_text('{"parts":{"engine":"car_engine_diesel"}}')
        self.data = {**VALID, "Configuration": "Touring Special", "Years": {"min": 2005, "max": 2010},
                     "defaultPaintName1": "Blue", "custom": {"keep": [1, 2, 3]},
                     "Power": 240, "Torque": 400, "Weight": 1600}
        (folder / "info_touring.json").write_text(json.dumps(self.data))
        (folder / "info_base.json").write_text('{"Value":0}')
        self.window = App()
        self.window.mods_data = scan_mods_folder(str(self.root / "mods"))
        self.window._rebuild_view()
        self.window._update_status()
        self.entries = {e.config_name: e for es in self.window.mods_data.values() for e in es}
        self.window.show()
        self.qt.processEvents()

    def tearDown(self):
        self.window._form_dirty = self.window._json_dirty = False
        self.window.close()
        self.qt.processEvents()
        self.settings_patch.stop()
        self.bulk_patch.stop()
        self.temp.cleanup()

    def activate(self, name="touring"):
        self.window._activate_entry(self.entries[name])

    def test_form_save_preserves_display_name_and_unknown_fields(self):
        self.activate()
        self.window.w_description.setPlainText("Edited")
        self.assertTrue(self.window._save_current())
        data = json.loads(Path(self.entries["touring"].info_path).read_text())
        self.assertEqual(data["Configuration"], "Touring Special")
        self.assertEqual(data["Years"], self.data["Years"])
        self.assertEqual(data["custom"], self.data["custom"])
        self.assertEqual(data["defaultPaintName1"], "Blue")
        self.assertEqual(data["Description"], "Edited")
        self.assertFalse(self.window.isWindowModified())

    def test_decimal_stats_survive_form_save(self):
        self.activate()
        self.window.w_weight.setText("1600.125")
        self.assertTrue(self.window._save_current())
        data = json.loads(Path(self.entries["touring"].info_path).read_text())
        self.assertEqual(data["Weight"], 1600.125)

    def test_preview_saves_current_json_draft(self):
        self.activate()
        self.window.editor_tabs.setCurrentIndex(1)
        data = dict(self.data, Description="JSON draft")
        self.window.json_view.set_content(data)
        self.window.editor_tabs.setCurrentIndex(2)
        self.assertTrue(self.window._save_current())
        self.assertEqual(json.loads(Path(self.entries["touring"].info_path).read_text())["Description"], "JSON draft")

    def test_json_draft_roundtrip_and_save(self):
        self.activate()
        self.window.w_description.setPlainText("From form")
        self.window.editor_tabs.setCurrentIndex(1)
        self.window._format_json()
        raw = json.loads(self.window.json_view.get_raw_text())
        self.assertEqual(raw["Description"], "From form")
        raw["Configuration"] = "From JSON"
        raw["custom"]["extra"] = True
        self.window.json_view.set_content(raw)
        self.window.editor_tabs.setCurrentIndex(0)
        self.assertEqual(self.window.w_name.text(), "From JSON")
        self.assertTrue(self.window._save_current())
        self.assertTrue(json.loads(Path(self.entries["touring"].info_path).read_text())["custom"]["extra"])

    def test_invalid_json_does_not_switch_or_save(self):
        self.activate()
        self.window.editor_tabs.setCurrentIndex(1)
        self.window.json_view.set_raw('{"unfinished":')
        original = Path(self.entries["touring"].info_path).read_bytes()
        with patch.object(QMessageBox, "warning"):
            self.window.editor_tabs.setCurrentIndex(0)
            self.assertEqual(self.window.editor_tabs.currentIndex(), 1)
            self.assertFalse(self.window._save_current())
        self.assertEqual(Path(self.entries["touring"].info_path).read_bytes(), original)

    def test_preview_tolerates_invalid_metadata_types(self):
        self.activate()
        self.window._card.update({"Configuration": ["bad"], "Config Type": {"bad": True},
                                  "Description": None, "Value": float("inf")})
        self.assertIn("bad", self.window._card._lbl_name.text())
        self.assertEqual(self.window._card._lbl_desc.text(), "")

    def test_svg_icons_render_visible_pixels_and_disabled_state(self):
        from PySide6.QtGui import QIcon
        for asset in resource_path("icons", "lucide").glob("*.svg"):
            normal = icon(asset.stem).pixmap(32, 32).toImage()
            disabled = icon(asset.stem).pixmap(32, 32, QIcon.Disabled).toImage()
            pixels = [normal.pixelColor(x, y) for y in range(32) for x in range(32)]
            self.assertTrue(any(p.alpha() > 0 for p in pixels), asset.name)
            self.assertTrue(any(normal.pixelColor(x, y) != disabled.pixelColor(x, y)
                                for y in range(32) for x in range(32)), asset.name)
        self.assertFalse(self.window.save_btn.icon().isNull())
        self.assertFalse(self.window.tree.topLevelItem(0).child(0).icon(0).isNull())

    def test_application_icon_sizes_and_release_version(self):
        from PySide6.QtGui import QIcon
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")
        for artwork in (app_icon(), QIcon(str(resource_path("icons", "app.ico")))):
            for size in (16, 24, 32, 48, 128, 256):
                pixmap = artwork.pixmap(size, size)
                self.assertFalse(pixmap.isNull())
                image = pixmap.toImage()
                self.assertGreater(image.pixelColor(size // 2, size // 2).alpha(), 0)
                self.assertLessEqual(image.pixelColor(0, 0).alpha(), 8)

    def test_about_author_licenses_links_and_button(self):
        from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit, QTabWidget
        dialog = AboutDialog(self.window)
        self.assertEqual(dialog.findChild(QLabel, "aboutAuthor").text(), f"Created by {APP_AUTHOR}")
        notice = dialog.findChild(QTextEdit, "aboutLicenses").toPlainText()
        self.assertIn("MIT License", notice)
        self.assertIn("Lucide", notice)
        self.assertIn("Cole Bemis", notice)
        with patch("about.QDesktopServices.openUrl") as open_url:
            buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
            buttons["GitHub"].click()
            self.assertEqual(open_url.call_args.args[0].toString(), PROJECT_URL)
            buttons["Report an issue"].click()
            self.assertEqual(open_url.call_args.args[0].toString(), f"{PROJECT_URL}/issues")
        with patch.object(AboutDialog, "exec", return_value=0) as show:
            self.window.about_btn.click()
            show.assert_called_once()
        dialog.show()
        self.qt.processEvents()
        output = os.environ.get("BEAMNG_SCREENSHOTS")
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            dialog.grab().save(str(Path(output) / "about.png"))
            dialog.findChild(QTabWidget).setCurrentIndex(1)
            self.qt.processEvents()
            dialog.grab().save(str(Path(output) / "about-licenses.png"))
        dialog.close()

    def test_unsaved_cancel_preserves_current_entry(self):
        self.activate()
        self.window.w_description.setPlainText("Unsaved")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel):
            self.assertFalse(self.window._activate_entry(self.entries["race"]))
        self.assertIs(self.window.selected_entry, self.entries["touring"])
        self.assertEqual(self.window.w_description.toPlainText(), "Unsaved")

    def test_search_and_status_filters(self):
        self.window.search_edit.setText("race")
        self.window._rebuild_view()
        self.assertEqual(self.window.tree.topLevelItemCount(), 1)
        self.assertEqual(self.window.tree.topLevelItem(0).childCount(), 1)
        self.window._toggle_filter("missing")
        self.assertEqual(self.window.tree.topLevelItemCount(), 0)

    def test_table_multiple_selection_and_numeric_sort(self):
        self.window._toggle_view()
        self.window.table.selectRow(0)
        model = self.window.table.selectionModel()
        model.select(self.window.table.model().index(1, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        self.window._on_table_selection()
        self.assertEqual(len(self.window._selection), 2)
        from app import _NumberItem
        self.assertTrue(_NumberItem("9") < _NumberItem("100"))

    def test_table_icon_only_status_sort(self):
        from PySide6.QtCore import Qt
        self.window._toggle_view()
        self.window.table.sortItems(0, Qt.AscendingOrder)
        self.assertEqual([self.window.table.item(row, 0).data(Qt.UserRole).status
                          for row in range(3)], ["missing", "bad", "ok"])

    def test_partial_batch_reports_actual_success(self):
        calls = []
        def work(entry):
            if entry.config_name == "base":
                raise OSError("locked file")
        with patch.object(QMessageBox, "warning"):
            result = self.window._run_batch("Test", [self.entries["base"], self.entries["race"]],
                                             work, calls.append)
        self.assertFalse(result)
        self.assertEqual(calls, [1])
        self.assertEqual(self.window._history[-1]["completed"], 1)
        self.assertIn("locked file", self.window._history[-1]["errors"][0])

    def test_worker_error_and_cancel_close_dialog(self):
        def fail(cancel, progress):
            raise ValueError("worker failure")
        worker = TaskDialog("Test", fail, self.window).execute()
        self.assertIn("worker failure", worker.error)
        def wait_cancel(cancel, progress):
            cancel.wait(2)
            from storage import check_cancel
            check_cancel(cancel)
        dialog = TaskDialog("Test", wait_cancel, self.window)
        QTimer.singleShot(30, dialog.cancel)
        self.assertTrue(dialog.execute().cancelled)

    def test_generation_names_and_rescan(self):
        self.window._generate_all_missing()
        self.assertEqual(Path(self.entries["race"].info_path).name, "info_race.json")
        rescanned = scan_mods_folder(str(self.root / "mods"))
        self.assertEqual(next(e for es in rescanned.values() for e in es if e.config_name == "race").status, "ok")

    def test_bulk_preview_scope_backup_and_cancel(self):
        from dialogs import BulkPreviewDialog, describe_change
        base, race = self.entries["base"], self.entries["race"]
        self.assertEqual(describe_change(race, {"Value": 1})[0], "Create")
        self.assertEqual(describe_change(base, {"Value": 5000}), ("Update", ["Value"]))
        pairs = [(base, {"Value": 5000}), (race, {"Value": 1})]
        dialog = BulkPreviewDialog(self.window, "Preview", pairs, {id(race)}, backup=False)
        self.assertEqual(dialog.table.rowCount(), 2)
        self.assertTrue(dialog.backup_note.isVisibleTo(dialog))
        dialog.only_visible.setChecked(True)
        self.assertEqual(dialog.selected_pairs(), [pairs[1]])
        self.assertEqual(dialog.confirm.text(), "Write 1 file")
        dialog.close()
        self.bulk_preview.side_effect = lambda *args: None
        before = race.status
        self.window._generate_all_missing()
        self.assertEqual(race.status, before)

    def test_measure_in_game_writes_reviewed_values(self):
        import measure
        from types import SimpleNamespace
        probe = {"weight": 1501, "power": 201.4, "torque": 352, "layout": "AWD", "turbo": True,
                 "gearboxes": ["dctGearbox"], "storages": [{"type": "fuelTank", "energy": "gasoline"}]}
        self.activate("race")
        session = SimpleNamespace(root=self.root / "unused")
        with patch.object(measure, "prepare", return_value=session), \
                patch.object(measure, "launch") as launch, \
                patch.object(measure, "cleanup") as cleanup, \
                patch.object(measure, "wait", return_value={"done": True, "results": [
                    {"model": "car", "config": "race", "data": probe}]}), \
                patch.object(self.window, "_game_dir", return_value=str(self.root)), \
                patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.window._measure_in_game()
        launch.assert_called_once()
        cleanup.assert_called_once_with(session)
        data = json.loads(Path(self.entries["race"].info_path).read_text())
        self.assertEqual((data["Power"], data["Torque"], data["Weight"]), (201, 355, 1505))
        self.assertEqual((data["Drivetrain"], data["Transmission"], data["Induction Type"]), ("AWD", "DCT", "Turbo"))
        self.assertEqual(self.bulk_preview.call_args.args[1], "Apply measured values")

    def test_bulk_preview_backup_choice_is_saved(self):
        self.bulk_preview.side_effect = lambda _parent, _title, pairs, *args: (pairs, True)
        self.window._generate_all_missing()
        self.assertTrue(json.loads((self.root / "settings.json").read_text())["backup_writes"])

    def test_fix_selected_bad_info_uses_positive_defaults(self):
        self.activate("base")
        self.window._fix_all_bad()
        self.assertFalse(self.entries["base"].missing_fields)
        self.assertGreater(self.entries["base"].info_content["Value"], 0)

    def test_scan_replaces_stale_editor(self):
        self.activate()
        self.window.folder_edit.setText(str(self.root / "mods"))
        self.window._scan()
        self.assertIsNone(self.window.selected_entry)
        self.assertFalse(self.window.save_btn.isEnabled())
        self.assertFalse(self.window.json_view.isEnabled())
        self.assertEqual(len(self.window.mods_data), 1)

    def test_render_sizes_and_json_tab(self):
        self.activate()
        output = os.environ.get("BEAMNG_SCREENSHOTS")
        for width, height in ((1180, 840), (900, 650)):
            self.window.resize(width, height)
            self.qt.processEvents()
            self.assertEqual(self.window.width(), width)
            self.assertGreater(self.window.editor_tabs.width(), 350)
            if output:
                folder = Path(output)
                folder.mkdir(parents=True, exist_ok=True)
                self.window.grab().save(str(folder / f"details-{width}.png"))
        self.window.editor_tabs.setCurrentIndex(1)
        self.window._format_json()
        self.qt.processEvents()
        if output:
            self.window.grab().save(str(Path(output) / "json-900.png"))
