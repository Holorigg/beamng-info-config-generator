import ast
import os
import string
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import i18n
from i18n_ru import RU

ROOT = Path(__file__).resolve().parents[1]
UI_MODULES = ("app.py", "dialogs.py", "widgets.py", "rls_dialog.py", "workers.py", "about.py", "editor_form.py")


def used_keys():
    keys = set()
    for name in UI_MODULES:
        for node in ast.walk(ast.parse((ROOT / name).read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                keys.add(node.args[0].value)
    return keys


def fields(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_every_interface_string_has_russian_text(self):
        missing = sorted(used_keys() - set(RU))
        self.assertEqual(missing, [])

    def test_placeholders_match(self):
        for key, value in RU.items():
            with self.subTest(key=key):
                self.assertEqual(fields(key), fields(value))

    def test_english_is_default_and_unknown_language_falls_back(self):
        self.assertEqual(i18n.t("Save"), "Save")
        i18n.set_language("ru")
        self.assertEqual(i18n.t("Save"), "Сохранить")
        self.assertEqual(i18n.t("Untranslated text"), "Untranslated text")
        i18n.set_language("xx")
        self.assertEqual(i18n.language(), "en")

    def test_russian_window_builds(self):
        from unittest.mock import patch
        import tempfile
        from PySide6.QtWidgets import QApplication
        import app as app_module
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / "settings.json"
            settings.write_text('{"language": "ru"}', encoding="utf-8")
            with patch.object(app_module, "SETTINGS_FILE", settings):
                window = app_module.App()
                self.assertEqual(window.save_btn.text(), "Сохранить")
                self.assertEqual(window.gen_sel_btn.text(), "Создать для выбранных (0)")
                window.close()


if __name__ == "__main__":
    unittest.main()
