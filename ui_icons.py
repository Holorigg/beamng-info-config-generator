"""Render vendored Lucide SVGs with consistent colors and HiDPI sizes."""

from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def resource_path(*parts):
    return Path(__file__).resolve().parent.joinpath(*parts)


@lru_cache(maxsize=1)
def app_icon():
    result = QIcon(str(resource_path("icons", "app.png")))
    if result.isNull():
        raise ValueError("Application icon could not be loaded")
    return result


@lru_cache(maxsize=128)
def icon(name, color="#dce3e7"):
    svg = ET.parse(resource_path("icons", "lucide", f"{name}.svg")).getroot()
    result = QIcon()
    for mode, tint in ((QIcon.Normal, color), (QIcon.Disabled, "#727a80")):
        svg.set("stroke", tint)
        renderer = QSvgRenderer(ET.tostring(svg))
        if not renderer.isValid():
            raise ValueError(f"Invalid SVG icon: {name}")
        for size in (16, 18, 20, 24, 32, 48, 64, 128):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            result.addPixmap(pixmap, mode)
    return result
