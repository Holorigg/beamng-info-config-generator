"""Capture the actual interface without publishing mod names or local paths."""

import argparse
from io import BytesIO
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageFilter
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

import app as app_module
from scanner import scan_mods_folder


def capture(widget):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    widget.grab().save(buffer, "PNG")
    return Image.open(BytesIO(bytes(data))).convert("RGB")


def obscure(image, box):
    left, top, right, bottom = box
    box = (max(0, left), max(0, top), min(image.width, right), min(image.height, bottom))
    if box[2] > box[0] and box[3] > box[1]:
        image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(12)), box)


def obscure_widget(image, window, widget, inset=0):
    point = widget.mapTo(window, QPoint(0, 0))
    obscure(image, (point.x() + inset, point.y() + inset,
                    point.x() + widget.width() - inset, point.y() + widget.height() - inset))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mods", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/images"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    qt = QApplication([])
    if os.name == "nt":
        for name in ("segoeui.ttf", "segoeuib.ttf", "cour.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / name))
    qt.setStyle("Fusion")
    qt.setStyleSheet(app_module.make_dark_style())
    issues = []
    data = scan_mods_folder(str(args.mods), issues=issues)
    entries = [entry for group in data.values() for entry in group if entry.status == "ok"]
    if not entries:
        raise ValueError("No valid configurations available for a real-data screenshot")
    selected = max(entries, key=lambda entry: sum(bool(entry.info_content.get(key))
                   for key in ("Power", "Torque", "Weight", "Description")))
    with tempfile.TemporaryDirectory() as temporary:
        with patch.object(app_module, "SETTINGS_FILE", Path(temporary) / "settings.json"):
            window = app_module.App()
            window.resize(1280, 900)
            window.folder_edit.setText(str(args.mods))
            window.mods_data = data
            window._collapsed = {name: selected not in group for name, group in data.items()}
            window._selection = {id(selected)}
            window._rebuild_view()
            window._update_status()
            window._activate_entry(selected)
            window.show()
            qt.processEvents()
            for index in range(window.tree.topLevelItemCount()):
                parent = window.tree.topLevelItem(index)
                for child_index in range(parent.childCount()):
                    child = parent.child(child_index)
                    if child.isSelected():
                        window.tree.scrollToItem(child)
            qt.processEvents()
            image = capture(window)
            for widget in (window.folder_edit, window.editor_title, window.source_label,
                           window.w_name, window.w_description):
                obscure_widget(image, window, widget, 4)
            origin = window.tree.viewport().mapTo(window, QPoint(0, 0))
            for index in range(window.tree.topLevelItemCount()):
                parent = window.tree.topLevelItem(index)
                for item in [parent] + [parent.child(i) for i in range(parent.childCount())]:
                    rect = window.tree.visualItemRect(item)
                    if rect.isEmpty() or rect.bottom() < 0 or rect.top() >= window.tree.viewport().height():
                        continue
                    text_inset = 24 if item.parent() else 0
                    obscure(image, (origin.x() + rect.left() + text_inset, origin.y() + rect.top(),
                                    origin.x() + rect.right() - 3, origin.y() + rect.bottom() + 1))
            image.save(args.output / "app-overview.png", optimize=True)
            errors = []
            def settings_capture():
                dialog = qt.activeModalWidget()
                try:
                    capture(dialog).save(args.output / "zip-settings.png", optimize=True)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    dialog.reject()
            QTimer.singleShot(100, settings_capture)
            window._show_settings()
            window.close()
            if errors:
                raise errors[0]
    print(f"Saved two redacted screenshots ({sum(map(len, data.values()))} real configurations scanned)")


if __name__ == "__main__":
    main()
