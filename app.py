"""
BeamNG Info Config Generator — PySide6 GUI.
"""
import json
import random
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QItemSelectionModel, QLocale, QSize
from PySide6.QtGui import QColor, QFont, QKeySequence, QPixmap, QShortcut, QIntValidator, QDoubleValidator
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QPushButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QGridLayout,
    QTabWidget, QCheckBox, QDialogButtonBox, QSizePolicy,
)

from analyzer import analyze
from generator import generate, fix, validate
import json_utils
from json_view import JsonView
from scanner import ConfigEntry, scan_mods_folder, load_thumbnail
from zip_handler import write_many_to_zip
from storage import OperationCancelled, check_cancel, write_text_atomic
from theme import make_dark_style as make_dark_style
from workers import TaskDialog
from ui_icons import app_icon, icon
from about import AboutDialog

SETTINGS_FILE = Path.home() / ".beamng_infogen.json"

STATUS_ICON  = {"ok": "circle-check", "bad": "triangle-alert", "missing": "circle-dashed"}
STATUS_COLOR = {"ok": "#4CAF50", "bad": "#E67E22", "missing": "#E74C3C"}

def _load_settings() -> dict:
    try:
        data = json_utils.load_file(SETTINGS_FILE)
        return data
    except (OSError, ValueError):
        return {}


def _save_settings(data: dict):
    write_text_atomic(SETTINGS_FILE, json.dumps(data, indent=2, ensure_ascii=False))


class _NumberItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except (TypeError, ValueError, OverflowError):
            return self.text() < other.text()


class _StatusItem(QTableWidgetItem):
    def __lt__(self, other):
        return self.data(Qt.UserRole + 1) < other.data(Qt.UserRole + 1)


class _CardPreview(QFrame):
    _IMG_W = 144
    _IMG_H = 90

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardPreview")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame#cardPreview {
                background-color: #242b2e;
                border: 1px solid #434f55;
                border-radius: 6px;
            }
        """)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 12, 10)
        outer.setSpacing(12)

        self._lbl_img = QLabel()
        self._lbl_img.setFixedSize(self._IMG_W, self._IMG_H)
        self._lbl_img.setAlignment(Qt.AlignCenter)
        self._lbl_img.setStyleSheet(
            "background-color: #191c1e; border-radius: 4px; border: 1px solid #434f55;"
        )
        outer.addWidget(self._lbl_img)

        info = QVBoxLayout()
        info.setSpacing(3)

        title_row = QHBoxLayout()
        self._lbl_name = QLabel("")
        self._lbl_name.setWordWrap(True)
        self._lbl_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._lbl_name.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self._lbl_name.setStyleSheet("color: #ffffff; background: transparent;")
        title_row.addWidget(self._lbl_name, 1)
        self._lbl_type = QLabel("")
        self._lbl_type.setMaximumWidth(110)
        self._lbl_type.setStyleSheet(
            "color: #c0dfd2; background: #354b43; border-radius: 3px; "
            "padding: 1px 6px; font-size: 9pt;"
        )
        title_row.addWidget(self._lbl_type)
        info.addLayout(title_row)

        self._lbl_row1 = QLabel("")
        self._lbl_row1.setWordWrap(True)
        self._lbl_row1.setStyleSheet("color: #cccccc; background: transparent;")
        info.addWidget(self._lbl_row1)

        self._lbl_row2 = QLabel("")
        self._lbl_row2.setWordWrap(True)
        self._lbl_row2.setStyleSheet("color: #cccccc; background: transparent;")
        info.addWidget(self._lbl_row2)

        self._lbl_stats = QLabel("")
        self._lbl_stats.setWordWrap(True)
        self._lbl_stats.setStyleSheet("color: #b5cea8; background: transparent;")
        info.addWidget(self._lbl_stats)

        self._lbl_desc = QLabel("")
        self._lbl_desc.setStyleSheet("color: #888888; font-style: italic; background: transparent;")
        self._lbl_desc.setWordWrap(True)
        self._lbl_desc.setMaximumHeight(34)
        info.addWidget(self._lbl_desc)

        info.addStretch()
        outer.addLayout(info, 1)

    def set_thumbnail(self, data: bytes):
        if not data:
            self._lbl_img.setText("No preview")
            return
        px = QPixmap()
        px.loadFromData(data)
        if px.isNull():
            self._lbl_img.setText("No preview")
        else:
            self._lbl_img.setPixmap(
                px.scaled(self._IMG_W, self._IMG_H,
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def update(self, data: dict):
        name = str(data.get("Configuration") or "—")
        self._lbl_name.setText(name)
        self._lbl_type.setText(str(data.get("Config Type") or ""))

        value = data.get("Value", "")
        try:
            value_str = f"{int(float(value)):,}".replace(",", " ")
        except (TypeError, ValueError, OverflowError):
            value_str = str(value) if value else "—"

        self._lbl_row1.setText(
            f"  {value_str}     "
            f"  {data.get('Drivetrain', '—')}   "
            f"  {data.get('Fuel Type', '—')}"
        )
        self._lbl_row2.setText(
            f"  {data.get('Transmission', '—')}   "
            f"  {data.get('Induction Type', '—')}   "
            f"  {data.get('Body Style', '—')}"
        )

        parts = []
        if data.get("Power"):   parts.append(f"  {data['Power']} HP")
        if data.get("Torque"):  parts.append(f"  {data['Torque']} Nm")
        if data.get("Weight"):  parts.append(f"  {data['Weight']} kg")
        self._lbl_stats.setText("   ".join(parts) if parts else "")

        desc = str(data.get("Description") or "")
        if len(desc) > 90:
            desc = desc[:87] + "..."
        self._lbl_desc.setText(desc)

    def clear(self):
        self._lbl_img.clear()
        for lbl in (self._lbl_name, self._lbl_type, self._lbl_row1,
                    self._lbl_row2, self._lbl_stats, self._lbl_desc):
            lbl.setText("")


class App(QMainWindow):
    def __init__(self, mods_path: str = None):
        super().__init__()
        self.setWindowTitle("BeamNG Info Config Generator[*]")
        self.setWindowIcon(app_icon())
        self.resize(1180, 840)
        self.setMinimumSize(900, 650)
        self._loading = True
        self._form_dirty = False
        self._json_dirty = False
        self._draft_data = None
        self._previous_tab = 0
        self._busy = False
        self._history = []
        self._settings = _load_settings()
        self._cancel_event = None
        self._operation_progress = None

        self.mods_data: dict[str, list[ConfigEntry]] = {}
        self.selected_entry: Optional[ConfigEntry]   = None
        self._selection: set[int]                    = set()
        self._status_filter: set[str]                = {"ok", "bad", "missing"}
        # mods with all-ok entries are collapsed by default
        self._collapsed: dict[str, bool]             = {}

        self._build_ui()
        self._loading = False
        self._restore_layout()
        self._update_status()

        if mods_path:
            self.folder_edit.setText(mods_path)
            QTimer.singleShot(0, self._scan)
        else:
            self._load_last_path()

        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_current)
        QShortcut(QKeySequence("F5"),     self).activated.connect(self._rescan)

    def _load_last_path(self):
        path = _load_settings().get("last_mods_path", "")
        if path and Path(path).exists():
            self.folder_edit.setText(path)

    def _save_last_path(self, path: str):
        s = _load_settings()
        s["last_mods_path"] = path
        _save_settings(s)

    def _button(self, text, icon_name, slot, primary=False):
        button = QPushButton(text)
        button.setIcon(icon(icon_name))
        button.setIconSize(QSize(18, 18))
        if not text:
            button.setFixedWidth(38)
        button.clicked.connect(slot)
        if primary:
            button.setObjectName("primary")
        return button

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget()
        top.setObjectName("topBar")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(16, 12, 16, 12)
        branding = QHBoxLayout()
        brand = QLabel("BeamNG Info Config Generator")
        brand.setObjectName("brand")
        branding.addWidget(brand)
        branding.addStretch()
        branding.addWidget(self._button("History", "clock-arrow-left", self._show_history))
        branding.addWidget(self._button("Settings", "settings", self._show_settings))
        self.about_btn = self._button("", "info", self._show_about)
        self.about_btn.setToolTip("About")
        self.about_btn.setAccessibleName("About")
        branding.addWidget(self.about_btn)
        top_lay.addLayout(branding)
        path_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Mods directory")
        self.folder_edit.returnPressed.connect(self._scan)
        path_row.addWidget(self.folder_edit, 1)
        self.browse_btn = self._button("Browse", "folder-open", self._browse)
        path_row.addWidget(self.browse_btn)
        self.scan_btn = self._button("Scan", "scan-search", self._scan, True)
        path_row.addWidget(self.scan_btn)
        self.rescan_btn = self._button("", "refresh-cw", self._rescan)
        self.rescan_btn.setToolTip("Rescan")
        self.rescan_btn.setEnabled(False)
        path_row.addWidget(self.rescan_btn)
        top_lay.addLayout(path_row)
        root.addWidget(top)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(5)
        self.splitter.setChildrenCollapsible(False)
        root.addWidget(self.splitter, 1)
        left = QWidget()
        left.setMinimumWidth(320)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(12, 12, 8, 8)
        left_lay.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("Configurations")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()
        self._table_mode = False
        self._view_btn = self._button("", "table-2", self._toggle_view)
        self._view_btn.setToolTip("Table view")
        header.addWidget(self._view_btn)
        left_lay.addLayout(header)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search mods, configs, vehicle details")
        self.search_edit.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(160)
        self._search_timer.timeout.connect(self._rebuild_view)
        self.search_edit.textChanged.connect(lambda: self._search_timer.start())
        left_lay.addWidget(self.search_edit)
        filters = QHBoxLayout()
        filters.setSpacing(5)
        self._filter_btns = {}
        for status, label in (("missing", "Missing"), ("bad", "Incomplete"), ("ok", "Valid")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setToolTip(label)
            btn.clicked.connect(lambda checked=False, s=status: self._toggle_filter(s))
            filters.addWidget(btn)
            self._filter_btns[status] = btn
        left_lay.addLayout(filters)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(16)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.currentItemChanged.connect(self._on_tree_current)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemExpanded.connect(lambda item: self._collapsed.update({item.data(0, Qt.UserRole + 1): False}))
        self.tree.itemCollapsed.connect(lambda item: self._collapsed.update({item.data(0, Qt.UserRole + 1): True}))
        left_lay.addWidget(self.tree, 1)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Status", "Mod", "Config", "Drive", "Fuel", "Trans.", "Type", "Value"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSortingEnabled(True)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.currentCellChanged.connect(lambda row, col, oldrow, oldcol: self._on_table_cell_clicked(row, col))
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.table.hide()
        left_lay.addWidget(self.table, 1)
        self.list_count = QLabel("No configurations")
        self.list_count.setObjectName("muted")
        left_lay.addWidget(self.list_count)
        self.splitter.addWidget(left)

        editor_container = QWidget()
        editor_container.setMinimumWidth(480)
        self._editor_lay = QVBoxLayout(editor_container)
        self._editor_lay.setContentsMargins(16, 12, 16, 8)
        self._editor_lay.setSpacing(8)
        self._build_editor(self._editor_lay)
        self.splitter.addWidget(editor_container)
        self.splitter.setSizes([400, 720])

        bot = QWidget()
        bot.setObjectName("botBar")
        bot_lay = QVBoxLayout(bot)
        bot_lay.setContentsMargins(12, 8, 12, 8)
        actions = QHBoxLayout()
        self.gen_all_btn = self._button("Generate missing", "file-plus", self._generate_all_missing)
        actions.addWidget(self.gen_all_btn)
        self.fix_all_btn = self._button("Fix incomplete", "wrench", self._fix_all_bad)
        actions.addWidget(self.fix_all_btn)
        actions.addWidget(self._button("Analyze", "chart-no-axes-combined", self._show_analyze_dialog))
        self.gen_sel_btn = self._button("Generate selected (0)", "file-plus", self._generate_selected)
        actions.addWidget(self.gen_sel_btn)
        actions.addStretch()
        bot_lay.addLayout(actions)
        self.status_lbl = QLabel("No mods loaded")
        self.status_lbl.setObjectName("muted")
        bot_lay.addWidget(self.status_lbl)
        root.addWidget(bot)

    def _build_editor(self, layout):
        self.editor_title = QLabel("Generation defaults")
        self.editor_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.editor_title.setObjectName("sectionTitle")
        layout.addWidget(self.editor_title)
        self.source_label = QLineEdit()
        self.source_label.setReadOnly(True)
        self.source_label.setPlaceholderText("No configuration selected")
        layout.addWidget(self.source_label)
        self.editor_tabs = QTabWidget()
        layout.addWidget(self.editor_tabs, 1)
        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form = QWidget()
        grid = QGridLayout(form)
        grid.setContentsMargins(0, 12, 8, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        fields = [
            ("Display name", "w_name", None),
            ("Config type", "w_config_type", ["Factory", "Custom", "Race"]),
            ("Drivetrain", "w_drivetrain", ["RWD", "AWD", "FWD", "4WD"]),
            ("Transmission", "w_transmission", ["Automatic", "Manual", "DCT", "CVT"]),
            ("Fuel type", "w_fuel", ["Gasoline", "Diesel", "Electric", "Hybrid"]),
            ("Body style", "w_body", ["Sedan", "Coupe", "SUV", "Hatchback", "Wagon", "Truck", "Van", "Convertible"]),
            ("Induction", "w_induction", ["Turbo", "Twin Turbo", "Supercharger", "Natural"]),
            ("Power (HP)", "w_power", None),
            ("Torque (Nm)", "w_torque", None),
            ("Weight (kg)", "w_weight", None),
            ("Price min", "w_price_min", None),
            ("Price max", "w_price_max", None),
        ]
        for index, (label, attr, choices) in enumerate(fields):
            row, column = (index // 2) * 2, index % 2
            caption = QLabel(label)
            caption.setObjectName("muted")
            grid.addWidget(caption, row, column)
            if choices:
                widget = QComboBox()
                widget.addItems(choices)
                widget.currentTextChanged.connect(self._form_changed)
            else:
                widget = QLineEdit()
                if attr in ("w_power", "w_torque", "w_weight"):
                    validator = QDoubleValidator(0, 2147483647, 6, widget)
                    validator.setLocale(QLocale.c())
                    validator.setNotation(QDoubleValidator.StandardNotation)
                    widget.setValidator(validator)
                elif attr != "w_name":
                    widget.setValidator(QIntValidator(0, 2147483647, widget))
                widget.textChanged.connect(self._form_changed)
            grid.addWidget(widget, row + 1, column)
            setattr(self, attr, widget)
        self.w_price_min.setText("10000")
        self.w_price_max.setText("50000")
        self.w_name.setEnabled(False)
        description_label = QLabel("Description")
        description_label.setObjectName("muted")
        grid.addWidget(description_label, 12, 0, 1, 2)
        self.w_description = QTextEdit()
        self.w_description.setAcceptRichText(False)
        self.w_description.setMinimumHeight(80)
        self.w_description.setMaximumHeight(110)
        self.w_description.textChanged.connect(self._form_changed)
        grid.addWidget(self.w_description, 13, 0, 1, 2)
        grid.setRowStretch(14, 1)
        form_scroll.setWidget(form)
        self.editor_tabs.addTab(form_scroll, "Details")

        json_tab = QWidget()
        json_layout = QVBoxLayout(json_tab)
        json_layout.setContentsMargins(0, 10, 0, 0)
        self.json_view = JsonView()
        self.json_view.setEnabled(False)
        self.json_view._editor.textChanged.connect(self._json_changed)
        json_layout.addWidget(self.json_view, 1)
        json_tools = QHBoxLayout()
        json_tools.addWidget(self._button("Format", "braces", self._format_json))
        json_tools.addStretch()
        json_layout.addLayout(json_tools)
        self.editor_tabs.addTab(json_tab, "JSON")
        self.editor_tabs.currentChanged.connect(self._switch_editor_tab)

        self.lbl_missing = QLabel("")
        self.lbl_missing.setStyleSheet("color: #e2ad63;")
        self.lbl_missing.setWordWrap(True)
        layout.addWidget(self.lbl_missing)
        buttons = QHBoxLayout()
        self.save_btn = self._button("Save", "save", self._save_current, True)
        self.regen_btn = self._button("Regenerate", "refresh-cw", self._regen_current)
        self.copy_btn = self._button("Copy from...", "copy", self._copy_from_dialog)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.regen_btn)
        buttons.addWidget(self.copy_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        self._card = _CardPreview()
        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)
        preview_layout.setContentsMargins(0, 12, 0, 0)
        preview_layout.addWidget(self._card)
        preview_layout.addStretch()
        self.editor_tabs.addTab(preview_tab, "Preview")
        for button in (self.save_btn, self.regen_btn, self.copy_btn):
            button.setEnabled(False)

    def _matches(self, mod_name, entry):
        if entry.status not in self._status_filter:
            return False
        query = self.search_edit.text().strip().casefold()
        if not query:
            return True
        data = entry.info_content or entry.auto_detected
        text = " ".join([mod_name, entry.config_name, str(data.get("Configuration", "")),
                         str(data.get("Drivetrain", "")), str(data.get("Fuel Type", "")),
                         str(data.get("Transmission", "")), str(data.get("Config Type", ""))]).casefold()
        return all(word in text for word in query.split())

    def _toggle_filter(self, status):
        if status in self._status_filter:
            self._status_filter.remove(status)
        else:
            self._status_filter.add(status)
        self._update_filter_buttons()
        self._rebuild_view()

    def _update_filter_buttons(self):
        labels = {"missing": "Missing", "bad": "Incomplete", "ok": "Valid"}
        entries = [e for es in self.mods_data.values() for e in es]
        for status, button in self._filter_btns.items():
            button.setChecked(status in self._status_filter)
            button.setText(f"{labels[status]} {sum(e.status == status for e in entries)}")
            button.setStyleSheet(f"color: {STATUS_COLOR[status]};")

    def _rebuild_tree(self):
        self.tree.blockSignals(True)
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        for mod_name, entries in self.mods_data.items():
            visible = [e for e in entries if self._matches(mod_name, e)]
            if not visible:
                continue
            parent = QTreeWidgetItem([f"{mod_name}  ({len(visible)})"])
            parent.setData(0, Qt.UserRole + 1, mod_name)
            parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
            parent.setFont(0, QFont("Segoe UI", 10, QFont.Bold))
            self.tree.addTopLevelItem(parent)
            for entry in visible:
                child = QTreeWidgetItem([entry.config_name])
                child.setIcon(0, icon(STATUS_ICON[entry.status], STATUS_COLOR[entry.status]))
                child.setData(0, Qt.UserRole, entry)
                child.setForeground(0, QColor(STATUS_COLOR[entry.status]))
                child.setToolTip(0, entry.info_path or entry.pc_path)
                parent.addChild(child)
                child.setSelected(id(entry) in self._selection)
                if entry is self.selected_entry:
                    self.tree.setCurrentItem(child, 0, QItemSelectionModel.NoUpdate)
            expanded = not self._collapsed.get(mod_name, all(e.status == "ok" for e in entries))
            parent.setExpanded(expanded or bool(self.search_edit.text().strip()))
        self.tree.setUpdatesEnabled(True)
        self.tree.blockSignals(False)

    def _rebuild_view(self):
        self._rebuild_tree()
        if self._table_mode:
            self._rebuild_table()
        visible_ids = {id(e) for name, entries in self.mods_data.items() for e in entries if self._matches(name, e)}
        self._selection.intersection_update(visible_ids)
        self.list_count.setText(f"{len(visible_ids)} shown / {sum(map(len, self.mods_data.values()))} total")
        self._update_sel_button()

    def _toggle_view(self):
        self._table_mode = not self._table_mode
        self.tree.setVisible(not self._table_mode)
        self.table.setVisible(self._table_mode)
        self._view_btn.setIcon(icon("list-tree" if self._table_mode else "table-2"))
        self._view_btn.setToolTip("Tree view" if self._table_mode else "Table view")
        self._rebuild_view()

    def _rebuild_table(self):
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for mod_name, entries in self.mods_data.items():
            for entry in entries:
                if not self._matches(mod_name, entry):
                    continue
                data = entry.info_content or entry.auto_detected
                row = self.table.rowCount()
                self.table.insertRow(row)
                values = ["", mod_name, entry.config_name,
                          data.get("Drivetrain", ""), data.get("Fuel Type", ""),
                          data.get("Transmission", ""), data.get("Config Type", ""), data.get("Value", "")]
                for column, value in enumerate(values):
                    if column == 0:
                        item = _StatusItem()
                        item.setData(Qt.UserRole + 1, {"missing": 0, "bad": 1, "ok": 2}[entry.status])
                    else:
                        item = _NumberItem(str(value)) if column == 7 else QTableWidgetItem(str(value))
                    if column == 0:
                        item.setData(Qt.UserRole, entry)
                        item.setIcon(icon(STATUS_ICON[entry.status], STATUS_COLOR[entry.status]))
                        item.setToolTip({"ok": "Valid", "bad": "Incomplete", "missing": "Missing"}[entry.status])
                        item.setForeground(QColor(STATUS_COLOR[entry.status]))
                    if column == 7:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(row, column, item)
        self.table.setSortingEnabled(True)
        for row in range(self.table.rowCount()):
            entry = self.table.item(row, 0).data(Qt.UserRole)
            for column in range(self.table.columnCount()):
                self.table.item(row, column).setSelected(id(entry) in self._selection)
        self.table.setUpdatesEnabled(True)
        self.table.blockSignals(False)

    def _activate_entry(self, entry):
        if entry is self.selected_entry:
            return True
        if not self._confirm_changes():
            return False
        self.selected_entry = entry
        self._load_to_editor(entry)
        return True

    def _on_table_cell_clicked(self, row, _column):
        item = self.table.item(row, 0)
        if item is not None:
            if not self._activate_entry(item.data(Qt.UserRole)):
                self._restore_current_selection()

    def _on_table_selection(self):
        self._selection = {id(self.table.item(i.row(), 0).data(Qt.UserRole))
                           for i in self.table.selectionModel().selectedRows()}
        self._update_sel_button()

    def _on_tree_current(self, current, previous):
        if current is not None and current.data(0, Qt.UserRole) is not None:
            if not self._activate_entry(current.data(0, Qt.UserRole)):
                self._restore_current_selection()

    def _on_item_clicked(self, item, _column):
        entry = item.data(0, Qt.UserRole)
        if entry is None:
            item.setExpanded(not item.isExpanded())
        elif not self._activate_entry(entry):
            self._restore_current_selection()

    def _restore_current_selection(self):
        if self.selected_entry:
            self._selection = {id(self.selected_entry)}
            self._rebuild_view()

    def _on_selection_changed(self):
        self._selection = {id(item.data(0, Qt.UserRole)) for item in self.tree.selectedItems()
                           if item.data(0, Qt.UserRole) is not None}
        self._update_sel_button()

    def _update_sel_button(self):
        n = len(self._selection)
        self.gen_sel_btn.setText(f"Generate selected ({n})")
        self.gen_sel_btn.setEnabled(n > 0 and not self._busy)

    def _maybe_auto_collapse(self, mod_name):
        entries = self.mods_data.get(mod_name, [])
        if entries and all(e.status == "ok" for e in entries):
            self._collapsed[mod_name] = True

    def _refresh_entry_item(self, entry):
        self._rebuild_view()

    def _fill_form_data(self, data, auto):
        def set_combo(widget, value):
            value = str(value) if value is not None else ""
            index = widget.findText(value)
            if index < 0:
                widget.addItem(value)
                index = widget.count() - 1
            widget.setCurrentIndex(index)
        for widget, key, fallback in (
            (self.w_config_type, "Config Type", "Factory"),
            (self.w_drivetrain, "Drivetrain", auto.get("Drivetrain", "RWD")),
            (self.w_transmission, "Transmission", auto.get("Transmission", "Automatic")),
            (self.w_fuel, "Fuel Type", auto.get("Fuel Type", "Gasoline")),
            (self.w_body, "Body Style", "Sedan"),
            (self.w_induction, "Induction Type", "Natural"),
        ):
            set_combo(widget, data.get(key, fallback))
        self.w_name.setText(str(data.get("Configuration") or self.selected_entry.config_name))
        for widget, key in ((self.w_power, "Power"), (self.w_torque, "Torque"), (self.w_weight, "Weight")):
            val = data.get(key, "")
            widget.setText(str(val) if val is not None else "")
        value = data.get("Value", "")
        try:
            price = float(value)
            valid_price = not isinstance(value, bool) and math.isfinite(price) and price >= 1
        except (TypeError, ValueError, OverflowError):
            valid_price = False
        self.w_price_min.setText(str(int(price)) if valid_price else "10000")
        self.w_price_max.setText(str(int(price)) if valid_price else "50000")
        self.w_description.setPlainText(str(data.get("Description") or ""))

    def _load_to_editor(self, entry):
        self._loading = True
        self._draft_data = dict(entry.info_content or {})
        self._fill_form_data(self._draft_data, entry.auto_detected)
        self._populate_json_view(entry)
        self.json_view.setEnabled(True)
        self.editor_title.setText(entry.config_name)
        self.editor_title.setToolTip(entry.config_name)
        self.source_label.setText(entry.info_path or self._target_path_for_entry(entry))
        self.source_label.setToolTip(f"{entry.source_path}\n{entry.pc_path}")
        self.w_name.setEnabled(True)
        for button in (self.save_btn, self.regen_btn, self.copy_btn):
            button.setEnabled(True)
        try:
            self._card.set_thumbnail(load_thumbnail(entry))
        except Exception as exc:
            self._card.set_thumbnail(b"")
            self._history.append({"operation": "Thumbnail", "errors": [str(exc)]})
        self.lbl_missing.setText(
            f"Unreadable info: {entry.parse_error}" if entry.parse_error else
            (f"Missing / invalid: {', '.join(entry.missing_fields)}" if entry.missing_fields else
             ("No info file" if entry.status == "missing" else ""))
        )
        self._form_dirty = self._json_dirty = False
        self.setWindowModified(False)
        self._previous_tab = self.editor_tabs.currentIndex()
        self._loading = False
        self._refresh_card()

    def _populate_json_view(self, entry: ConfigEntry):
        if entry.info_raw is not None:
            self.json_view.set_raw(entry.info_raw, set(entry.missing_fields))
        else:
            auto = entry.auto_detected
            data = {
                "Configuration": entry.config_name,
                "Config Type":   "Factory",
                "Drivetrain":    auto.get("Drivetrain",   "RWD"),
                "Transmission":  auto.get("Transmission", "Automatic"),
                "Fuel Type":     auto.get("Fuel Type",    "Gasoline"),
                "Value":         0,
            }
            self.json_view.set_content(data, set(validate(data)))

    def _refresh_card(self):
        if not self.selected_entry:
            return
        try:
            price = int(self.w_price_min.text())
        except (ValueError, TypeError):
            price = 0
        data = {
            "Configuration":  self.w_name.text() or self.selected_entry.config_name,
            "Config Type":    self.w_config_type.currentText(),
            "Drivetrain":     self.w_drivetrain.currentText(),
            "Transmission":   self.w_transmission.currentText(),
            "Fuel Type":      self.w_fuel.currentText(),
            "Induction Type": self.w_induction.currentText(),
            "Body Style":     self.w_body.currentText(),
            "Value":          price,
            "Description":    self.w_description.toPlainText(),
        }
        for key, w in [("Power", self.w_power), ("Torque", self.w_torque),
                       ("Weight", self.w_weight)]:
            try:
                value = float(w.text())
                data[key] = int(value) if value.is_integer() else value
            except (ValueError, TypeError):
                pass
        if self._json_dirty or self.editor_tabs.currentIndex() == 1:
            try:
                data = json_utils.loads(self.json_view.get_raw_text())
            except ValueError:
                return
        self._card.update(data)

    def _editor_defaults(self) -> dict:
        return {
            "config_type": self.w_config_type.currentText(),
            "induction":   self.w_induction.currentText(),
            "body_style":  self.w_body.currentText(),
            "power":       self.w_power.text(),
            "torque":      self.w_torque.text(),
            "weight":      self.w_weight.text(),
            "price_min":   self.w_price_min.text() or "10000",
            "price_max":   self.w_price_max.text() or "50000",
            "description": self.w_description.toPlainText(),
        }

    def _build_data_from_editor(self, entry):
        d = self._editor_defaults()
        data = dict(self._draft_data if self._draft_data is not None else entry.info_content or {})
        data.update({
            "Configuration": self.w_name.text().strip() or entry.config_name,
            "Config Type": self.w_config_type.currentText(),
            "Drivetrain": self.w_drivetrain.currentText(),
            "Transmission": self.w_transmission.currentText(),
            "Fuel Type": self.w_fuel.currentText(),
            "Propulsion": "Electric" if self.w_fuel.currentText() == "Electric" else "ICE",
            "Induction Type": d["induction"],
            "Body Style": d["body_style"],
            "Description": d["description"],
        })
        data.setdefault("Population", 5000)
        data.setdefault("Off-Road Score", 20)
        lo, hi = int(d["price_min"]), int(d["price_max"])
        if min(lo, hi) <= 0:
            raise ValueError("Price must be greater than zero")
        lo, hi = sorted((lo, hi))
        data["Value"] = lo if lo == hi else min(hi, max(lo, round(random.randint(lo, hi) / 500) * 500))
        for key, dkey in (("Power", "power"), ("Torque", "torque"), ("Weight", "weight")):
            text = d[dkey].strip()
            if text:
                value = float(text)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"{key} must be greater than zero or blank")
                data[key] = int(value) if value.is_integer() else value
            else:
                data.pop(key, None)
        return data

    def _form_changed(self, *args):
        if self._loading:
            return
        if self.selected_entry:
            self._form_dirty = True
            self.setWindowModified(True)
        self._refresh_card()

    def _json_changed(self):
        if self._loading:
            return
        if self.selected_entry:
            self._json_dirty = True
            self.setWindowModified(True)
        self._refresh_card()

    def _switch_editor_tab(self, index):
        if self._loading or not self.selected_entry:
            self._previous_tab = index
            return
        try:
            if index == 1 and self._form_dirty:
                data = self._build_data_from_editor(self.selected_entry)
                self._loading = True
                self._draft_data = data
                self.json_view.set_content(data, set(validate(data)))
                self._form_dirty = False
                self._json_dirty = True
            elif index == 0 and self._json_dirty:
                data = json_utils.loads(self.json_view.get_raw_text())
                self._loading = True
                self._draft_data = data
                self._fill_form_data(data, self.selected_entry.auto_detected)
                self._json_dirty = False
                self._form_dirty = True
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid draft", str(exc))
            self.editor_tabs.blockSignals(True)
            self.editor_tabs.setCurrentIndex(self._previous_tab)
            self.editor_tabs.blockSignals(False)
        finally:
            self._loading = False
            self._previous_tab = self.editor_tabs.currentIndex()
        self._refresh_card()

    def _format_json(self):
        try:
            data = json_utils.loads(self.json_view.get_raw_text())
            self.json_view.set_content(data, set(validate(data)))
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid JSON", str(exc))

    def _confirm_changes(self):
        if not (self._form_dirty or self._json_dirty):
            return True
        answer = QMessageBox.question(
            self, "Unsaved changes", "Save changes to the current configuration?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save,
        )
        if answer == QMessageBox.Save:
            return self._save_current()
        if answer == QMessageBox.Discard:
            self._form_dirty = self._json_dirty = False
            self.setWindowModified(False)
            if self.selected_entry:
                self._load_to_editor(self.selected_entry)
            return True
        return False

    def _restore_layout(self):
        size = self._settings.get("window_size")
        if isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) for v in size):
            self.resize(max(900, min(size[0], 2400)), max(650, min(size[1], 1600)))
        sizes = self._settings.get("splitter_sizes")
        if isinstance(sizes, list) and len(sizes) == 2 and all(isinstance(v, int) and v > 0 for v in sizes):
            self.splitter.setSizes(sizes)
        if self._settings.get("table_view", False):
            self._toggle_view()

    def closeEvent(self, event):
        if self._busy or not self._confirm_changes():
            event.ignore()
            return
        self._settings.update({
            "window_size": [self.width(), self.height()],
            "splitter_sizes": self.splitter.sizes(),
            "table_view": self._table_mode,
            "last_mods_path": self.folder_edit.text().strip(),
        })
        try:
            _save_settings(self._settings)
        except OSError as exc:
            QMessageBox.warning(self, "Settings", str(exc))
        event.accept()

    def _show_about(self):
        AboutDialog(self).exec()

    def _show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumWidth(410)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("ZIP write mode"))
        mode = QComboBox()
        for label, value in (("Automatic (append / disk)", "auto"), ("Disk", "disk"), ("RAM", "ram")):
            mode.addItem(label, value)
        index = mode.findData(self._settings.get("zip_mode", "auto"))
        mode.setCurrentIndex(max(0, index))
        mode.setToolTip("Automatic appends new files. Disk and RAM rebuild the archive. Replacements are committed through a temporary file next to the mod.")
        layout.addWidget(mode)
        backup = QCheckBox("Back up before writes")
        backup.setChecked(bool(self._settings.get("backup_writes", False)))
        backup.setToolTip("Keeps dated .bak files next to originals. A ZIP backup requires space for the entire archive.")
        layout.addWidget(backup)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setIcon(icon("save"))
        buttons.button(QDialogButtonBox.Cancel).setIcon(icon("x"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            self._settings["zip_mode"] = mode.currentData()
            self._settings["backup_writes"] = backup.isChecked()
            try:
                _save_settings(self._settings)
            except OSError as exc:
                QMessageBox.warning(self, "Settings", str(exc))

    def _show_history(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Operation history")
        dialog.resize(720, 480)
        layout = QVBoxLayout(dialog)
        report = QTextEdit()
        report.setReadOnly(True)
        lines = []
        for item in self._history:
            lines.append(f"{item.get('time', '')}  {item.get('operation', '')}")
            lines.append(f"Completed: {item.get('completed', 0)}   Cancelled: {item.get('cancelled', False)}   {item.get('seconds', 0):.2f}s")
            lines.extend(str(error) for error in item.get("errors", []))
            lines.append("")
        report.setPlainText("\n".join(lines) or "No operations")
        layout.addWidget(report)
        row = QHBoxLayout()
        def export():
            path, _ = QFileDialog.getSaveFileName(dialog, "Export history", "operations.json", "JSON (*.json)")
            if path:
                try:
                    write_text_atomic(path, json.dumps(self._history, indent=2, ensure_ascii=False))
                except OSError as exc:
                    QMessageBox.warning(dialog, "Export failed", str(exc))
        row.addWidget(self._button("Export", "download", export))
        row.addStretch()
        row.addWidget(self._button("Close", "x", dialog.accept))
        layout.addLayout(row)
        dialog.exec()

    def _info_filename_for_entry(self, entry: ConfigEntry) -> str:
        if entry.info_path:
            return Path(entry.info_path).name

        return f"info_{entry.config_name}.json"

    def _target_path_for_entry(self, entry: ConfigEntry) -> str:
        if entry.info_path:
            return entry.info_path
        info_filename = self._info_filename_for_entry(entry)
        if entry.source == "zip":
            target = (Path(entry.pc_path).parent / info_filename).as_posix()
            if target.startswith("./"):
                target = target[2:]
            return target
        return str(Path(entry.pc_path).parent / info_filename)

    def _mark_entry_written(self, entry: ConfigEntry, data: dict, json_str: str, info_path: str):
        entry.info_path      = info_path
        entry.info_content   = data
        entry.info_raw       = json_str
        entry.missing_fields = validate(data)
        entry.status         = "ok" if not entry.missing_fields else "bad"
        entry.parse_error    = None

    def _write_entry(self, entry: ConfigEntry, data: dict, refresh: bool = True):
        self._write_entry_pairs([(entry, data)])
        if refresh:
            self._refresh_entry_item(entry)

    def _write_entry_pairs(self, pairs: list[tuple[ConfigEntry, dict]]):
        zip_updates: dict[str, dict[str, str]] = {}
        zip_written: list[tuple[ConfigEntry, dict, str, str]] = []

        for entry, data in pairs:
            check_cancel(self._cancel_event)
            json_str = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
            target = self._target_path_for_entry(entry)

            if entry.source == "zip":
                updates = zip_updates.setdefault(entry.source_path, {})
                if target in updates:
                    raise ValueError(f"Multiple configurations map to the same info file: {target}")
                updates[target] = json_str
                zip_written.append((entry, data, json_str, target))
            else:
                write_text_atomic(target, json_str, backup=self._settings.get("backup_writes", False))
                self._mark_entry_written(entry, data, json_str, target)

        for zip_path, updates in zip_updates.items():
            write_many_to_zip(zip_path, updates, mode=self._settings.get("zip_mode", "auto"),
                              backup=self._settings.get("backup_writes", False),
                              cancel=self._cancel_event, progress=self._operation_progress)
            for entry, data, json_str, target in zip_written:
                if entry.source_path == zip_path:
                    self._mark_entry_written(entry, data, json_str, target)

    def _write_groups_for_pairs(self, pairs: list[tuple[ConfigEntry, dict]]) -> list[list[tuple[ConfigEntry, dict]]]:
        groups: list[list[tuple[ConfigEntry, dict]]] = []
        zip_groups: dict[str, list[tuple[ConfigEntry, dict]]] = {}

        for entry, data in pairs:
            if entry.source == "zip":
                zip_groups.setdefault(entry.source_path, []).append((entry, data))
            else:
                groups.append([(entry, data)])

        groups.extend(zip_groups.values())
        return groups

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select mods folder")
        if path:
            self.folder_edit.setText(path)

    def _scan(self):
        if self._busy or not self._confirm_changes():
            return
        path = self.folder_edit.text().strip()
        if not Path(path).is_dir():
            QMessageBox.warning(self, "Mods directory", "Select a valid folder.")
            return
        issues = []
        def task(cancel, progress):
            return scan_mods_folder(path, issues=issues, progress=progress, cancel=cancel)
        started = time.monotonic()
        self._busy = True
        worker = TaskDialog("Scanning mods", task, self).execute()
        self._busy = False
        self._history.append({"time": datetime.now().isoformat(timespec="seconds"), "operation": "Scan",
                              "completed": sum(map(len, worker.value.values())) if worker.value is not None else 0,
                              "cancelled": worker.cancelled, "seconds": time.monotonic() - started,
                              "errors": issues + ([worker.error] if worker.error else [])})
        if worker.error:
            QMessageBox.critical(self, "Scan failed", worker.error)
            return
        if worker.cancelled:
            self.status_lbl.setText("Scan cancelled")
            return
        self.mods_data = worker.value
        self.selected_entry = None
        self._selection.clear()
        self._collapsed.clear()
        self._clear_editor()
        self._rebuild_view()
        self._update_status()
        self.rescan_btn.setEnabled(True)
        self._settings["last_mods_path"] = path
        try:
            _save_settings(self._settings)
        except OSError as exc:
            issues.append(f"Settings: {exc}")
        if issues:
            QMessageBox.warning(self, "Scan completed with issues", f"{len(issues)} unreadable files. See History for details.\n\n" + "\n".join(issues[:3]))

    def _clear_editor(self):
        self._loading = True
        self._form_dirty = self._json_dirty = False
        self._draft_data = None
        self.setWindowModified(False)
        self.editor_title.setText("Generation defaults")
        self.source_label.clear()
        self.w_name.clear()
        self.w_name.setEnabled(False)
        self.json_view.set_raw("")
        self.json_view.setEnabled(False)
        self.lbl_missing.clear()
        self._card.clear()
        for button in (self.save_btn, self.regen_btn, self.copy_btn):
            button.setEnabled(False)
        self._loading = False

    def _rescan(self):
        self._scan()

    def _save_current(self):
        if not self.selected_entry or self._busy:
            return False
        if self._json_dirty or self.editor_tabs.currentIndex() == 1:
            return self._save_json_current()
        entry = self.selected_entry
        try:
            data = self._build_data_from_editor(entry)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid values", str(exc))
            return False
        if entry.parse_error and QMessageBox.question(
                self, "Replace unreadable info", "Replace the unreadable info file with form values?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        def done(_):
            self._refresh_entry_item(entry)
            self._load_to_editor(entry)
            self._update_status()
        return self._run_batch("Save configuration", [entry],
                               lambda _: self._write_entry(entry, data, refresh=False), done)

    def _regen_current(self):
        if not self.selected_entry or self._busy:
            return
        entry = self.selected_entry
        if QMessageBox.question(self, "Regenerate configuration",
                "Replace this info file completely using the current defaults?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        regen = generate(entry.config_name, {
            "Drivetrain": self.w_drivetrain.currentText(),
            "Transmission": self.w_transmission.currentText(),
            "Fuel Type": self.w_fuel.currentText(),
        }, self._editor_defaults())
        def done(_):
            self._refresh_entry_item(entry)
            self._load_to_editor(entry)
            self._update_status()
        self._run_batch("Regenerate configuration", [entry],
                        lambda _: self._write_entry(entry, regen, refresh=False), done)

    def _save_json_current(self):
        if not self.selected_entry or self._busy:
            return False
        try:
            data = json_utils.loads(self.json_view.get_raw_text().strip())
            json.dumps(data, allow_nan=False)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Invalid JSON", str(exc))
            return False
        missing = validate(data)
        if missing and QMessageBox.question(
                self, "Incomplete configuration", f"Save with invalid fields: {', '.join(missing)}?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        entry = self.selected_entry
        def done(_):
            self._refresh_entry_item(entry)
            self._load_to_editor(entry)
            self._update_status()
        return self._run_batch("Save JSON", [entry],
                               lambda _: self._write_entry(entry, data, refresh=False), done)

    def _generate_all_missing(self):
        if self._busy or not self._confirm_changes():
            return
        defaults = self._editor_defaults()
        pairs = [
            (e, generate(e.config_name, e.auto_detected, defaults))
            for es in self.mods_data.values()
            for e in es if e.status == "missing"
        ]
        groups = self._write_groups_for_pairs(pairs)

        def work(group):
            self._write_entry_pairs(group)

        def done(n):
            for mod_name in self.mods_data:
                self._maybe_auto_collapse(mod_name)
            self._rebuild_view()
            self._update_status(created=n)
            if self.selected_entry and any(e is self.selected_entry for e, _ in pairs):
                self._load_to_editor(self.selected_entry)

        self._run_batch("Generating...", groups, work, done,
                        subtitle="Generating missing info configs...")

    def _generate_selected(self):
        if self._busy or not self._selection or not self._confirm_changes():
            return
        defaults = self._editor_defaults()
        auto_override = {
            "Drivetrain":   self.w_drivetrain.currentText(),
            "Transmission": self.w_transmission.currentText(),
            "Fuel Type":    self.w_fuel.currentText(),
        }
        all_entries = {id(e): e for es in self.mods_data.values() for e in es}
        entries = [all_entries[eid] for eid in self._selection if eid in all_entries]
        existing = sum(e.status != "missing" for e in entries)
        if existing and QMessageBox.question(
                self, "Generate selected", f"Overwrite {existing} existing info files?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        pairs = [
            (e, generate(e.config_name, auto_override, defaults))
            for e in entries
        ]
        groups = self._write_groups_for_pairs(pairs)

        def work(group):
            self._write_entry_pairs(group)

        def done(n):
            for mod_name in self.mods_data:
                self._maybe_auto_collapse(mod_name)
            self._rebuild_view()
            self._update_status(created=n)
            if self.selected_entry and id(self.selected_entry) in self._selection:
                self._load_to_editor(self.selected_entry)

        self._run_batch("Generating...", groups, work, done,
                        subtitle="Generating selected configs...")

    def _fix_all_bad(self):
        if self._busy or not self._confirm_changes():
            return
        unreadable = [e for es in self.mods_data.values() for e in es if e.parse_error]
        if unreadable:
            QMessageBox.warning(self, "Unreadable info files",
                                f"{len(unreadable)} unreadable files will be skipped. Their raw content is available in the JSON tab.")
        defaults = self._editor_defaults()
        pairs = [
            (e, fix(e.info_content or {}, e.config_name, e.auto_detected, defaults))
            for es in self.mods_data.values()
            for e in es if e.status == "bad" and not e.parse_error
        ]
        groups = self._write_groups_for_pairs(pairs)

        def work(group):
            self._write_entry_pairs(group)

        def done(n):
            for mod_name in self.mods_data:
                self._maybe_auto_collapse(mod_name)
            self._rebuild_view()
            self._update_status(updated=n)
            if self.selected_entry and any(e is self.selected_entry for e, _ in pairs):
                self._load_to_editor(self.selected_entry)

        self._run_batch("Fixing...", groups, work, done,
                        subtitle="Filling missing fields in existing configs...")

    def _show_analyze_dialog(self):
        report = analyze(self.mods_data)

        dialog = QDialog(self)
        dialog.setWindowTitle("Analyze — Config Issues")
        dialog.resize(560, 480)
        lay = QVBoxLayout(dialog)

        if not report:
            lay.addWidget(QLabel("All configs look good"))
        else:
            tree = QTreeWidget()
            tree.setHeaderHidden(True)
            tree.setRootIsDecorated(True)
            tree.setIndentation(16)
            lay.addWidget(tree, 1)

            for mod_name, configs in report.items():
                mod_item = QTreeWidgetItem([mod_name])
                mod_item.setFont(0, QFont("Segoe UI", 10, QFont.Bold))
                mod_item.setForeground(0, QColor("#aaaaaa"))
                tree.addTopLevelItem(mod_item)

                for cfg in configs:
                    cfg_item = QTreeWidgetItem([cfg["config_name"]])
                    cfg_item.setForeground(0, QColor("#cccccc"))
                    mod_item.addChild(cfg_item)

                    for msg in cfg["critical"]:
                        ch = QTreeWidgetItem([msg])
                        ch.setIcon(0, icon("circle-x", "#E74C3C"))
                        ch.setForeground(0, QColor("#E74C3C"))
                        cfg_item.addChild(ch)
                    for msg in cfg["warnings"]:
                        ch = QTreeWidgetItem([msg])
                        ch.setIcon(0, icon("triangle-alert", "#E67E22"))
                        ch.setForeground(0, QColor("#E67E22"))
                        cfg_item.addChild(ch)

                mod_item.setExpanded(True)
                for i in range(mod_item.childCount()):
                    mod_item.child(i).setExpanded(True)

        btn_row = QHBoxLayout()
        if report:
            copy_btn = QPushButton("Copy report")
            copy_btn.setIcon(icon("copy"))
            def _copy():
                lines = []
                for mod_name, configs in report.items():
                    lines.append(mod_name)
                    for cfg in configs:
                        lines.append(f"  {cfg['config_name']}")
                        for m in cfg["critical"]:
                            lines.append(f"    [CRITICAL] {m}")
                        for m in cfg["warnings"]:
                            lines.append(f"    [WARNING]  {m}")
                QApplication.clipboard().setText("\n".join(lines))
            copy_btn.clicked.connect(_copy)
            btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setIcon(icon("x"))
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        dialog.exec()

    def _copy_from_dialog(self):
        if not self.selected_entry or not self.mods_data:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Copy fields from...")
        dialog.resize(420, 480)
        lay = QVBoxLayout(dialog)

        lay.addWidget(QLabel("Select a config to copy fields from:"))

        listbox = QListWidget()
        lay.addWidget(listbox, 1)

        source_entries: list[ConfigEntry] = []
        for mod_name, entries in self.mods_data.items():
            for e in entries:
                if e.info_content and e is not self.selected_entry:
                    listbox.addItem(f"  {mod_name} / {e.config_name}")
                    source_entries.append(e)

        if not source_entries:
            lay.addWidget(QLabel("No configs with data to copy from."))

        def _do_copy():
            row = listbox.currentRow()
            if row < 0:
                return
            dialog.accept()
            self._apply_copy(source_entries[row])

        copy_btn = QPushButton("Copy")
        copy_btn.setIcon(icon("copy"))
        copy_btn.clicked.connect(_do_copy)
        lay.addWidget(copy_btn)
        dialog.exec()

    def _apply_copy(self, source: ConfigEntry):
        data = source.info_content or {}

        def _set(w: QComboBox, key: str):
            val = data.get(key)
            if val:
                val = str(val)
                idx = w.findText(val)
                if idx >= 0:
                    w.setCurrentIndex(idx)

        _set(self.w_config_type,  "Config Type")
        _set(self.w_drivetrain,   "Drivetrain")
        _set(self.w_transmission, "Transmission")
        _set(self.w_fuel,         "Fuel Type")
        _set(self.w_body,         "Body Style")
        _set(self.w_induction,    "Induction Type")

        for widget, key in [(self.w_power, "Power"), (self.w_torque, "Torque"),
                             (self.w_weight, "Weight")]:
            val = data.get(key)
            if val is not None and val != "":
                widget.setText(str(val))

        val = data.get("Value", "")
        if val:
            price_str = str(int(val)) if isinstance(val, float) else str(val)
            self.w_price_min.setText(price_str)
            self.w_price_max.setText(price_str)

        desc = data.get("Description", "")
        if desc:
            self.w_description.setPlainText(desc)

    def _run_batch(self, title, items, work_fn, done_fn, subtitle=""):
        if not items or self._busy:
            return False
        total = sum(len(item) if isinstance(item, list) else 1 for item in items)
        def task(cancel, progress):
            completed, errors = 0, []
            for item in items:
                if cancel.is_set():
                    break
                group = item if isinstance(item, list) else [(item, None)]
                entry = group[0][0]
                label = Path(entry.source_path).name
                progress(completed, total, f"{label}: {len(group)} configuration(s)")
                self._cancel_event = cancel
                def zip_progress(current, count, name):
                    progress(completed, total, f"{label}: copying archive {current}/{count}")
                self._operation_progress = zip_progress
                try:
                    work_fn(item)
                    completed += len(group)
                except OperationCancelled:
                    break
                except Exception as exc:
                    errors.append(f"{label}: {exc}")
                finally:
                    self._cancel_event = None
                    self._operation_progress = None
                progress(completed, total, label)
            return {"completed": completed, "errors": errors, "cancelled": cancel.is_set()}
        started = time.monotonic()
        self._busy = True
        worker = TaskDialog(title, task, self).execute()
        self._busy = False
        result = worker.value or {"completed": 0, "errors": [worker.error or "Operation failed"], "cancelled": worker.cancelled}
        result.update({"operation": title, "time": datetime.now().isoformat(timespec="seconds"),
                       "seconds": time.monotonic() - started})
        self._history.append(result)
        self._history = self._history[-100:]
        if result["completed"]:
            done_fn(result["completed"])
        else:
            self._update_status()
        if result["errors"]:
            QMessageBox.warning(self, "Operation completed with errors",
                                f"{result['completed']} / {total} configurations written.\n\n" +
                                "\n".join(result["errors"][:5]))
        elif result["cancelled"]:
            self.status_lbl.setText(f"Cancelled. {result['completed']} / {total} configurations written.")
        else:
            self.status_lbl.setText(f"{result['completed']} configurations written in {result['seconds']:.2f}s")
        return result["completed"] == total and not result["errors"] and not result["cancelled"]

    def _update_status(self, created=0, updated=0):
        entries = [e for es in self.mods_data.values() for e in es]
        missing = sum(e.status == "missing" for e in entries)
        bad = sum(e.status == "bad" for e in entries)
        valid = sum(e.status == "ok" for e in entries)
        self._update_filter_buttons()
        self.gen_all_btn.setEnabled(missing > 0 and not self._busy)
        self.fix_all_btn.setEnabled(bad > 0 and not self._busy)
        self._update_sel_button()
        self.status_lbl.setText(f"{len(self.mods_data)} mods  |  {len(entries)} configurations  |  {valid} valid  |  {bad} incomplete  |  {missing} missing")
