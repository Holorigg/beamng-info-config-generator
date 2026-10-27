"""Secondary dialogs of the main window: settings, history, analysis, copy source."""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout,
)

import game_paths
from i18n import LANGUAGES, t
from storage import write_text_atomic
from theme import COLORS, STATUS_COLOR, STATUS_ICON
from ui_icons import icon
from widgets import label, make_button


def _dialog(parent, title, width, height=None):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    if height:
        dialog.resize(width, height)
    else:
        dialog.setMinimumWidth(width)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 18, 20, 16)
    layout.setSpacing(10)
    layout.addWidget(label(title, "sectionTitle"))
    return dialog, layout


def choose_game_dir(parent, start=""):
    """Ask for the BeamNG.drive installation folder; returns a valid path or ''."""
    while True:
        path = QFileDialog.getExistingDirectory(parent, t("Select the BeamNG.drive game folder"), start)
        if not path:
            return ""
        if game_paths.is_game_dir(path):
            return path
        if QMessageBox.question(
                parent, t("Not a game folder"),
                t("This folder has no content/vehicles. Choose the folder that contains BeamNG.drive.exe."),
                QMessageBox.Retry | QMessageBox.Cancel, QMessageBox.Retry) != QMessageBox.Retry:
            return ""
        start = path


def settings_dialog(parent, settings: dict) -> dict | None:
    """Return updated settings values, or None when cancelled."""
    dialog, layout = _dialog(parent, t("Settings"), 520)

    layout.addWidget(label(t("GAME"), "groupTitle"))
    game = {"dir": settings.get("game_dir") if game_paths.is_game_dir(settings.get("game_dir")) else ""}
    game_row = QHBoxLayout()
    game_edit = QLineEdit()
    game_edit.setReadOnly(True)
    game_edit.addAction(icon("gamepad-2", COLORS["muted"]), QLineEdit.LeadingPosition)
    game_row.addWidget(game_edit, 1)
    game_status = label("", "muted", wrap=True)

    def show_game():
        path = game["dir"] or game_paths.detect_game_dir()
        game_edit.setText(path)
        game_edit.setPlaceholderText(t("BeamNG.drive was not found"))
        version = game_paths.game_version(path) if path else ""
        if path:
            game_status.setText((t("Detected automatically") if not game["dir"] else t("Chosen manually"))
                                + ("  ·  " + t("version {version}").format(version=version) if version else ""))
        else:
            game_status.setText(t("Not found. Stock vehicle data is unavailable until you choose the game folder."))

    def browse_game():
        path = choose_game_dir(dialog, game_edit.text())
        if path:
            game["dir"] = path
            show_game()

    def detect_game():
        game["dir"] = ""
        show_game()
    game_row.addWidget(make_button(t("Browse"), "folder-open", browse_game))
    game_row.addWidget(make_button("", "rotate-ccw", detect_game, tooltip=t("Detect automatically")))
    layout.addLayout(game_row)
    layout.addWidget(game_status)
    show_game()
    use_stock = QCheckBox(t("Use stock vehicle data when generating"))
    use_stock.setChecked(bool(settings.get("use_stock_data", True)))
    use_stock.setToolTip(t("For mods based on a stock model, generated files take price, power, torque, "
                         "weight, years, body style, region and insurance class from the game's own files."))
    layout.addWidget(use_stock)
    layout.addSpacing(6)

    layout.addWidget(label(t("WRITING"), "groupTitle"))
    layout.addWidget(label(t("ZIP write mode"), "fieldLabel"))
    mode = QComboBox()
    for text, value in (("Automatic (append / disk)", "auto"), ("Disk", "disk"), ("RAM", "ram")):
        mode.addItem(t(text), value)
    mode.setCurrentIndex(max(0, mode.findData(settings.get("zip_mode", "auto"))))
    mode.setToolTip(t("Automatic appends new files. Disk and RAM rebuild the archive. "
                    "Replacements are committed through a temporary file next to the mod."))
    layout.addWidget(mode)
    layout.addWidget(label(t("Automatic appends new files without rewriting the archive."), "muted", wrap=True))
    layout.addSpacing(6)
    backup = QCheckBox(t("Back up before writes"))
    backup.setChecked(bool(settings.get("backup_writes", False)))
    backup.setToolTip(t("Keeps dated .bak files next to originals. A ZIP backup requires space for the entire archive."))
    layout.addWidget(backup)
    layout.addWidget(label(t("Dated .bak copies are kept next to each changed file."), "muted", wrap=True))
    layout.addSpacing(6)

    layout.addWidget(label(t("INTERFACE"), "groupTitle"))
    language = QComboBox()
    for code, name in LANGUAGES.items():
        language.addItem(name, code)
    language.setCurrentIndex(max(0, language.findData(settings.get("language", "en"))))
    layout.addWidget(label(t("Language"), "fieldLabel"))
    layout.addWidget(language)
    layout.addWidget(label(t("Takes effect after restarting the application."), "muted"))
    layout.addSpacing(8)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.button(QDialogButtonBox.Save).setIcon(icon("save"))
    buttons.button(QDialogButtonBox.Save).setObjectName("primary")
    buttons.button(QDialogButtonBox.Cancel).setIcon(icon("x"))
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() != QDialog.Accepted:
        return None
    return {"zip_mode": mode.currentData(), "backup_writes": backup.isChecked(),
            "game_dir": game["dir"], "use_stock_data": use_stock.isChecked(),
            "language": language.currentData()}


def history_dialog(parent, history: list):
    dialog, layout = _dialog(parent, t("Operation history"), 760, 500)
    entries = QTreeWidget()
    entries.setHeaderLabels([t("Operation"), t("Written"), t("Time"), t("Duration")])
    entries.setRootIsDecorated(True)
    entries.setAlternatingRowColors(True)
    for item in reversed(history):
        errors = item.get("errors", [])
        tone = "missing" if errors else "bad" if item.get("cancelled") else "ok"
        row = QTreeWidgetItem([str(item.get("operation", "")), str(item.get("completed", 0)),
                               str(item.get("time", "")), f"{item.get('seconds', 0):.2f}s"])
        row.setIcon(0, icon(STATUS_ICON[tone] if tone != "missing" else "circle-x", STATUS_COLOR[tone]))
        for error in errors:
            child = QTreeWidgetItem([str(error)])
            child.setForeground(0, QColor(COLORS["danger"]))
            child.setToolTip(0, str(error))
            row.addChild(child)
        entries.addTopLevelItem(row)
    entries.header().resizeSection(0, 360)
    layout.addWidget(entries, 1)
    if not history:
        entries.hide()
        layout.addWidget(label(t("No operations yet."), "muted"), 1, Qt.AlignCenter)
    row = QHBoxLayout()

    def export():
        path, _ = QFileDialog.getSaveFileName(dialog, t("Export history"), "operations.json", "JSON (*.json)")
        if path:
            try:
                write_text_atomic(path, json.dumps(history, indent=2, ensure_ascii=False))
            except OSError as exc:
                QMessageBox.warning(dialog, t("Export failed"), str(exc))
    export_button = make_button(t("Export"), "download", export)
    export_button.setEnabled(bool(history))
    row.addWidget(export_button)
    row.addStretch()
    row.addWidget(make_button(t("Close"), "x", dialog.accept))
    layout.addLayout(row)
    dialog.exec()


def analyze_dialog(parent, report: dict):
    dialog, layout = _dialog(parent, t("Analyze"), 640, 520)
    critical = sum(len(cfg["critical"]) for configs in report.values() for cfg in configs)
    warnings = sum(len(cfg["warnings"]) for configs in report.values() for cfg in configs)
    layout.addWidget(label(
        t("{critical} critical issue(s) and {warnings} warning(s) across {mods} mod(s).").format(
            critical=critical, warnings=warnings, mods=len(report))
        if report else t("All configurations look good."), "muted"))
    if report:
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setIndentation(18)
        layout.addWidget(tree, 1)
        for mod_name, configs in report.items():
            mod_item = QTreeWidgetItem([mod_name])
            mod_item.setIcon(0, icon("package"))
            mod_item.setFont(0, QFont("Segoe UI", 10, QFont.DemiBold))
            tree.addTopLevelItem(mod_item)
            for cfg in configs:
                cfg_item = QTreeWidgetItem([cfg["config_name"]])
                cfg_item.setIcon(0, icon("car-front", COLORS["muted"]))
                mod_item.addChild(cfg_item)
                for message, icon_name, color in (
                    *((m, "circle-x", COLORS["danger"]) for m in cfg["critical"]),
                    *((m, "triangle-alert", COLORS["warn"]) for m in cfg["warnings"]),
                ):
                    child = QTreeWidgetItem([t(message)])
                    child.setIcon(0, icon(icon_name, color))
                    child.setToolTip(0, message)
                    cfg_item.addChild(child)
            mod_item.setExpanded(True)
            for i in range(mod_item.childCount()):
                mod_item.child(i).setExpanded(True)
    else:
        layout.addStretch()
    row = QHBoxLayout()
    if report:
        def copy_report():
            lines = []
            for mod_name, configs in report.items():
                lines.append(mod_name)
                for cfg in configs:
                    lines.append(f"  {cfg['config_name']}")
                    lines.extend(f"    [CRITICAL] {m}" for m in cfg["critical"])
                    lines.extend(f"    [WARNING]  {m}" for m in cfg["warnings"])
            QApplication.clipboard().setText("\n".join(lines))
        row.addWidget(make_button(t("Copy report"), "copy", copy_report))
    row.addStretch()
    row.addWidget(make_button(t("Close"), "x", dialog.accept))
    layout.addLayout(row)
    dialog.exec()


def copy_source_dialog(parent, mods_data: dict, current):
    """Let the user pick another configuration with info data; returns it or None."""
    dialog, layout = _dialog(parent, t("Copy fields from"), 480, 540)
    layout.addWidget(label(t("Values are copied into the form. Nothing is saved until you click Save."),
                           "muted", wrap=True))
    search = QLineEdit()
    search.setPlaceholderText(t("Filter configurations"))
    search.setClearButtonEnabled(True)
    search.addAction(icon("search", COLORS["muted"]), QLineEdit.LeadingPosition)
    layout.addWidget(search)
    listbox = QListWidget()
    layout.addWidget(listbox, 1)
    for mod_name, entries in mods_data.items():
        for entry in entries:
            if entry.info_content and entry is not current:
                item = QListWidgetItem(icon(STATUS_ICON[entry.status], STATUS_COLOR[entry.status]),
                                       f"{entry.config_name}    {mod_name}")
                item.setData(Qt.UserRole, entry)
                item.setToolTip(f"{mod_name} / {entry.config_name}")
                listbox.addItem(item)
    if not listbox.count():
        layout.addWidget(label(t("No configurations with data to copy from."), "muted"))

    def filter_items(text):
        words = text.casefold().split()
        for index in range(listbox.count()):
            item = listbox.item(index)
            item.setHidden(not all(word in item.text().casefold() for word in words))
    search.textChanged.connect(filter_items)
    row = QHBoxLayout()
    row.addStretch()
    row.addWidget(make_button(t("Cancel"), "x", dialog.reject))
    copy_button = make_button(t("Copy"), "copy", dialog.accept, "primary")
    copy_button.setEnabled(False)
    listbox.currentItemChanged.connect(lambda current_item, _: copy_button.setEnabled(current_item is not None))
    listbox.itemDoubleClicked.connect(lambda _item: dialog.accept())
    row.addWidget(copy_button)
    layout.addLayout(row)
    if dialog.exec() != QDialog.Accepted or listbox.currentItem() is None:
        return None
    return listbox.currentItem().data(Qt.UserRole)


def describe_change(entry, data):
    """Return (action, changed field names) for writing data over entry's info file."""
    if entry.status == "missing" or not isinstance(entry.info_content, dict):
        return "Create", sorted(data)
    old = entry.info_content
    changed = sorted(key for key in set(old) | set(data) if old.get(key) != data.get(key))
    return "Update", changed


class BulkPreviewDialog(QDialog):
    """Shows what a bulk write will do and lets the user narrow it before confirming."""

    def __init__(self, parent, title, pairs, visible_ids=None, backup=False, allow_scope=True):
        from PySide6.QtWidgets import QHeaderView, QRadioButton, QTableWidget, QTableWidgetItem
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 560)
        self._pairs = list(pairs)
        self._visible_ids = visible_ids
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(label(title, "sectionTitle"))
        self.summary = label("", "muted", wrap=True)
        layout.addWidget(self.summary)

        visible_count = sum(id(entry) in visible_ids for entry, _ in self._pairs) if visible_ids is not None else 0
        self.only_visible = None
        if allow_scope and visible_ids is not None and 0 < visible_count < len(self._pairs):
            scope = QHBoxLayout()
            scope.setSpacing(16)
            everything = QRadioButton(t("All loaded configurations ({count})").format(count=len(self._pairs)))
            everything.setChecked(True)
            self.only_visible = QRadioButton(t("Only those shown by search and filters ({count})").format(count=visible_count))
            scope.addWidget(everything)
            scope.addWidget(self.only_visible)
            scope.addStretch()
            layout.addLayout(scope)
            self.only_visible.toggled.connect(self._render)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([t("Configuration"), t("Mod"), t("Action"), t("Fields")])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 190)
        self._item = QTableWidgetItem
        layout.addWidget(self.table, 1)

        self.backup = QCheckBox(t("Back up before writing"))
        self.backup.setChecked(backup)
        self.backup.setToolTip(t("Keeps a dated .bak copy next to each changed file. "
                               "A ZIP backup needs space for the whole archive."))
        layout.addWidget(self.backup)
        self.backup_note = label(t("Backups are off. Changes cannot be undone without them."), "notice", wrap=True)
        layout.addWidget(self.backup_note)
        self.backup.toggled.connect(lambda checked: self.backup_note.setVisible(not checked))
        self.backup_note.setVisible(not backup)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(make_button(t("Cancel"), "x", self.reject))
        self.confirm = make_button(t("Write"), "save", self.accept, "primary")
        row.addWidget(self.confirm)
        layout.addLayout(row)
        self._render()

    def selected_pairs(self):
        if self.only_visible is not None and self.only_visible.isChecked():
            return [pair for pair in self._pairs if id(pair[0]) in self._visible_ids]
        return list(self._pairs)

    def _render(self, *_args):
        pairs = self.selected_pairs()
        shown = pairs[:500]
        self.table.setRowCount(len(shown))
        counts = {"Create": 0, "Update": 0}
        mods = set()
        for entry, data in pairs:
            counts[describe_change(entry, data)[0]] += 1
            mods.add(entry.source_path)
        for row, (entry, data) in enumerate(shown):
            action, fields = describe_change(entry, data)
            name = self._item(entry.config_name)
            name.setIcon(icon(STATUS_ICON[entry.status], STATUS_COLOR[entry.status]))
            name.setToolTip(entry.info_path or entry.pc_path)
            mod = self._item(Path(entry.source_path).name if entry.source_path else "")
            mod.setForeground(QColor(COLORS["muted"]))
            mod.setToolTip(entry.source_path)
            act = self._item(t(action))
            act.setIcon(icon("file-plus" if action == "Create" else "wrench",
                             COLORS["accent"] if action == "Create" else COLORS["warn"]))
            text = t("New file") if action == "Create" else (", ".join(fields) or t("No changes"))
            changes = self._item(text)
            changes.setToolTip(", ".join(fields))
            for column, item in enumerate((name, mod, act, changes)):
                self.table.setItem(row, column, item)
        if counts["Create"] and counts["Update"]:
            summary = t("{new} new and {updated} updated info file(s) in {mods} mod(s).").format(
                new=counts["Create"], updated=counts["Update"], mods=len(mods))
        elif counts["Create"]:
            summary = t("{count} new info file(s) in {mods} mod(s).").format(count=counts["Create"], mods=len(mods))
        else:
            summary = t("{count} info file(s) to update in {mods} mod(s).").format(
                count=counts["Update"], mods=len(mods))
        if len(shown) < len(pairs):
            summary += " " + t("Showing the first {count}.").format(count=len(shown))
        self.summary.setText(summary + " " + t("Fields that already exist are kept unless listed."))
        self.confirm.setText((t("Write 1 file") if len(pairs) == 1 else t("Write {count} files"))
                             .format(count=len(pairs)))
        self.confirm.setEnabled(bool(pairs))


def confirm_bulk(parent, title, pairs, visible_ids=None, backup=False, allow_scope=True):
    """Return (pairs to write, backup flag), or None when cancelled."""
    dialog = BulkPreviewDialog(parent, title, pairs, visible_ids, backup, allow_scope)
    if dialog.exec() != QDialog.Accepted:
        return None
    return dialog.selected_pairs(), dialog.backup.isChecked()
