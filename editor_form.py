"""The grouped Details form of the configuration editor."""
from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QTextEdit,
    QVBoxLayout, QWidget,
)

import vocabulary
from i18n import t
from widgets import label

INSURANCE_LABELS = {"": "Not set", "dailyDriver": "Daily driver",
                    "commercial": "Commercial", "prestige": "Prestige"}
REGION_LABELS = {"northAmerica": "North America", "europe": "Europe",
                 "asiaPacific": "Asia Pacific", "china": "China"}

FULL = 0  # span marker: the field takes a whole row

# (group, [(caption, attribute, choices or field kind, span)])
FIELDS = [
    ("Identity", [
        ("Display name", "w_name", "text", FULL),
        ("Config type", "w_config_type", vocabulary.CONFIG_TYPES, 1),
        ("Body style", "w_body", vocabulary.BODY_STYLES, 1),
        ("Insurance", "w_insurance", "insurance", 1),
    ]),
    ("Powertrain", [
        ("Drivetrain", "w_drivetrain", vocabulary.DRIVETRAINS, 1),
        ("Transmission", "w_transmission", vocabulary.TRANSMISSIONS, 1),
        ("Fuel type", "w_fuel", vocabulary.FUEL_TYPES, 1),
        ("Induction", "w_induction", vocabulary.INDUCTION_TYPES, 1),
    ]),
    ("Performance", [
        ("Power, hp", "w_power", "decimal", 1),
        ("Torque, Nm", "w_torque", "decimal", 1),
        ("Weight, kg", "w_weight", "decimal", 1),
    ]),
    ("Market", [
        ("Price min", "w_price_min", "integer", 1),
        ("Price max", "w_price_max", "integer", 1),
        ("Population", "w_population", "population", 1),
        ("Years from", "w_year_min", "year", 1),
        ("Years to", "w_year_max", "year", 1),
        ("Paint", "w_paint", "paint", 1),
        ("Region", "w_region", "region", FULL),
    ]),
]


class RegionPicker(QWidget):
    """Toggle chips for the stock Region values; none selected leaves Region out."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._buttons = {}
        for value, text in REGION_LABELS.items():
            button = QPushButton(t(text))
            button.setObjectName("chip")
            button.setCheckable(True)
            button.toggled.connect(lambda _checked: self.changed.emit())
            layout.addWidget(button)
            self._buttons[value] = button
        layout.addStretch()
        self._extra = []

    def value(self):
        return [key for key, button in self._buttons.items() if button.isChecked()] + self._extra

    def set_value(self, value):
        values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        self.blockSignals(True)
        for key, button in self._buttons.items():
            button.setChecked(key in values)
        # Unknown regions are kept so a save never drops them.
        self._extra = [item for item in values if isinstance(item, str) and item not in self._buttons]
        self.blockSignals(False)


class ResponsiveGrid(QWidget):
    """Label/field pairs that reflow into one, two or three pairs per row."""

    def __init__(self):
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(8)
        self._items = []
        self._pairs = 0

    def add(self, caption, widget, span):
        caption_label = label(caption, "fieldLabel")
        caption_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        caption_label.setMinimumWidth(78)
        self._items.append((caption_label, widget, span))

    def _layout(self, pairs):
        if pairs == self._pairs:
            return
        self._pairs = pairs
        for caption, widget, _span in self._items:
            self._grid.removeWidget(caption)
            self._grid.removeWidget(widget)
        for column in range(6):
            self._grid.setColumnStretch(column, 0)
        for pair in range(pairs):
            self._grid.setColumnStretch(pair * 2 + 1, 1)
        row = column = 0
        for caption, widget, span in self._items:
            if span == FULL or column >= pairs:
                if column:
                    row += 1
                column = 0
            self._grid.addWidget(caption, row, column * 2)
            if span == FULL:
                self._grid.addWidget(widget, row, 1, 1, pairs * 2 - 1)
                row += 1
                continue
            self._grid.addWidget(widget, row, column * 2 + 1)
            column += 1

    def resizeEvent(self, event):
        width = event.size().width()
        self._layout(3 if width >= 760 else 2 if width >= 460 else 1)
        super().resizeEvent(event)

    def reflow(self, pairs=2):
        self._layout(pairs)


def _field(kind, on_change):
    if isinstance(kind, list):
        widget = QComboBox()
        # Editable so mod-specific values (e.g. a custom Config Type) stay possible.
        widget.setEditable(True)
        widget.setInsertPolicy(QComboBox.NoInsert)
        # Long values must not widen the column and force a horizontal scroll.
        widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(6)
        widget.addItems(kind)
        widget.currentTextChanged.connect(on_change)
        return widget
    if kind == "insurance":
        widget = QComboBox()
        widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(6)
        for value in vocabulary.INSURANCE_CLASSES:
            widget.addItem(t(INSURANCE_LABELS[value]), value)
        widget.setToolTip(t("Career insurance tier (InsuranceClass). Not set leaves the field out."))
        widget.currentIndexChanged.connect(on_change)
        return widget
    if kind == "region":
        widget = RegionPicker()
        widget.setToolTip(t("Markets where the vehicle is sold (Region). None selected leaves the field out."))
        widget.changed.connect(on_change)
        return widget
    widget = QLineEdit()
    widget.setMinimumWidth(70)
    if kind == "decimal":
        validator = QDoubleValidator(0, 2147483647, 6, widget)
        validator.setLocale(QLocale.c())
        validator.setNotation(QDoubleValidator.StandardNotation)
        widget.setValidator(validator)
        widget.setPlaceholderText(t("Not set"))
    elif kind == "integer":
        widget.setValidator(QIntValidator(0, 2147483647, widget))
    elif kind == "population":
        widget.setValidator(QIntValidator(0, 2147483647, widget))
        widget.setPlaceholderText("5000")
        widget.setToolTip(t("Traffic and dealership spawn weight (Population)."))
    elif kind == "year":
        widget.setValidator(QIntValidator(0, 9999, widget))
        widget.setPlaceholderText(t("Not set"))
    elif kind == "paint":
        widget.setPlaceholderText(t("Not set"))
        widget.setToolTip(t("Default paint name (defaultPaintName1)."))
    widget.textChanged.connect(on_change)
    return widget


def build_details_form(owner, on_change) -> QScrollArea:
    """Create the form and expose each input as an attribute of owner."""
    page = QWidget()
    page.setObjectName("formPage")
    root = QVBoxLayout(page)
    root.setContentsMargins(2, 6, 12, 10)
    root.setSpacing(6)
    for title, fields in FIELDS:
        root.addWidget(label(t(title).upper(), "groupTitle"))
        grid = ResponsiveGrid()
        for caption, attribute, kind, span in fields:
            widget = _field(kind, on_change)
            grid.add(t(caption), widget, span)
            setattr(owner, attribute, widget)
        grid.reflow()
        root.addWidget(grid)
        root.addSpacing(4)
    root.addWidget(label(t("Description").upper(), "groupTitle"))
    owner.w_description = QTextEdit()
    owner.w_description.setAcceptRichText(False)
    owner.w_description.setPlaceholderText(t("Shown in the vehicle selector"))
    owner.w_description.setMinimumHeight(64)
    owner.w_description.setMaximumHeight(96)
    owner.w_description.textChanged.connect(on_change)
    root.addWidget(owner.w_description)
    root.addStretch(1)
    owner.w_price_min.setText("10000")
    owner.w_price_max.setText("50000")
    owner.w_induction.setCurrentText(vocabulary.DEFAULT_INDUCTION)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(page)
    return scroll


def set_combo(widget: QComboBox, value):
    value = str(value) if value is not None else ""
    index = widget.findText(value)
    if index < 0:
        widget.addItem(value)
        index = widget.count() - 1
    widget.setCurrentIndex(index)


def set_insurance(widget: QComboBox, value):
    index = widget.findData(value if isinstance(value, str) else "")
    if index < 0:
        widget.addItem(str(value), value)
        index = widget.count() - 1
    widget.setCurrentIndex(index)
