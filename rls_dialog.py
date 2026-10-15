"""RLS contracts diagnostics and managed patch controls."""

import traceback

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ui_icons import icon
from workers import TaskDialog

from rls_contracts import collect_models, diagnose, discover_rls
from rls_patch import install_patch, read_patch, set_patch_enabled


def _item(text, align=None):
    item = QTableWidgetItem(str(text or ""))
    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    if align is not None:
        item.setTextAlignment(align)
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

        self.setWindowTitle("RLS Contracts")
        self.setMinimumSize(960, 600)
        self.resize(1120, 700)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        heading = QLabel("RLS Contracts")
        heading.setObjectName("sectionTitle")
        header.addWidget(heading)
        header.addStretch(1)
        header.addWidget(QLabel("Installed RLS"))
        self.installation_selector = QComboBox()
        self.installation_selector.setMinimumWidth(290)
        self.installation_selector.setEnabled(False)
        self.installation_selector.currentIndexChanged.connect(self._select_installation)
        header.addWidget(self.installation_selector)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setIcon(icon("refresh-cw"))
        self.refresh_button.setIconSize(QSize(18, 18))
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        root.addLayout(header)

        self.installation_status = QLabel("Detecting installed RLS...")
        self.installation_status.setObjectName("muted")
        self.installation_status.setWordWrap(True)
        root.addWidget(self.installation_status)

        controls = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search models and notes")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_rows)
        controls.addWidget(self.search, 1)
        self.select_visible = QPushButton("Select all visible")
        self.select_visible.setIcon(icon("list-tree"))
        self.select_visible.clicked.connect(self._toggle_visible)
        controls.addWidget(self.select_visible)
        root.addLayout(controls)
        self.models_status = QLabel("Scanning model configs...")
        self.models_status.setObjectName("muted")
        root.addWidget(self.models_status)
        self.preserved_status = QLabel("")
        self.preserved_status.setObjectName("muted")
        self.preserved_status.setWordWrap(True)
        root.addWidget(self.preserved_status)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("", "Model", "Drift", "Drag", "Race", "Config types", "Notes"))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
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
        self.patch_status = QLabel("Managed patch: checking...")
        self.patch_status.setObjectName("muted")
        footer.addWidget(self.patch_status, 1)
        self.patch_toggle = QPushButton("Disable patch")
        self.patch_toggle.setIcon(icon("wrench"))
        self.patch_toggle.clicked.connect(self._toggle_patch)
        footer.addWidget(self.patch_toggle)
        self.apply_button = QPushButton("Apply patch")
        self.apply_button.setObjectName("primary")
        self.apply_button.setIcon(icon("save"))
        self.apply_button.clicked.connect(self._apply_patch)
        footer.addWidget(self.apply_button)
        close = QPushButton("Close")
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
        self.installation_status.setText("Scanning RLS and vehicle configs...")

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
                progress(index + 1, max(1, len(installations)), f"Diagnosing RLS {installation.version}")
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
                rule_status = "verified rules" if installation.supported else "unverified rules"
                version = installation.version or "unknown"
                index = self.installation_selector.count()
                self.installation_selector.addItem(f"RLS {version} ({rule_status})", installation.path)
                tooltip = installation.issue or f"Rules verified against RLS {version}."
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
            rule_status = "Verified rules" if self.installation.supported else "Unverified rules"
            self.installation_status.setText(f"{rule_status} | RLS {self.installation.version or 'unknown'}")
            self.installation_status.setToolTip(
                f"Path: {self.installation.path}\nVehicle pool SHA-256: {self.installation.pool_hash}\n"
                f"{self.installation.issue or ''}"
            )
        else:
            self.installation_status.setText("No installed RLS archive was detected.")
            self.installation_status.setToolTip("")

        old_keys = set((self.patch or {}).get("models", ()))
        preserved = sorted(old_keys - {model.key for model in self.models})
        self.preserved_status.setText(
            f"Preserving {len(preserved)} patched model(s) not present in this scan."
            if preserved else ""
        )
        self.preserved_status.setToolTip("\n".join(preserved))
        self.preserved_status.setVisible(bool(preserved))
        self.models_status.setText(
            f"{len(self.models)} models found" if self.models else
            "No model entries found. Scan the mods folder first."
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
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.addWidget(check)
            self.table.setCellWidget(row, 0, cell)
            diagnosis = next((item for item in self.diagnoses.get(self.installation.path, ())
                              if item.model.key == key), None) if self.installation else None
            model_item = _item(key)
            model_item.setToolTip("Sources:\n" + ("\n".join(model.sources) or "No source path recorded"))
            self.table.setItem(row, 1, model_item)
            self.table.setItem(row, 2, _item(self._diag_value(diagnosis, "drift")))
            self.table.setItem(row, 3, _item(self._diag_value(diagnosis, "drag")))
            race = self._diag_value(diagnosis, "race")
            self.table.setItem(row, 4, _item(race))
            self.table.setItem(row, 5, _item(", ".join(model.config_types)))
            note = model.issue or ("Excluded" if model.excluded else "")
            if diagnosis and getattr(diagnosis, "issue", ""):
                note = "; ".join(filter(None, (note, diagnosis.issue)))
            self.table.setItem(row, 6, _item(note))
            for column in range(1, self.table.columnCount()):
                item = self.table.item(row, column)
                if column != 1:
                    item.setToolTip(item.text())
            self.table.setRowHeight(row, 44)
        self.table.resizeRowsToContents()
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, max(44, self.table.rowHeight(row)))
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
        status = "enabled" if enabled else "disabled" if exists else "not installed"
        if self._restart_required:
            status += "; Applied; restart BeamNG"
        self.patch_status.setText("Managed patch: " + status)
        self.patch_toggle.setText("Disable patch" if enabled else "Enable patch")
        self.patch_toggle.setEnabled(exists)

    def _apply_patch(self):
        if not self.models:
            QMessageBox.warning(self, "Apply patch", "No model entries found. Scan the mods folder first.")
            return
        if not self.installation or not isinstance(self.installation.config, dict):
            QMessageBox.warning(self, "Apply patch", "A valid RLS installation and patch backend are required.")
            return
        self._sync_all_selected()
        scanned = set(self._row_keys)
        previous = set((self.patch or {}).get("models", ()))
        preserved = previous - scanned
        keys = sorted((self.selected_keys & scanned) | preserved)
        if not keys:
            QMessageBox.warning(self, "Apply patch", "Select at least one vehicle model.")
            return
        shown = keys[:20]
        names = "\n".join(f"  {key}" for key in shown)
        if len(keys) > len(shown):
            names += f"\n  ... and {len(keys) - len(shown)} more"
        unverified = not self.installation.supported or self.installation.version != "2.7.2"
        warning = "\n\nWarning: this version or contract hash is unverified." if unverified else ""
        if preserved:
            warning += f"\n\n{len(preserved)} existing model(s) absent from this scan will be preserved."
        answer = QMessageBox.question(
            self, "Apply managed patch",
            f"Replace the managed selection with {len(keys)} model(s)?\n\n{names}{warning}\n\n"
            "Restart BeamNG after changes.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        def task(_cancel, progress):
            progress(0, 1, "Applying managed patch")
            return install_patch(self.mods_path, self.installation, keys)

        self._run_task("Apply managed patch", task, self._patch_applied)

    def _toggle_patch(self):
        if self.patch is None:
            return
        enabled = not bool(self.patch.get("enabled", False))
        verb = "Enable" if enabled else "Disable"
        answer = QMessageBox.question(
            self, f"{verb} managed patch",
            f"{verb} the managed RLS patch?\n\nRestart BeamNG after changes.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return

        def task(_cancel, progress):
            progress(0, 1, f"{verb}ing managed patch")
            return set_patch_enabled(self.mods_path, enabled)

        self._run_task(f"{verb} managed patch", task, self._patch_applied)

    def _patch_applied(self, _result):
        self._restart_required = True
        self.refresh()
        self._update_patch_controls()
