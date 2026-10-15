import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

import rls_dialog
from rls_contracts import RlsInstallation, VehicleModel
from rls_dialog import ContractsDialog


class ContractsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.installation = RlsInstallation("rls.zip", "future", {
            "contractVehicleModels": ["base"],
            "disciplines": [{"id": "roadracing", "contracts": {
                "contractVehicleConfigTypeWhitelist": ["Race"]}}],
        }, "unverified", False, "Unverified version")
        self.models = [VehicleModel("street", ("Factory",), ("cars.zip",)),
                       VehicleModel("track", ("Race",), ("cars.zip",))]
        self.managed = {"models": ["street", "absent"], "enabled": True}
        self.patches = [
            patch.object(rls_dialog, "discover_rls", return_value=[self.installation]),
            patch.object(rls_dialog, "collect_models", return_value=self.models),
            patch.object(rls_dialog, "read_patch", side_effect=lambda _: self.managed),
        ]
        for item in self.patches:
            item.start()
        self.window = ContractsDialog(str(Path(self.temp.name)), [], {"track"})

    def tearDown(self):
        self.window.close()
        self.qt.processEvents()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_unknown_version_is_warning_not_version_lock(self):
        self.assertTrue(self.window.apply_button.isEnabled())
        self.assertIn("unverified", self.window.installation_selector.currentText())
        self.assertEqual(self.window.table.rowCount(), 2)
        self.assertIn("Needs Race config", self.window.table.item(0, 4).text())

    def test_unchecking_existing_selection_survives_render_and_refresh(self):
        self.window._checkbox_for_key("street").setChecked(False)
        self.window._render()
        self.assertFalse(self.window._checkbox_for_key("street").isChecked())
        self.window.refresh()
        self.assertFalse(self.window._checkbox_for_key("street").isChecked())

    def test_apply_retains_absent_models_and_confirms_unknown_version(self):
        self.window._checkbox_for_key("street").setChecked(False)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question, \
                patch.object(rls_dialog, "install_patch", return_value=Path("addon.zip")) as install:
            self.window._apply_patch()
        self.assertIn("unverified", question.call_args.args[2].lower())
        self.assertEqual(install.call_args.args[2], ["absent", "track"])

    def test_disabled_patch_does_not_count_as_active_pool(self):
        self.managed["enabled"] = False
        self.window.refresh()
        self.assertIn("Not in pool", self.window.table.item(0, 2).text())
        self.assertEqual(self.window.patch_toggle.text(), "Enable patch")

    def test_filter_and_visible_selection_do_not_touch_hidden_rows(self):
        self.window._checkbox_for_key("street").setChecked(False)
        self.window._checkbox_for_key("track").setChecked(False)
        self.window.search.setText("track")
        self.window._toggle_visible()
        self.assertFalse(self.window._checkbox_for_key("street").isChecked())
        self.assertTrue(self.window._checkbox_for_key("track").isChecked())


if __name__ == "__main__":
    unittest.main()
