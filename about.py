"""Application identity, project links, and bundled license notices."""

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget,
)

from ui_icons import app_icon, icon, resource_path

APP_NAME = "BeamNG Info Config Generator"
APP_AUTHOR = "Holorigg"
APP_VERSION = "1.2.0"
PROJECT_URL = "https://github.com/Holorigg/beamng-info-config-generator"


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.setWindowIcon(app_icon())
        self.resize(560, 440)
        self.setMinimumSize(500, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(16)
        header = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(48, 48))
        mark.setFixedSize(48, 48)
        header.addWidget(mark)
        title = QLabel(APP_NAME)
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        layout.addLayout(header)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        details = QWidget()
        body = QVBoxLayout(details)
        body.setContentsMargins(0, 18, 0, 0)
        body.setSpacing(12)
        author = QLabel(f"Created by {APP_AUTHOR}")
        author.setObjectName("aboutAuthor")
        author.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(author)
        version = QLabel(f"Version: {APP_VERSION}")
        version.setObjectName("muted")
        body.addWidget(version)
        body.addWidget(QLabel("MIT License"))
        credit = QLabel("Icons by Lucide and Feather (ISC / MIT).")
        credit.setObjectName("muted")
        body.addWidget(credit)
        note = QLabel("Independent project. Not affiliated with BeamNG.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        body.addWidget(note)
        body.addStretch()
        links = QHBoxLayout()
        for label, name, url in (("GitHub", "external-link", PROJECT_URL),
                                 ("Report an issue", "bug", f"{PROJECT_URL}/issues")):
            button = QPushButton(label)
            button.setIcon(icon(name))
            button.setIconSize(QSize(18, 18))
            button.setToolTip(url)
            button.clicked.connect(lambda checked=False, address=url: QDesktopServices.openUrl(QUrl(address)))
            links.addWidget(button)
        links.addStretch()
        body.addLayout(links)
        tabs.addTab(details, "About")
        licenses = QTextEdit()
        licenses.setObjectName("aboutLicenses")
        licenses.setReadOnly(True)
        licenses.setPlainText(
            "APPLICATION\n\n" + resource_path("LICENSE").read_text(encoding="utf-8") +
            "\n\nLUCIDE / FEATHER ICONS\n\n" +
            resource_path("icons", "lucide", "LICENSE").read_text(encoding="utf-8")
        )
        tabs.addTab(licenses, "Licenses")
        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("Close")
        close.setIcon(icon("x"))
        close.setIconSize(QSize(18, 18))
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)
