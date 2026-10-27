"""Reusable widgets shared by the main window and its dialogs."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from theme import COLORS, STATUS_LABEL
from i18n import t
from ui_icons import icon


def make_button(text, icon_name, slot=None, kind=None, tooltip=""):
    button = QPushButton(text)
    button.setIcon(icon(icon_name))
    button.setIconSize(QSize(16, 16))
    if not text:
        button.setFixedWidth(36)
        button.setAccessibleName(tooltip)
    if tooltip:
        button.setToolTip(tooltip)
    if kind:
        button.setObjectName(kind)
    if slot is not None:
        button.clicked.connect(slot)
    return button


def label(text="", name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def pill(text="", tone="neutral"):
    widget = label(text, "pill")
    set_tone(widget, tone)
    return widget


def set_tone(widget, tone):
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def status_pill(widget, status):
    widget.setText(t(STATUS_LABEL.get(status, "")) if status in STATUS_LABEL else "")
    set_tone(widget, status if status in STATUS_LABEL else "neutral")
    widget.setVisible(status in STATUS_LABEL)


def icon_label(icon_name, color=None, size=16):
    widget = QLabel()
    widget.setPixmap(icon(icon_name, color or COLORS["muted"]).pixmap(size, size))
    widget.setFixedSize(size, size)
    return widget


def divider():
    line = QFrame()
    line.setObjectName("divider")
    return line


class NumberItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except (TypeError, ValueError, OverflowError):
            return self.text() < other.text()


class StatusItem(QTableWidgetItem):
    def __lt__(self, other):
        return self.data(Qt.UserRole + 1) < other.data(Qt.UserRole + 1)


def _text(value, fallback="—"):
    if value is None or value == "" or isinstance(value, (dict, list, tuple, set)):
        return fallback
    return str(value)


def format_price(value):
    try:
        if isinstance(value, bool):
            raise TypeError
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError, OverflowError):
        return "—"


class _Stat(QWidget):
    def __init__(self, icon_name, caption):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(icon_label(icon_name, COLORS["accent"], 16), 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(label(caption, "fieldLabel"))
        self.value = QLabel("—")
        self.value.setStyleSheet("font-weight: 600;")
        text.addWidget(self.value)
        layout.addLayout(text, 1)


class CardPreview(QFrame):
    """Approximates the vehicle selector tile for a single configuration."""
    _IMG_W = 400
    _IMG_H = 225

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardPreview")
        self.setMaximumWidth(self._IMG_W + 34)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        self._lbl_img = QLabel()
        self._lbl_img.setFixedSize(self._IMG_W, self._IMG_H)
        self._lbl_img.setAlignment(Qt.AlignCenter)
        self._lbl_img.setStyleSheet(
            f"background: {COLORS['field']}; border: 1px solid {COLORS['border']}; border-radius: 6px;"
            f"color: {COLORS['faint']};"
        )
        outer.addWidget(self._lbl_img, 0, Qt.AlignHCenter)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self._lbl_name = QLabel("")
        self._lbl_name.setWordWrap(True)
        self._lbl_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._lbl_name.setStyleSheet("font-size: 13pt; font-weight: 600;")
        title_row.addWidget(self._lbl_name, 1)
        self._lbl_type = pill("", "neutral")
        title_row.addWidget(self._lbl_type, 0, Qt.AlignTop)
        outer.addLayout(title_row)

        self._lbl_row1 = label("", "muted", wrap=True)
        outer.addWidget(self._lbl_row1)

        price_row = QHBoxLayout()
        price_row.setSpacing(6)
        price_row.addWidget(icon_label("banknote", COLORS["accent"], 18))
        self._lbl_price = QLabel("—")
        self._lbl_price.setStyleSheet(f"font-size: 15pt; font-weight: 600; color: {COLORS['accent']};")
        price_row.addWidget(self._lbl_price)
        price_row.addStretch()
        outer.addLayout(price_row)
        outer.addWidget(divider())

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)
        self._stats = {}
        for index, (key, icon_name, caption) in enumerate((
            ("Power", "zap", "Power"), ("Torque", "gauge", "Torque"), ("Weight", "weight", "Weight"),
            ("Fuel Type", "fuel", "Fuel"), ("Induction Type", "cog", "Induction"),
            ("InsuranceClass", "shield", "Insurance"),
        )):
            stat = _Stat(icon_name, t(caption))
            self._stats[key] = stat
            grid.addWidget(stat, index // 3, index % 3)
        outer.addLayout(grid)
        # Kept for compatibility with callers that read the stats line.
        self._lbl_row2 = QLabel("")
        self._lbl_row2.hide()
        self._lbl_stats = QLabel("")
        self._lbl_stats.hide()

        self._lbl_desc = label("", "muted", wrap=True)
        self._lbl_desc.setStyleSheet("font-style: italic;")
        outer.addWidget(self._lbl_desc)
        outer.addStretch()

    def set_thumbnail(self, data: bytes):
        px = QPixmap()
        if data:
            px.loadFromData(data)
        if px.isNull():
            self._lbl_img.setPixmap(QPixmap())
            self._lbl_img.setText(t("No preview image"))
            return
        self._lbl_img.setPixmap(px.scaled(self._IMG_W - 2, self._IMG_H - 2,
                                          Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def update(self, data: dict):
        name = data.get("Configuration")
        self._lbl_name.setText(str(name) if name not in (None, "") else "—")
        config_type = _text(data.get("Config Type"), "")
        self._lbl_type.setText(config_type)
        self._lbl_type.setVisible(bool(config_type))
        parts = [_text(data.get(key), "") for key in ("Body Style", "Drivetrain", "Transmission")]
        self._lbl_row1.setText("  ·  ".join(part for part in parts if part))
        self._lbl_price.setText(format_price(data.get("Value")))

        units = {"Power": " " + t("hp"), "Torque": " " + t("Nm"), "Weight": " " + t("kg")}
        for key, stat in self._stats.items():
            value = _text(data.get(key))
            stat.value.setText(value + units.get(key, "") if value != "—" else value)
        stats = [stat.value.text() for key, stat in self._stats.items() if key in units]
        self._lbl_stats.setText("   ".join(value for value in stats if value != "—"))

        desc = data.get("Description")
        desc = desc if isinstance(desc, str) else ""
        self._lbl_desc.setText(desc[:177] + "..." if len(desc) > 180 else desc)

    def clear(self):
        self._lbl_img.clear()
        for widget in (self._lbl_name, self._lbl_type, self._lbl_row1, self._lbl_desc):
            widget.setText("")
        self._lbl_price.setText("—")
        for stat in self._stats.values():
            stat.value.setText("—")


class EmptyState(QWidget):
    """Centered illustration, message and actions for a panel with nothing to show."""

    def __init__(self, icon_name, title, text):
        super().__init__()
        self.setObjectName("emptyState")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.addStretch(2)
        badge = QLabel()
        badge.setObjectName("emptyBadge")
        badge.setFixedSize(84, 84)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(icon(icon_name, COLORS["accent"]).pixmap(40, 40))
        layout.addWidget(badge, 0, Qt.AlignHCenter)
        layout.addSpacing(6)
        self.title = label(title, "emptyTitle", wrap=True)
        self.title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title)
        self.text = label(text, "muted", wrap=True)
        self.text.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.text)
        layout.addSpacing(8)
        self.actions = QVBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions)
        self.hint = label("", "faint")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.hint)
        layout.addStretch(3)

    def set_hint(self, text):
        """Show a long path elided in the middle; the full text stays in the tooltip."""
        self._hint_full = text
        self.hint.setToolTip(text)
        self._elide_hint()

    def _elide_hint(self):
        full = getattr(self, "_hint_full", "")
        width = max(120, self.width() - 60)
        self.hint.setText(self.hint.fontMetrics().elidedText(full, Qt.ElideMiddle, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_hint()

    def add_action(self, button):
        button.setMinimumWidth(240)
        self.actions.addWidget(button, 0, Qt.AlignHCenter)
        return button


class Toast(QFrame):
    """A transient notification anchored to the bottom-right corner of its parent."""
    TONES = {"ok": ("circle-check", "ok"), "warn": ("triangle-alert", "warn"),
             "error": ("circle-x", "danger"), "info": ("info", "accent")}

    def __init__(self, parent):
        from PySide6.QtCore import QPropertyAnimation, QTimer
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        super().__init__(parent)
        self.setObjectName("toast")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 8, 10)
        layout.setSpacing(10)
        self._icon = QLabel()
        self._icon.setFixedSize(18, 18)
        layout.addWidget(self._icon, 0, Qt.AlignTop)
        self._text = label("", wrap=True)
        self._text.setMaximumWidth(360)
        layout.addWidget(self._text, 1)
        self._action = QPushButton()
        self._action.setObjectName("toastAction")
        self._action.hide()
        layout.addWidget(self._action, 0, Qt.AlignVCenter)
        close = make_button("", "x", self.dismiss, "ghost", t("Dismiss"))
        close.setFixedSize(26, 26)
        layout.addWidget(close, 0, Qt.AlignTop)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(180)
        self._fade.finished.connect(self._faded)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._callback = None
        self._action.clicked.connect(self._run_action)
        self.hide()

    def show_message(self, text, tone="ok", action=None, timeout=4500):
        icon_name, color = self.TONES.get(tone, self.TONES["info"])
        self._icon.setPixmap(icon(icon_name, COLORS[color]).pixmap(18, 18))
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)
        self._text.setText(text)
        self._callback = action[1] if action else None
        self._action.setText(action[0] if action else "")
        self._action.setVisible(bool(action))
        was_visible = self.isVisible()
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity() if was_visible else 0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(timeout if not action else max(timeout, 8000))

    def reposition(self):
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 18
        self.setFixedWidth(min(460, max(280, parent.width() // 3)))
        self.setFixedHeight(self.layout().heightForWidth(self.width()) if self.layout().hasHeightForWidth()
                            else self.sizeHint().height())
        bottom = parent.height() - margin - getattr(parent, "toast_bottom_offset", 0)
        self.move(parent.width() - self.width() - margin, bottom - self.height())

    def dismiss(self):
        if not self.isVisible():
            return
        self._timer.stop()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _faded(self):
        if self._effect.opacity() <= 0.01:
            self.hide()

    def _run_action(self):
        callback = self._callback
        self.dismiss()
        if callback:
            callback()
