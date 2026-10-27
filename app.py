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

from PySide6.QtCore import Qt, QTimer, QItemSelectionModel
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QTabWidget, QSizePolicy,
)

from analyzer import analyze
from generator import generate, fix, validate
import json_utils
import vocabulary
from json_view import JsonView
from scanner import ConfigEntry, scan_mods_folder, load_thumbnail
from zip_handler import write_many_to_zip
from storage import OperationCancelled, check_cancel, write_text_atomic
from theme import COLORS, STATUS_COLOR, STATUS_ICON, STATUS_LABEL, make_dark_style as make_dark_style
from workers import TaskDialog
from i18n import set_language, t
from ui_icons import app_icon, icon
from about import AboutDialog
import game_paths
from dialogs import (
    analyze_dialog, choose_game_dir, confirm_bulk, copy_source_dialog, history_dialog, settings_dialog,
)
import measure
import stock
from rls_contracts import model_key
from editor_form import build_details_form, set_combo, set_insurance
from widgets import CardPreview, NumberItem as _NumberItem, StatusItem as _StatusItem
from widgets import EmptyState, Toast, label, make_button, pill, status_pill

SETTINGS_FILE = Path.home() / ".beamng_infogen.json"


def _load_settings() -> dict:
    try:
        data = json_utils.load_file(SETTINGS_FILE)
        return data
    except (OSError, ValueError):
        return {}


def _save_settings(data: dict):
    write_text_atomic(SETTINGS_FILE, json.dumps(data, indent=2, ensure_ascii=False))


class App(QMainWindow):
    def __init__(self, mods_path: str = None):
        super().__init__()
        self.setWindowTitle("BeamNG Info Config Generator[*]")
        self.setWindowIcon(app_icon())
        self.resize(1240, 860)
        self.setMinimumSize(900, 650)
        self._loading = True
        self._form_dirty = False
        self._json_dirty = False
        self._draft_data = None
        self._previous_tab = 0
        self._busy = False
        self._history = []
        self._settings = _load_settings()
        set_language(self._settings.get("language", "en"))
        self._cancel_event = None
        self._operation_progress = None
        self._scanned_mods_path = None
        self._backup_tip_shown = False
        self._detected_game = None
        self.toast_bottom_offset = 0

        self.mods_data: dict[str, list[ConfigEntry]] = {}
        self.selected_entry: Optional[ConfigEntry]   = None
        self._selection: set[int]                    = set()
        self._status_filter: set[str]                = {"ok", "bad", "missing"}
        # mods with all-ok entries are collapsed by default
        self._collapsed: dict[str, bool]             = {}

        self._build_ui()
        self._toast = Toast(self)
        self._loading = False
        self._restore_layout()
        self._update_status()
        self._sync_list_visibility()

        if mods_path:
            self.folder_edit.setText(mods_path)
            QTimer.singleShot(0, self._scan)
        else:
            self._load_last_path()

        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_current)
        QShortcut(QKeySequence("F5"),     self).activated.connect(self._rescan)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)

    def _load_last_path(self):
        path = _load_settings().get("last_mods_path", "")
        if path and Path(path).exists():
            self.folder_edit.setText(path)
        elif self._detected_mods:
            self.folder_edit.setText(self._detected_mods)

    def _save_last_path(self, path: str):
        s = _load_settings()
        s["last_mods_path"] = path
        _save_settings(s)

    def _button(self, text, icon_name, slot, primary=False):
        return make_button(text, icon_name, slot, "primary" if primary else None)

    def notify(self, text, tone="ok", action=None):
        self.toast_bottom_offset = self._bot_bar.height()
        self._toast.show_message(text, tone, action)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.toast_bottom_offset = self._bot_bar.height()
        if self._toast.isVisible():
            self._toast.reposition()

    def _focus_search(self):
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget()
        top.setObjectName("topBar")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(18, 12, 18, 14)
        top_lay.setSpacing(12)
        branding = QHBoxLayout()
        branding.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(32, 32))
        mark.setFixedSize(32, 32)
        branding.addWidget(mark)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("BeamNG Info Config Generator", "brand"))
        titles.addWidget(label(t("Vehicle configuration metadata for BeamNG.drive 0.40"), "brandSub"))
        branding.addLayout(titles)
        branding.addStretch()
        self.contracts_btn = make_button(t("RLS Contracts"), "trophy", self._show_contracts, "ghost")
        self.contracts_btn.setToolTip(t("Check and extend RLS Career Overhaul contract vehicles"))
        branding.addWidget(self.contracts_btn)
        branding.addWidget(make_button(t("History"), "clock-arrow-left", self._show_history, "ghost"))
        branding.addWidget(make_button(t("Settings"), "settings", self._show_settings, "ghost"))
        self.about_btn = make_button("", "info", self._show_about, "ghost", t("About"))
        branding.addWidget(self.about_btn)
        top_lay.addLayout(branding)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(t("BeamNG mods directory, e.g. ...\\BeamNG.drive\\current\\mods"))
        self.folder_edit.addAction(icon("folder", COLORS["muted"]), QLineEdit.LeadingPosition)
        self.folder_edit.returnPressed.connect(self._scan)
        path_row.addWidget(self.folder_edit, 1)
        self.browse_btn = self._button(t("Browse"), "folder-open", self._browse)
        path_row.addWidget(self.browse_btn)
        self.scan_btn = self._button(t("Scan"), "scan-search", self._scan, True)
        self.scan_btn.setToolTip(t("Scan the mods directory (read-only)"))
        path_row.addWidget(self.scan_btn)
        self.rescan_btn = make_button("", "refresh-cw", self._rescan, tooltip=t("Rescan (F5)"))
        self.rescan_btn.setEnabled(False)
        path_row.addWidget(self.rescan_btn)
        top_lay.addLayout(path_row)
        root.addWidget(top)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        root.addWidget(self.splitter, 1)
        left = QWidget()
        left.setObjectName("sidePanel")
        left.setMinimumWidth(320)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(14, 14, 10, 10)
        left_lay.setSpacing(10)
        header = QHBoxLayout()
        header.addWidget(label(t("Configurations"), "sectionTitle"))
        self.list_badge = label("0", "count")
        header.addWidget(self.list_badge, 0, Qt.AlignVCenter)
        header.addStretch()
        self._table_mode = False
        self._view_btn = make_button("", "table-2", self._toggle_view, "ghost", t("Table view"))
        header.addWidget(self._view_btn)
        left_lay.addLayout(header)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(t("Search mods, configs, vehicle details  (Ctrl+F)"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(icon("search", COLORS["muted"]), QLineEdit.LeadingPosition)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(160)
        self._search_timer.timeout.connect(self._rebuild_view)
        self.search_edit.textChanged.connect(lambda: self._search_timer.start())
        left_lay.addWidget(self.search_edit)
        filters = QHBoxLayout()
        filters.setSpacing(6)
        self._filter_btns = {}
        for status in ("missing", "bad", "ok"):
            btn = make_button(t(STATUS_LABEL[status]), STATUS_ICON[status], kind="chip")
            btn.setIcon(icon(STATUS_ICON[status], STATUS_COLOR[status]))
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setToolTip(t("Show {status} configurations").format(status=t(STATUS_LABEL[status]).lower()))
            btn.clicked.connect(lambda checked=False, s=status: self._toggle_filter(s))
            filters.addWidget(btn)
            self._filter_btns[status] = btn
        filters.addStretch()
        left_lay.addLayout(filters)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(18)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.currentItemChanged.connect(self._on_tree_current)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemExpanded.connect(lambda item: self._collapsed.update({item.data(0, Qt.UserRole + 1): False}))
        self.tree.itemCollapsed.connect(lambda item: self._collapsed.update({item.data(0, Qt.UserRole + 1): True}))
        self._detected_mods = game_paths.detect_user_mods()
        self.empty_state = EmptyState(
            "folder-search", t("Scan your BeamNG mods"),
            t("Find vehicle configurations that are missing info files or have incomplete ones. "
            "Scanning only reads files."))
        if self._detected_mods:
            self.empty_state.add_action(make_button(t("Scan detected folder"), "scan-search",
                                                    self._scan_detected, "primary"))
            self.empty_state.set_hint(self._detected_mods)
        self.empty_state.add_action(make_button(t("Choose mods folder..."), "folder-open", self._browse_and_scan))
        left_lay.addWidget(self.empty_state, 1)
        left_lay.addWidget(self.tree, 1)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["", t("Mod"), t("Config"), t("Drive"), t("Fuel"), t("Trans."), t("Type"), t("Value")])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setMinimumSectionSize(36)
        self.table.setColumnWidth(1, 150)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.setSortingEnabled(True)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.currentCellChanged.connect(lambda row, col, oldrow, oldcol: self._on_table_cell_clicked(row, col))
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        self.table.hide()
        left_lay.addWidget(self.table, 1)
        self.list_count = label(t("No configurations"), "muted")
        left_lay.addWidget(self.list_count)
        self.splitter.addWidget(left)

        editor_container = QWidget()
        editor_container.setObjectName("editorPanel")
        editor_container.setMinimumWidth(480)
        self._editor_lay = QVBoxLayout(editor_container)
        self._editor_lay.setContentsMargins(20, 14, 18, 10)
        self._editor_lay.setSpacing(8)
        self._build_editor(self._editor_lay)
        self.splitter.addWidget(editor_container)
        self.splitter.setSizes([420, 780])

        bot = QWidget()
        self._bot_bar = bot
        bot.setObjectName("botBar")
        bot_lay = QHBoxLayout(bot)
        bot_lay.setContentsMargins(14, 9, 16, 9)
        bot_lay.setSpacing(8)
        self.gen_all_btn = self._button(t("Generate missing"), "file-plus", self._generate_all_missing)
        self.gen_all_btn.setToolTip(t("Create info files for every configuration without one"))
        bot_lay.addWidget(self.gen_all_btn)
        self.fix_all_btn = self._button(t("Fix incomplete"), "wrench", self._fix_all_bad)
        self.fix_all_btn.setToolTip(t("Fill only missing or invalid required fields; other values are kept"))
        bot_lay.addWidget(self.fix_all_btn)
        self.gen_sel_btn = self._button(t("Generate selected (0)"), "sparkles", self._generate_selected)
        bot_lay.addWidget(self.gen_sel_btn)
        self.measure_btn = self._button(t("Measure in game"), "gauge", self._measure_in_game)
        self.measure_btn.setToolTip(t("Start BeamNG with a temporary user folder and measure power, torque, "
                                      "weight and drivetrain of the selected configurations"))
        bot_lay.addWidget(self.measure_btn)
        bot_lay.addWidget(self._button(t("Analyze"), "chart-no-axes-combined", self._show_analyze_dialog))
        bot_lay.addStretch()
        self.status_lbl = label(t("No mods loaded"), "muted")
        bot_lay.addWidget(self.status_lbl)
        root.addWidget(bot)

    def _build_editor(self, layout):
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self.editor_title = QLabel(t("Generation defaults"))
        self.editor_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.editor_title.setObjectName("sectionTitle")
        title_row.addWidget(self.editor_title, 1)
        self.status_badge = pill()
        self.status_badge.hide()
        title_row.addWidget(self.status_badge)
        layout.addLayout(title_row)
        self.source_label = QLineEdit()
        self.source_label.setReadOnly(True)
        self.source_label.setPlaceholderText(t("No configuration selected. Form values are used as generation defaults."))
        self.source_label.addAction(icon("braces", COLORS["faint"]), QLineEdit.LeadingPosition)
        layout.addWidget(self.source_label)
        self.editor_tabs = QTabWidget()
        self.editor_tabs.setDocumentMode(True)
        layout.addWidget(self.editor_tabs, 1)
        self.editor_tabs.addTab(build_details_form(self, self._form_changed), icon("list-tree"), t("Details"))
        self.w_name.setEnabled(False)

        json_tab = QWidget()
        json_layout = QVBoxLayout(json_tab)
        json_layout.setContentsMargins(0, 10, 0, 0)
        self.json_view = JsonView()
        self.json_view.setEnabled(False)
        self.json_view._editor.textChanged.connect(self._json_changed)
        json_layout.addWidget(self.json_view, 1)
        json_tools = QHBoxLayout()
        json_tools.addWidget(self._button(t("Format"), "braces", self._format_json))
        json_tools.addStretch()
        json_layout.addLayout(json_tools)
        self.editor_tabs.addTab(json_tab, icon("braces"), t("JSON"))
        self.editor_tabs.currentChanged.connect(self._switch_editor_tab)

        self._card = CardPreview()
        preview_page = QWidget()
        preview_page.setObjectName("formPage")
        preview_layout = QVBoxLayout(preview_page)
        preview_layout.setContentsMargins(0, 14, 0, 0)
        preview_layout.addWidget(self._card, 0, Qt.AlignHCenter)
        preview_layout.addWidget(label(t("Approximation of the vehicle selector tile."), "muted"), 0, Qt.AlignHCenter)
        preview_layout.addStretch()
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setWidget(preview_page)
        self.editor_tabs.addTab(preview_scroll, icon("eye"), t("Preview"))

        self.lbl_missing = label("", "notice", wrap=True)
        layout.addWidget(self.lbl_missing)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.save_btn = self._button(t("Save"), "save", self._save_current, True)
        self.save_btn.setToolTip(t("Save (Ctrl+S)"))
        self.regen_btn = self._button(t("Regenerate"), "rotate-ccw", self._regen_current)
        self.regen_btn.setToolTip(t("Replace the whole info file using the form values"))
        self.copy_btn = self._button(t("Copy from..."), "copy", self._copy_from_dialog)
        self.copy_btn.setToolTip(t("Copy values from another configuration into the form"))
        self.stock_btn = self._button(t("From stock"), "car-front", self._fill_from_stock)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.regen_btn)
        buttons.addWidget(self.copy_btn)
        buttons.addWidget(self.stock_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        for button in (self.save_btn, self.regen_btn, self.copy_btn, self.stock_btn):
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
        entries = [e for es in self.mods_data.values() for e in es]
        for status, button in self._filter_btns.items():
            checked = status in self._status_filter
            button.setChecked(checked)
            button.setText(f"{t(STATUS_LABEL[status])}  {sum(e.status == status for e in entries)}")
            button.setIcon(icon(STATUS_ICON[status], STATUS_COLOR[status] if checked else COLORS["faint"]))

    def _rebuild_tree(self):
        self.tree.blockSignals(True)
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        bold = QFont(self.tree.font())
        bold.setWeight(QFont.DemiBold)
        for mod_name, entries in self.mods_data.items():
            visible = [e for e in entries if self._matches(mod_name, e)]
            if not visible:
                continue
            problems = sum(e.status != "ok" for e in entries)
            parent = QTreeWidgetItem([mod_name, str(problems) if problems else ""])
            parent.setData(0, Qt.UserRole + 1, mod_name)
            parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
            parent.setFont(0, bold)
            parent.setIcon(0, icon("package", COLORS["muted"]))
            parent.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            parent.setToolTip(0, f"{mod_name}\n{len(entries)} configuration(s)")
            if problems:
                parent.setIcon(1, icon("triangle-alert", COLORS["warn"]))
                parent.setForeground(1, QColor(COLORS["warn"]))
                parent.setFont(1, bold)
                parent.setToolTip(1, t("{problems} of {total} configuration(s) need attention").format(
                    problems=problems, total=len(entries)))
            else:
                parent.setIcon(1, icon("circle-check", COLORS["ok"]))
                parent.setToolTip(1, t("All {total} configuration(s) are valid").format(total=len(entries)))
            self.tree.addTopLevelItem(parent)
            for entry in visible:
                child = QTreeWidgetItem([entry.config_name])
                child.setIcon(0, icon(STATUS_ICON[entry.status], STATUS_COLOR[entry.status]))
                child.setData(0, Qt.UserRole, entry)
                child.setToolTip(0, f"{t(STATUS_LABEL[entry.status])}\n{entry.info_path or entry.pc_path}")
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
        total = sum(map(len, self.mods_data.values()))
        self.list_badge.setText(str(total))
        self.list_count.setText(t("{shown} shown of {total}").format(shown=len(visible_ids), total=total)
                                if total else t("No configurations"))
        self._sync_list_visibility()
        self._update_sel_button()

    def _sync_list_visibility(self):
        empty = not self.mods_data
        self.empty_state.setVisible(empty)
        self.tree.setVisible(not empty and not self._table_mode)
        self.table.setVisible(not empty and self._table_mode)
        if empty and self._scanned_mods_path:
            self.empty_state.title.setText(t("No vehicle configurations found"))
            self.empty_state.text.setText(t("This folder has no vehicles/*/*.pc files. Pick the BeamNG mods "
                                          "folder in your user folder, not the game installation."))

    def _scan_detected(self):
        self.folder_edit.setText(self._detected_mods)
        self._scan()

    def _browse_and_scan(self):
        before = self.folder_edit.text()
        self._browse()
        if self.folder_edit.text() != before or Path(before).is_dir():
            self._scan()

    def _toggle_view(self):
        self._table_mode = not self._table_mode
        self._view_btn.setIcon(icon("list-tree" if self._table_mode else "table-2"))
        self._view_btn.setToolTip(t("Tree view") if self._table_mode else t("Table view"))
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
                        item.setToolTip(STATUS_LABEL[entry.status])
                    if column in (1, 2):
                        item.setToolTip(str(value))
                    if column == 1:
                        item.setForeground(QColor(COLORS["muted"]))
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
        self.gen_sel_btn.setText(t("Generate selected ({count})").format(count=n))
        self.gen_sel_btn.setEnabled(n > 0 and not self._busy)

    def _maybe_auto_collapse(self, mod_name):
        entries = self.mods_data.get(mod_name, [])
        if entries and all(e.status == "ok" for e in entries):
            self._collapsed[mod_name] = True

    def _refresh_entry_item(self, entry):
        self._rebuild_view()

    def _fill_form_data(self, data, auto):
        for widget, key, fallback in (
            (self.w_config_type, "Config Type", "Factory"),
            (self.w_drivetrain, "Drivetrain", auto.get("Drivetrain", "RWD")),
            (self.w_transmission, "Transmission", auto.get("Transmission", "Automatic")),
            (self.w_fuel, "Fuel Type", auto.get("Fuel Type", "Gasoline")),
            (self.w_body, "Body Style", "Sedan"),
            (self.w_induction, "Induction Type", vocabulary.DEFAULT_INDUCTION),
        ):
            set_combo(widget, data.get(key, fallback))
        set_insurance(self.w_insurance, data.get("InsuranceClass", ""))
        self.w_region.set_value(data.get("Region"))
        population = data.get("Population")
        valid_population = isinstance(population, (int, float)) and not isinstance(population, bool)
        self.w_population.setText(str(int(population)) if valid_population else "")
        paint = data.get("defaultPaintName1")
        self.w_paint.setText(paint if isinstance(paint, str) else "")
        self.w_name.setText(str(data.get("Configuration") or self.selected_entry.config_name))
        for widget, key in ((self.w_power, "Power"), (self.w_torque, "Torque"), (self.w_weight, "Weight")):
            val = data.get(key, "")
            widget.setText(str(val) if val is not None else "")
        years = data.get("Years") if isinstance(data.get("Years"), dict) else {}
        self.w_year_min.setText(str(years.get("min", "")))
        self.w_year_max.setText(str(years.get("max", "")))
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
        status_pill(self.status_badge, entry.status)
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
            t("Unreadable info: {error}").format(error=entry.parse_error) if entry.parse_error else
            (t("Missing or invalid: {fields}").format(fields=", ".join(entry.missing_fields))
             if entry.missing_fields else
             (t("No info file yet. Save creates it from the form.") if entry.status == "missing" else ""))
        )
        self._form_dirty = self._json_dirty = False
        self.setWindowModified(False)
        self._previous_tab = self.editor_tabs.currentIndex()
        self._loading = False
        self._update_stock_button(entry)
        self._refresh_card()

    def _game_dir(self):
        chosen = self._settings.get("game_dir")
        if game_paths.is_game_dir(chosen):
            return chosen
        if self._detected_game is None:
            self._detected_game = game_paths.detect_game_dir()
        return self._detected_game

    def _update_stock_button(self, entry):
        game = self._game_dir()
        key = model_key(entry)
        if not game:
            self.stock_btn.setEnabled(True)
            self.stock_btn.setToolTip(t("Fill the form from the stock vehicle. The game folder will be requested."))
        elif key and stock.is_stock_model(game, key):
            self.stock_btn.setEnabled(True)
            self.stock_btn.setToolTip(t("Fill the form with typical values of the stock '{model}' model").format(model=key))
        else:
            self.stock_btn.setEnabled(False)
            self.stock_btn.setToolTip(t("'{model}' is not a stock BeamNG model").format(model=key or "?"))

    def _stock_for(self, entry):
        key = model_key(entry)
        game = self._game_dir()
        return stock.suggestions(game, key) if key and game else {}

    def _with_stock(self, entry, data, defaults):
        """Prefer the stock model's typical values over generic generation defaults."""
        if not self._settings.get("use_stock_data", True):
            return data
        values = self._stock_for(entry)
        if not values:
            return data
        data = dict(data)
        for key in ("Value", "Body Style"):
            if key in values:
                data[key] = values[key]
        for key in ("Power", "Torque", "Weight", "Years", "Region", "defaultPaintName1", "InsuranceClass"):
            if key in values and key not in data:
                data[key] = values[key]
        return data

    def _stock_price_fix(self, entry, data):
        """When Fix had to invent a price, use the stock model's typical price instead."""
        if "Value" not in validate(entry.info_content or {}) or not self._settings.get("use_stock_data", True):
            return data
        value = self._stock_for(entry).get("Value")
        return {**data, "Value": value} if value else data

    def _require_game_dir(self):
        """Return the game folder, asking the user to choose it when it was not found."""
        game = self._game_dir()
        if game:
            return game
        if QMessageBox.question(
                self, t("BeamNG.drive not found"),
                t("The game installation was not found automatically.\n\n"
                  "Choose the BeamNG.drive folder?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return ""
        path = choose_game_dir(self)
        if not path:
            return ""
        self._settings["game_dir"] = path
        try:
            _save_settings(self._settings)
        except OSError as exc:
            QMessageBox.warning(self, t("Settings"), str(exc))
        return path

    def _measure_in_game(self):
        if self._busy or not self._confirm_changes():
            return
        all_entries = {id(e): e for es in self.mods_data.values() for e in es}
        entries = [all_entries[eid] for eid in self._selection if eid in all_entries]
        if not entries and self.selected_entry is not None:
            entries = [self.selected_entry]
        entries = [e for e in entries if measure.config_key(e)]
        if not entries:
            self.notify(t("Select the configurations to measure first."), "warn")
            return
        game = self._require_game_dir()
        if not game:
            return
        minutes = max(1, round((60 + 10 * len(entries)) / 60))
        if QMessageBox.question(
                self, t("Measure in game"),
                t("BeamNG.drive will start in its own window with a temporary user folder and measure "
                  "{count} configuration(s). This takes about {minutes} min; the game closes by itself.\n\n"
                  "Your mods, settings and saves are not changed. Results are shown for review before "
                  "anything is written.").format(count=len(entries), minutes=minutes),
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes) != QMessageBox.Yes:
            return

        def task(cancel, progress):
            progress(0, len(entries), t("Preparing a temporary user folder"))
            session = measure.prepare(entries)
            try:
                measure.launch(session, game)
                return measure.wait(session, cancel, lambda done, total, _text: progress(
                    done, total, t("Measuring in BeamNG.drive: {done} of {total}").format(done=done, total=total)))
            finally:
                measure.cleanup(session)

        started = time.monotonic()
        self._busy = True
        worker = TaskDialog(t("Measure in game"), task, self).execute()
        self._busy = False
        self._history.append({"time": datetime.now().isoformat(timespec="seconds"), "operation": "Measure",
                              "completed": len((worker.value or {}).get("results", [])),
                              "cancelled": worker.cancelled, "seconds": time.monotonic() - started,
                              "errors": [worker.error] if worker.error else []})
        if worker.cancelled:
            self.notify(t("Measuring cancelled"), "warn")
            return
        if worker.error:
            QMessageBox.critical(self, t("Measure in game"), worker.error)
            return
        measured, errors = measure.match_results(entries, worker.value or {})
        self._history[-1]["errors"].extend(errors)
        defaults = self._editor_defaults()
        pairs = []
        for entry in entries:
            if id(entry) not in measured:
                continue
            if entry.status != "missing" and isinstance(entry.info_content, dict) and not entry.parse_error:
                base = dict(entry.info_content)
            else:
                base = self._with_stock(entry, generate(entry.config_name, entry.auto_detected, defaults), defaults)
            pairs.append((entry, {**base, **measured[id(entry)]}))
        if errors:
            QMessageBox.warning(self, t("Measure in game"),
                                t("{count} configuration(s) could not be measured.").format(count=len(errors))
                                + "\n\n" + "\n".join(errors[:8]))
        pairs = self._confirm_bulk(t("Apply measured values"), pairs, allow_scope=False)
        if not pairs:
            return
        groups = self._write_groups_for_pairs(pairs)

        def done(n):
            self._rebuild_view()
            self._update_status(updated=n)
            if self.selected_entry and any(e is self.selected_entry for e, _ in pairs):
                self._load_to_editor(self.selected_entry)

        self._run_batch(t("Writing measured values"), groups, self._write_entry_pairs, done)

    def _fill_from_stock(self):
        entry = self.selected_entry
        if entry is None:
            return
        if not self._game_dir():
            if not self._require_game_dir():
                return
            self._update_stock_button(entry)
            if not self.stock_btn.isEnabled():
                self.notify(t("'{model}' is not a stock BeamNG model").format(model=model_key(entry)), "warn")
                return
        values = self._stock_for(entry)
        if not values:
            self.notify(t("No stock data for this model"), "warn")
            return
        filled = 0
        if "Body Style" in values:
            set_combo(self.w_body, values["Body Style"])
            filled += 1
        if isinstance(values.get("InsuranceClass"), str):
            set_insurance(self.w_insurance, values["InsuranceClass"])
            filled += 1
        for widget, key in ((self.w_power, "Power"), (self.w_torque, "Torque"), (self.w_weight, "Weight"),
                            (self.w_paint, "defaultPaintName1")):
            if key in values:
                widget.setText(str(values[key]))
                filled += 1
        if "Value" in values:
            self.w_price_min.setText(str(values["Value"]))
            self.w_price_max.setText(str(values["Value"]))
            filled += 1
        years = values.get("Years")
        if isinstance(years, dict) and years.get("min") and years.get("max"):
            self.w_year_min.setText(str(years["min"]))
            self.w_year_max.setText(str(years["max"]))
            filled += 1
        if "Region" in values:
            self.w_region.set_value(values["Region"])
            self._form_changed()
            filled += 1
        self.notify(t("Filled {count} fields from stock {model} ({configs} configurations). Review, then Save.")
                    .format(count=filled, model=values["_label"], configs=values["_configs"]), "ok")

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
            "InsuranceClass": self.w_insurance.currentText() if self.w_insurance.currentData() else "",
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
            "insurance_class": self.w_insurance.currentData() or "",
            "power":       self.w_power.text(),
            "torque":      self.w_torque.text(),
            "weight":      self.w_weight.text(),
            "price_min":   self.w_price_min.text() or "10000",
            "price_max":   self.w_price_max.text() or "50000",
            "description": self.w_description.toPlainText(),
        }

    def _editor_years(self):
        texts = [self.w_year_min.text().strip(), self.w_year_max.text().strip()]
        if not any(texts):
            return None
        # A single year means the model was built in that year only.
        low, high = sorted(int(text or next(value for value in texts if value)) for text in texts)
        if low < 1886:
            raise ValueError("Years must be 1886 or later")
        return {"min": low, "max": high}

    def _build_data_from_editor(self, entry):
        d = self._editor_defaults()
        data = dict(self._draft_data if self._draft_data is not None else entry.info_content or {})
        data.update({
            "Configuration": self.w_name.text().strip() or entry.config_name,
            "Config Type": self.w_config_type.currentText(),
            "Drivetrain": self.w_drivetrain.currentText(),
            "Transmission": self.w_transmission.currentText(),
            "Fuel Type": self.w_fuel.currentText(),
            "Propulsion": vocabulary.propulsion_for(self.w_fuel.currentText()),
            "Induction Type": d["induction"],
            "Body Style": d["body_style"],
            "Description": d["description"],
        })
        if d["insurance_class"]:
            data["InsuranceClass"] = d["insurance_class"]
        else:
            data.pop("InsuranceClass", None)
        years = self._editor_years()
        if years:
            data["Years"] = years
        else:
            data.pop("Years", None)
        population = self.w_population.text().strip()
        data["Population"] = int(population) if population else data.get("Population", 5000)
        paint = self.w_paint.text().strip()
        if paint:
            data["defaultPaintName1"] = paint
        else:
            data.pop("defaultPaintName1", None)
        regions = self.w_region.value()
        original = data.get("Region")
        if regions and regions == ([original] if isinstance(original, str) else original):
            pass  # Keep the file's own string-or-list spelling when unchanged.
        elif regions:
            data["Region"] = regions
        else:
            data.pop("Region", None)
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
                    raise ValueError(t("{field} must be greater than zero or blank").format(field=key))
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
            QMessageBox.warning(self, t("Invalid draft"), str(exc))
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
            QMessageBox.warning(self, t("Invalid JSON"), str(exc))

    def _confirm_changes(self):
        if not (self._form_dirty or self._json_dirty):
            return True
        answer = QMessageBox.question(
            self, t("Unsaved changes"), t("Save changes to the current configuration?"),
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
            QMessageBox.warning(self, t("Settings"), str(exc))
        event.accept()

    def _show_about(self):
        AboutDialog(self).exec()

    def _show_settings(self):
        values = settings_dialog(self, self._settings)
        if values is None:
            return
        language_changed = values.get("language", "en") != self._settings.get("language", "en")
        self._settings.update(values)
        if self.selected_entry:
            self._update_stock_button(self.selected_entry)
        if language_changed:
            self.notify(t("Restart the application to switch the language."), "info")
        try:
            _save_settings(self._settings)
        except OSError as exc:
            QMessageBox.warning(self, t("Settings"), str(exc))

    def _show_history(self):
        history_dialog(self, self._history)

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
        path = QFileDialog.getExistingDirectory(self, t("Select mods folder"), self.folder_edit.text().strip())
        if path:
            self.folder_edit.setText(path)

    def _show_contracts(self):
        if self._busy or not self._confirm_changes():
            return
        path = self.folder_edit.text().strip()
        if not Path(path).is_dir():
            QMessageBox.warning(self, t("RLS Contracts"), t("Select a valid mods directory first."))
            return
        if self._scanned_mods_path != str(Path(path).resolve()):
            self._scan()
            if self._scanned_mods_path != str(Path(path).resolve()):
                return
        from rls_dialog import ContractsDialog
        entries = [entry for group in self.mods_data.values() for entry in group]
        selected = {key for entry in entries if id(entry) in self._selection
                    if (key := model_key(entry))}
        ContractsDialog(path, entries, selected_keys=selected, parent=self).exec()

    def _scan(self):
        if self._busy or not self._confirm_changes():
            return
        path = self.folder_edit.text().strip()
        if not Path(path).is_dir():
            QMessageBox.warning(self, t("Mods directory"), t("Select a valid folder."))
            return
        issues = []
        def task(cancel, progress):
            return scan_mods_folder(path, issues=issues, progress=progress, cancel=cancel)
        started = time.monotonic()
        self._busy = True
        worker = TaskDialog(t("Scanning mods"), task, self).execute()
        self._busy = False
        self._history.append({"time": datetime.now().isoformat(timespec="seconds"), "operation": "Scan",
                              "completed": sum(map(len, worker.value.values())) if worker.value is not None else 0,
                              "cancelled": worker.cancelled, "seconds": time.monotonic() - started,
                              "errors": issues + ([worker.error] if worker.error else [])})
        if worker.error:
            QMessageBox.critical(self, t("Scan failed"), worker.error)
            return
        if worker.cancelled:
            self.notify(t("Scan cancelled"), "warn")
            return
        self.mods_data = worker.value
        self._scanned_mods_path = str(Path(path).resolve())
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
        configs = sum(map(len, self.mods_data.values()))
        self.notify(t("Scanned {mods} mods, {configs} configurations").format(
            mods=len(self.mods_data), configs=configs), "ok")
        if issues:
            QMessageBox.warning(self, t("Scan completed with issues"), t("{count} unreadable files. See History for details.").format(count=len(issues))
                                + "\n\n" + "\n".join(issues[:3]))

    def _clear_editor(self):
        self._loading = True
        self._form_dirty = self._json_dirty = False
        self._draft_data = None
        self.setWindowModified(False)
        self.editor_title.setText(t("Generation defaults"))
        self.status_badge.hide()
        self.source_label.clear()
        self.w_name.clear()
        self.w_name.setEnabled(False)
        self.json_view.set_raw("")
        self.json_view.setEnabled(False)
        self.lbl_missing.clear()
        self._card.clear()
        for button in (self.save_btn, self.regen_btn, self.copy_btn, self.stock_btn):
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
            QMessageBox.warning(self, t("Invalid values"), str(exc))
            return False
        if entry.parse_error and QMessageBox.question(
                self, t("Replace unreadable info"), t("Replace the unreadable info file with form values?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        def done(_):
            self._refresh_entry_item(entry)
            self._load_to_editor(entry)
            self._update_status()
        return self._run_batch(t("Save configuration"), [entry],
                               lambda _: self._write_entry(entry, data, refresh=False), done)

    def _regen_current(self):
        if not self.selected_entry or self._busy:
            return
        entry = self.selected_entry
        if QMessageBox.question(self, t("Regenerate configuration"),
                t("Replace this info file completely using the current defaults?"),
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
        self._run_batch(t("Regenerate configuration"), [entry],
                        lambda _: self._write_entry(entry, regen, refresh=False), done)

    def _save_json_current(self):
        if not self.selected_entry or self._busy:
            return False
        try:
            data = json_utils.loads(self.json_view.get_raw_text().strip())
            json.dumps(data, allow_nan=False)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, t("Invalid JSON"), str(exc))
            return False
        missing = validate(data)
        if missing and QMessageBox.question(
                self, t("Incomplete configuration"), t("Save with invalid fields: {fields}?").format(fields=", ".join(missing)),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        entry = self.selected_entry
        def done(_):
            self._refresh_entry_item(entry)
            self._load_to_editor(entry)
            self._update_status()
        return self._run_batch(t("Save JSON"), [entry],
                               lambda _: self._write_entry(entry, data, refresh=False), done)

    def _confirm_bulk(self, title, pairs, allow_scope=True):
        """Preview a bulk write; returns the pairs to write or None."""
        if not pairs:
            return None
        visible = {id(e) for name, es in self.mods_data.items() for e in es if self._matches(name, e)}
        enabled = bool(self._settings.get("backup_writes", False))
        result = confirm_bulk(self, title, pairs, visible, enabled, allow_scope)
        if result is None:
            return None
        chosen, backup = result
        if backup != enabled:
            self._settings["backup_writes"] = backup
            try:
                _save_settings(self._settings)
            except OSError as exc:
                QMessageBox.warning(self, t("Settings"), str(exc))
        return chosen

    def _generate_all_missing(self):
        if self._busy or not self._confirm_changes():
            return
        defaults = self._editor_defaults()
        pairs = [
            (e, self._with_stock(e, generate(e.config_name, e.auto_detected, defaults), defaults))
            for es in self.mods_data.values()
            for e in es if e.status == "missing"
        ]
        pairs = self._confirm_bulk(t("Generate missing info files"), pairs)
        if not pairs:
            return
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

        self._run_batch(t("Generating..."), groups, work, done,
                        subtitle=t("Generating missing info configs..."))

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
        pairs = [
            (e, self._with_stock(e, generate(e.config_name, auto_override, defaults), defaults))
            for e in entries
        ]
        pairs = self._confirm_bulk(t("Generate selected info files"), pairs, allow_scope=False)
        if not pairs:
            return
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

        self._run_batch(t("Generating..."), groups, work, done,
                        subtitle=t("Generating selected configs..."))

    def _fix_all_bad(self):
        if self._busy or not self._confirm_changes():
            return
        unreadable = [e for es in self.mods_data.values() for e in es if e.parse_error]
        if unreadable:
            QMessageBox.warning(self, t("Unreadable info files"),
                                t("{count} unreadable files will be skipped. Their raw content is available in the JSON tab.")
                                .format(count=len(unreadable)))
        defaults = self._editor_defaults()
        pairs = [
            (e, self._stock_price_fix(e, fix(e.info_content or {}, e.config_name, e.auto_detected, defaults)))
            for es in self.mods_data.values()
            for e in es if e.status == "bad" and not e.parse_error
        ]
        pairs = self._confirm_bulk(t("Fix incomplete info files"), pairs)
        if not pairs:
            return
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

        self._run_batch(t("Fixing..."), groups, work, done,
                        subtitle=t("Filling missing fields in existing configs..."))

    def _show_analyze_dialog(self):
        analyze_dialog(self, analyze(self.mods_data))

    def _copy_from_dialog(self):
        if not self.selected_entry or not self.mods_data:
            return
        source = copy_source_dialog(self, self.mods_data, self.selected_entry)
        if source is not None:
            self._apply_copy(source)

    def _apply_copy(self, source: ConfigEntry):
        data = source.info_content or {}

        for widget, key in ((self.w_config_type, "Config Type"), (self.w_drivetrain, "Drivetrain"),
                            (self.w_transmission, "Transmission"), (self.w_fuel, "Fuel Type"),
                            (self.w_body, "Body Style"), (self.w_induction, "Induction Type")):
            if data.get(key):
                set_combo(widget, data[key])
        if data.get("InsuranceClass"):
            set_insurance(self.w_insurance, data["InsuranceClass"])

        for widget, key in [(self.w_power, "Power"), (self.w_torque, "Torque"),
                             (self.w_weight, "Weight")]:
            val = data.get(key)
            if val is not None and val != "":
                widget.setText(str(val))
        years = data.get("Years")
        if isinstance(years, dict) and years.get("min") and years.get("max"):
            self.w_year_min.setText(str(years["min"]))
            self.w_year_max.setText(str(years["max"]))

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
            QMessageBox.warning(self, t("Operation completed with errors"),
                                t("{done} / {total} configurations written.").format(done=result["completed"], total=total) + "\n\n" +
                                "\n".join(result["errors"][:5]))
        elif result["cancelled"]:
            self.notify(t("Cancelled. {done} of {total} configurations written.").format(
                done=result["completed"], total=total), "warn")
        else:
            self._notify_written(result["completed"], result["seconds"])
        return result["completed"] == total and not result["errors"] and not result["cancelled"]

    def _notify_written(self, count, seconds):
        text = t("{count} configuration(s) written in {seconds}s").format(count=count, seconds=f"{seconds:.2f}")
        if not self._settings.get("backup_writes", False) and not self._backup_tip_shown:
            self._backup_tip_shown = True
            self.notify(text + ".\n" + t("Backups are off. Turn them on to keep a .bak copy of every changed file."),
                        "info", ("Settings", self._show_settings))
            return
        self.notify(text, "ok")

    def _update_status(self, created=0, updated=0):
        entries = [e for es in self.mods_data.values() for e in es]
        missing = sum(e.status == "missing" for e in entries)
        bad = sum(e.status == "bad" for e in entries)
        valid = sum(e.status == "ok" for e in entries)
        self._update_filter_buttons()
        self.gen_all_btn.setEnabled(missing > 0 and not self._busy)
        self.fix_all_btn.setEnabled(bad > 0 and not self._busy)
        self._update_sel_button()
        if not self.mods_data:
            self.status_lbl.setText(t("No mods loaded"))
            return
        self.status_lbl.setText(t("{mods} mods  ·  {total} configurations  ·  {valid} valid  ·  "
                                  "{bad} incomplete  ·  {missing} missing").format(
            mods=len(self.mods_data), total=len(entries), valid=valid, bad=bad, missing=missing))
