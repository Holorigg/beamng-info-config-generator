"""RLS contracts diagnostics and managed patch controls."""

import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from theme import COLORS
from i18n import t
from ui_icons import icon
from widgets import label, make_button, pill, set_tone
from workers import TaskDialog

from rls_contracts import KNOWN_POOL_HASHES, collect_models, diagnose, discover_rls
from rls_patch import install_patch, read_patch, set_patch_enabled


def _item(text, align=None):
    item = QTableWidgetItem(str(text or ""))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if align is not None:
        item.setTextAlignment(align)
    return item


def _status_icon(text):
    value = text.casefold()
    if value.startswith("in pool"):
        return "circle-check", COLORS["ok"]
    if value.startswith("not in pool"):
        return "circle-dashed", COLORS["muted"]
    if value.startswith(("blacklisted", "excluded")):
        return "ban", COLORS["danger"]
    if value.startswith(("needs", "config type")):
        return "triangle-alert", COLORS["warn"]
    return None


# Diagnosis and note phrases produced by rls_contracts, translated only for display.
_PHRASES = (
    "RLS rules unverified estimate", "RLS version warning", "Config type unverified", "Not in pool",
    "In pool", "Blacklisted", "Excluded model", "Excluded",
    "Model info missing; common for vanilla-based configuration packs",
    "Found in multiple archives; effective override precedence is uncertain",
    "Vehicle pool hash is not a verified RLS rule source",
    "Version is unknown or differs from the verified RLS versions",
)


def _display(text):
    text = str(text or "")
    if text.startswith("Needs ") and text.split(" (")[0].endswith(" config"):
        base, _, rest = text.partition(" (")
        text = t("Needs {types} config").format(types=base[6:-7]) + (" (" + rest if rest else "")
    for phrase in _PHRASES:
        if phrase in text:
            text = text.replace(phrase, t(phrase))
    return text


def _status_item(text):
    found = _status_icon(str(text or ""))
    item = _item(_display(text))
    if found:
        item.setIcon(icon(*found))
    return item


class ContractsDialog(QDialog):
    def __init__(self, mods_path: str, entries: list, selected_keys: set[str] | None = None, parent=None):
        super().__init__(parent)
        self.mods_path = mods_path
        self.entries = list(entries)
        self.selected_keys = set(selected_keys or ())
        self.installation = None
        self.installations = []
        self.models = []
        self.diagnoses = {}
        self.patch = None
        self._selection_initialized = False
        self._restart_required = False
        self._busy_dialog = None

        self.setWindowTitle(t("RLS Contracts"))
        self.setMinimumSize(960, 600)
        self.resize(1120, 700)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label(t("RLS Contracts"), "sectionTitle"))
        titles.addWidget(label(t("Which vehicle models can appear in random Drift, Drag and Race contracts. "
                               "Supports RLS 2.7 and 2.8."), "muted", wrap=True))
        header.addLayout(titles, 1)
        header.addWidget(label(t("Installed RLS"), "fieldLabel"))
        self.installation_selector = QComboBox()
        self.installation_selector.setMinimumWidth(290)
        self.installation_selector.setEnabled(False)
        self.installation_selector.currentIndexChanged.connect(self._select_installation)
        header.addWidget(self.installation_selector)
        self.refresh_button = make_button(t("Refresh"), "refresh-cw", self.refresh)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.rules_pill = pill("", "neutral")
        self.rules_pill.hide()
        status_row.addWidget(self.rules_pill)
        self.installation_status = QLabel(t("Detecting installed RLS..."))
        self.installation_status.setObjectName("muted")
        self.installation_status.setWordWrap(True)
        status_row.addWidget(self.installation_status, 1)
        root.addLayout(status_row)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Search models and notes"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", COLORS["muted"]), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._filter_rows)
        controls.addWidget(self.search, 1)
        self.select_visible = QPushButton(t("Select all visible"))
        self.select_visible.setIcon(icon("check"))
        self.select_visible.clicked.connect(self._toggle_visible)
        controls.addWidget(self.select_visible)
        root.addLayout(controls)
        self.models_status = QLabel(t("Scanning model configs..."))
        self.models_status.setObjectName("muted")
        root.addWidget(self.models_status)
        self.preserved_status = QLabel("")
        self.preserved_status.setObjectName("muted")
        self.preserved_status.setWordWrap(True)
        root.addWidget(self.preserved_status)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ("", t("Model"), "Drift", "Drag", "Race", t("Config types"), t("Notes")))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 34)
        self.table.setColumnWidth(1, 230)
        for column in (2, 3, 4):
            self.table.setColumnWidth(column, 150)
        self.table.setColumnWidth(5, 170)
        self.table.setWordWrap(True)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.patch_status = QLabel(t("Managed patch: checking..."))
        self.patch_status.setObjectName("muted")
        footer.addWidget(self.patch_status, 1)
        self.patch_toggle = QPushButton(t("Disable patch"))
        self.patch_toggle.setIcon(icon("package"))
        self.patch_toggle.clicked.connect(self._toggle_patch)
        footer.addWidget(self.patch_toggle)
        self.apply_button = QPushButton(t("Apply patch"))
        self.apply_button.setObjectName("primary")
        self.apply_button.setIcon(icon("save"))
        self.apply_button.clicked.connect(self._apply_patch)
        footer.addWidget(self.apply_button)
        close = QPushButton(t("Close"))
        close.setIcon(icon("x"))
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

        self.refresh()

    def _run_task(self, title, task, on_success):
        worker_dialog = TaskDialog(title, task, self)
        self._busy_dialog = worker_dialog
        worker = worker_dialog.execute()
        self._busy_dialog = None
        if worker.error:
            QMessageBox.critical(self, title, worker.error)
            return
        if worker.cancelled:
            return
        try:
            on_success(worker.value)
        except Exception:
            QMessageBox.critical(self, title, traceback.format_exc())

    def refresh(self):
        if hasattr(self, "_row_keys"):
            self._sync_all_selected()
        self.refresh_button.setEnabled(False)
        self.installation_status.setText(t("Scanning RLS and vehicle configs..."))

        def task(cancel, progress):
            progress(0, 3, "Detecting installed RLS")
            installations = discover_rls(self.mods_path) or []
            progress(1, 3, "Collecting vehicle models")
            models = collect_models(self.entries, cancel=cancel, progress=progress)
            models = list(models or ())
            progress(2, 3, "Reading managed patch")
            patch = read_patch(self.mods_path)
            diagnoses = {}
            for index, installation in enumerate(installations):
                progress(index + 1, max(1, len(installations)), t("Diagnosing RLS {version}").format(version=installation.version))
                diagnoses[installation.path] = diagnose(
                    installation, models,
                    patched_models=(patch or {}).get("models", ()) if patch and patch.get("enabled") else (),
                )
            return installations, models, diagnoses, patch

        def done(result):
            self.installations, self.models, self.diagnoses, self.patch = result
            if not self._selection_initialized:
                self.selected_keys.update((self.patch or {}).get("models", ()))
                self._selection_initialized = True
            self.installation_selector.blockSignals(True)
            self.installation_selector.clear()
            for installation in self.installations:
                rule_status = t("verified rules") if installation.supported else t("unverified rules")
                version = installation.version or "unknown"
                index = self.installation_selector.count()
                self.installation_selector.addItem(f"RLS {version} ({rule_status})", installation.path)
                tooltip = _display(installation.issue) or t("Rules verified against RLS {version}.").format(version=version)
                self.installation_selector.setItemData(index, tooltip, Qt.ToolTipRole)
            self.installation_selector.setEnabled(bool(self.installations))
            self.installation_selector.blockSignals(False)
            self.installation = self.installations[0] if self.installations else None
            if self.installations:
                self.installation_selector.setCurrentIndex(0)
            self._render()
            self.refresh_button.setEnabled(True)

        self._run_task("RLS diagnostics", task, done)
        self.refresh_button.setEnabled(True)

    def _render(self):
        if self.installation:
            rule_status = t("Verified rules") if self.installation.supported else t("Unverified rules")
            self.rules_pill.setText(rule_status)
            set_tone(self.rules_pill, "ok" if self.installation.supported and not self.installation.issue else "bad")
            self.rules_pill.show()
            layout_name = getattr(getattr(self.installation, "layout", None), "name", "")
            details = [f"RLS {self.installation.version or 'unknown'}"]
            if layout_name:
                details.append(t("{layout} file layout").format(layout=layout_name))
            if self.installation.issue:
                details.append(_display(self.installation.issue))
            self.installation_status.setText("  ·  ".join(details))
            self.installation_status.setToolTip(
                f"Path: {self.installation.path}\nVehicle pool SHA-256: {self.installation.pool_hash}\n"
                f"{self.installation.issue or ''}"
            )
        else:
            self.rules_pill.hide()
            self.installation_status.setText(t("No installed RLS archive was detected."))
            self.installation_status.setToolTip("")

        old_keys = set((self.patch or {}).get("models", ()))
        preserved = sorted(old_keys - {model.key for model in self.models})
        self.preserved_status.setText(
            t("Preserving {count} patched model(s) not present in this scan.").format(count=len(preserved))
            if preserved else ""
        )
        self.preserved_status.setToolTip("\n".join(preserved))
        self.preserved_status.setVisible(bool(preserved))
        self.models_status.setText(
            t("{count} models found").format(count=len(self.models)) if self.models else
            t("No model entries found. Scan the mods folder first.")
        )
        self.table.setRowCount(len(self.models))
        self._row_keys = []
        for row, model in enumerate(self.models):
            key = model.key
            self._row_keys.append(key)
            check = QCheckBox()
            check.setChecked(key in self.selected_keys and not model.excluded)
            check.setEnabled(not model.excluded)
            check.stateChanged.connect(lambda _state, model_key=key: self._sync_selected(model_key))
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.addWidget(check)
            self.table.setCellWidget(row, 0, cell)
            diagnosis = next((item for item in self.diagnoses.get(self.installation.path, ())
                              if item.model.key == key), None) if self.installation else None
            model_item = _item(key)
            font = model_item.font()
            font.setWeight(font.Weight.DemiBold)
            model_item.setFont(font)
            model_item.setToolTip(t("Sources:\n") + ("\n".join(model.sources) or "No source path recorded"))
            self.table.setItem(row, 1, model_item)
            self.table.setItem(row, 2, _status_item(self._diag_value(diagnosis, "drift")))
            self.table.setItem(row, 3, _status_item(self._diag_value(diagnosis, "drag")))
            race = self._diag_value(diagnosis, "race")
            self.table.setItem(row, 4, _status_item(race))
            self.table.setItem(row, 5, _item(", ".join(model.config_types)))
            note = _display(model.issue or ("Excluded" if model.excluded else ""))
            if diagnosis and getattr(diagnosis, "issue", ""):
                note = "; ".join(filter(None, (note, diagnosis.issue)))
            self.table.setItem(row, 6, _item(note))
            for column in range(1, self.table.columnCount()):
                item = self.table.item(row, column)
                if column != 1:
                    item.setToolTip(item.text())
            self.table.setRowHeight(row, 38)
        self.table.resizeRowsToContents()
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, max(38, self.table.rowHeight(row)))
        self._filter_rows(self.search.text())
        self._update_patch_controls()
        self.apply_button.setEnabled(bool(
            self.installation and isinstance(self.installation.config, dict) and self.models
        ))
        self.apply_button.setToolTip(self.installation.issue if self.installation else "")

    @staticmethod
    def _diag_value(diagnosis, name):
        value = getattr(diagnosis, name, "") if diagnosis else ""
        return str(value or "—")

    def _select_installation(self, index):
        if index < 0:
            return
        path = self.installation_selector.itemData(index)
        self.installation = next((item for item in self.installations if item.path == path), None)
        self._render()

    def _sync_selected(self, key):
        checkbox = self._checkbox_for_key(key)
        if checkbox and checkbox.isChecked():
            self.selected_keys.add(key)
        else:
            self.selected_keys.discard(key)

    def _sync_all_selected(self):
        for key in self._row_keys:
            self._sync_selected(key)

    def _checkbox_for_key(self, key):
        try:
            row = self._row_keys.index(key)
        except (ValueError, AttributeError):
            return None
        widget = self.table.cellWidget(row, 0)
        return widget.findChild(QCheckBox) if widget else None

    def _filter_rows(self, query):
        query = query.casefold().strip()
        for row in range(self.table.rowCount()):
            visible = not query or any(
                query in (self.table.item(row, col).text().casefold() if self.table.item(row, col) else "")
                for col in range(1, self.table.columnCount())
            )
            self.table.setRowHidden(row, not visible)

    def _toggle_visible(self):
        visible = [row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]
        checks = [self.table.cellWidget(row, 0).findChild(QCheckBox) for row in visible]
        target = not all(check.isChecked() for check in checks if check and check.isEnabled())
        for check in checks:
            if check and check.isEnabled():
                check.setChecked(target)

    def _update_patch_controls(self):
        exists = self.patch is not None
        enabled = bool((self.patch or {}).get("enabled", False))
        status = t("enabled") if enabled else t("disabled") if exists else t("not installed")
        if self._restart_required:
            status += "; " + t("applied, restart BeamNG")
        self.patch_status.setText(t("Managed patch: ") + status)
        self.patch_toggle.setText(t("Disable patch") if enabled else t("Enable patch"))
        self.patch_toggle.setEnabled(exists)

    def _apply_patch(self):
        if not self.models:
            QMessageBox.warning(self, t("Apply patch"), t("No model entries found. Scan the mods folder first."))
            return
        if not self.installation or not isinstance(self.installation.config, dict):
            QMessageBox.warning(self, t("Apply patch"), t("A valid RLS installation and patch backend are required."))
            return
        self._sync_all_selected()
        scanned = set(self._row_keys)
        previous = set((self.patch or {}).get("models", ()))
        preserved = previous - scanned
        keys = sorted((self.selected_keys & scanned) | preserved)
        if not keys:
            QMessageBox.warning(self, t("Apply patch"), t("Select at least one vehicle model."))
            return
        shown = keys[:20]
        names = "\n".join(f"  {key}" for key in shown)
        if len(keys) > len(shown):
            names += "\n  " + t("... and {count} more").format(count=len(keys) - len(shown))
        unverified = (not self.installation.supported
                      or self.installation.version not in KNOWN_POOL_HASHES.values())
        warning = "\n\n" + t("Warning: this version or contract hash is unverified.") if unverified else ""
        if preserved:
            warning += "\n\n" + t("{count} existing model(s) absent from this scan will be preserved.").format(
                count=len(preserved))
        answer = QMessageBox.question(
            self, t("Apply managed patch"),
            t("Replace the managed selection with {count} model(s)?").format(count=len(keys))
            + f"\n\n{names}{warning}\n\n" + t("Restart BeamNG after changes."),
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        def task(_cancel, progress):
            progress(0, 1, "Applying managed patch")
            return install_patch(self.mods_path, self.installation, keys)

        self._run_task(t("Apply managed patch"), task, self._patch_applied)

    def _toggle_patch(self):
        if self.patch is None:
            return
        enabled = not bool(self.patch.get("enabled", False))
        title = t("Enable managed patch") if enabled else t("Disable managed patch")
        answer = QMessageBox.question(
            self, title,
            (t("Enable the managed RLS patch?") if enabled else t("Disable the managed RLS patch?"))
            + "\n\n" + t("Restart BeamNG after changes."),
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        def task(_cancel, progress):
            progress(0, 1, title)
            return set_patch_enabled(self.mods_path, enabled)

        self._run_task(title, task, self._patch_applied)

    def _patch_applied(self, _result):
        self._restart_required = True
        self.refresh()
        self._update_patch_controls()
