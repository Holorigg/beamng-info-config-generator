"""Design tokens and the application stylesheet."""

# Surfaces step up in lightness; one accent, three status hues.
COLORS = {
    "window": "#141618",
    "surface": "#1a1d20",
    "raised": "#212529",
    "field": "#16191b",
    "hover": "#2a2f34",
    "border": "#2e3439",
    "border_strong": "#3d454b",
    "text": "#e7eaec",
    "muted": "#8e979e",
    "faint": "#646d73",
    "accent": "#3dbb8c",
    "accent_strong": "#2a9c73",
    "accent_soft": "#1f3a31",
    "ok": "#4fbf87",
    "warn": "#e2a64b",
    "danger": "#e5675a",
}

STATUS_COLOR = {"ok": COLORS["ok"], "bad": COLORS["warn"], "missing": COLORS["danger"]}
STATUS_ICON = {"ok": "circle-check", "bad": "triangle-alert", "missing": "circle-dashed"}
STATUS_LABEL = {"ok": "Valid", "bad": "Incomplete", "missing": "Missing"}


def make_dark_style():
    from ui_icons import icon_file

    c = COLORS
    chevron = icon_file("chevron-down", c["muted"], 14)
    chevron_right = icon_file("chevron-right", c["muted"], 14)
    chevron_open = icon_file("chevron-down", c["muted"], 14)
    check = icon_file("check", "#ffffff", 12)
    return f"""
    QWidget {{ background: {c['window']}; color: {c['text']};
               font-family: "Segoe UI Variable Text", "Segoe UI"; font-size: 10pt; }}
    QLabel {{ background: transparent; }}
    QLabel#brand {{ font-size: 13pt; font-weight: 600; }}
    QLabel#brandSub, QLabel#muted, QLabel#sourceLabel {{ color: {c['muted']}; }}
    QLabel#sectionTitle {{ font-size: 12pt; font-weight: 600; }}
    QLabel#groupTitle {{ color: {c['muted']}; font-size: 8pt; font-weight: 700;
                         letter-spacing: 1px; padding-top: 6px; }}
    QLabel#fieldLabel {{ color: {c['muted']}; font-size: 9pt; }}
    QLabel#notice {{ color: {c['warn']}; }}
    QLabel#faint {{ color: {c['faint']}; font-size: 9pt; }}
    QLabel#emptyTitle {{ font-size: 13pt; font-weight: 600; }}
    QLabel#emptyBadge {{ background: {c['accent_soft']}; border: 1px solid {c['accent_strong']};
                         border-radius: 42px; }}
    QLabel#pill {{ border-radius: 9px; padding: 2px 10px; font-size: 9pt; font-weight: 600; }}
    QLabel#pill[tone="ok"] {{ background: #1d3a2d; color: {c['ok']}; }}
    QLabel#pill[tone="bad"] {{ background: #3d3020; color: {c['warn']}; }}
    QLabel#pill[tone="missing"] {{ background: #402521; color: {c['danger']}; }}
    QLabel#pill[tone="neutral"] {{ background: {c['raised']}; color: {c['muted']}; }}
    QLabel#count {{ background: {c['raised']}; color: {c['muted']}; border-radius: 9px;
                    padding: 0 8px; font-size: 9pt; min-height: 18px; max-height: 18px; }}

    QWidget#topBar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
    QWidget#botBar {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
    QWidget#sidePanel {{ background: {c['surface']}; }}
    QWidget#editorPanel, QWidget#formPage {{ background: {c['window']}; }}
    QFrame#card, QFrame#cardPreview {{ background: {c['surface']}; border: 1px solid {c['border']};
                                       border-radius: 8px; }}
    QFrame#card QLabel, QFrame#cardPreview QLabel {{ background: transparent; }}
    QFrame#divider {{ background: {c['border']}; max-height: 1px; min-height: 1px; border: none; }}

    QPushButton {{ background: {c['raised']}; border: 1px solid {c['border_strong']}; border-radius: 6px;
                   padding: 6px 12px; min-height: 20px; }}
    QPushButton:hover {{ background: {c['hover']}; border-color: #56606a; }}
    QPushButton:pressed {{ background: #30363c; }}
    QPushButton:focus {{ border-color: {c['accent']}; }}
    QPushButton:disabled {{ color: {c['faint']}; background: {c['surface']}; border-color: {c['border']}; }}
    QPushButton#primary {{ background: {c['accent_strong']}; border-color: {c['accent']}; color: white;
                           font-weight: 600; }}
    QPushButton#primary:hover {{ background: #31b083; }}
    QPushButton#primary:disabled {{ background: #1d2b26; border-color: #24392f; color: #5f7a70; }}
    QPushButton#ghost {{ background: transparent; border-color: transparent; }}
    QPushButton#ghost:hover {{ background: {c['hover']}; border-color: {c['border']}; }}
    QPushButton#chip {{ background: transparent; border: 1px solid {c['border_strong']}; border-radius: 15px;
                        padding: 4px 12px 4px 9px; color: {c['muted']}; }}
    QPushButton#chip:hover {{ background: {c['hover']}; }}
    QPushButton#chip:checked {{ background: {c['accent_soft']}; color: {c['text']}; border-color: {c['accent_strong']}; }}
    QPushButton#chip:checked:hover {{ background: #24453a; }}

    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox {{
        background: {c['field']}; border: 1px solid {c['border_strong']}; border-radius: 6px;
        padding: 5px 9px; selection-background-color: #2d5a4a; }}
    QLineEdit:hover, QComboBox:hover, QTextEdit:hover {{ border-color: #4c555c; }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {c['accent']}; }}
    QLineEdit:disabled, QComboBox:disabled, QTextEdit:disabled {{ color: {c['faint']}; border-color: {c['border']}; }}
    QLineEdit[readOnly="true"] {{ background: {c['surface']}; color: {c['muted']}; }}
    QComboBox {{ min-height: 22px; padding-right: 26px; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{ background: {c['raised']}; border: 1px solid {c['border_strong']};
                                   selection-background-color: {c['accent_soft']}; outline: none; padding: 4px; }}
    QComboBox QLineEdit {{ border: none; padding: 0; background: transparent; }}

    QCheckBox {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
                            border: 1px solid #56606a; background: {c['field']}; }}
    QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
    QCheckBox::indicator:checked {{ background: {c['accent_strong']}; border-color: {c['accent']};
                                    image: url("{check}"); }}
    QCheckBox::indicator:disabled {{ background: {c['surface']}; border-color: {c['border']}; }}

    QTreeWidget, QTableWidget, QListWidget {{ background: {c['surface']}; border: none; outline: none;
        alternate-background-color: #1d2124; gridline-color: {c['border']}; }}
    QTreeWidget::item {{ padding: 5px 4px; }}
    QListWidget::item {{ padding: 6px 6px; border-radius: 4px; }}
    QTableWidget::item {{ padding: 4px 6px; }}
    QTreeWidget::item:hover, QTableWidget::item:hover, QListWidget::item:hover {{ background: {c['hover']}; }}
    QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
        background: {c['accent_soft']}; color: white; }}
    QTreeWidget::branch {{ background: transparent; }}
    QTreeWidget::branch:selected {{ background: {c['accent_soft']}; }}
    QTreeWidget::branch:has-children:closed {{ image: url("{chevron_right}"); }}
    QTreeWidget::branch:has-children:open {{ image: url("{chevron_open}"); }}
    QHeaderView {{ background: {c['surface']}; }}
    QHeaderView::section {{ background: {c['surface']}; color: {c['muted']}; border: none;
                            border-bottom: 1px solid {c['border']}; padding: 8px 6px; font-weight: 600; }}
    QTableCornerButton::section {{ background: {c['surface']}; border: none; }}

    QTabWidget::pane {{ border: none; border-top: 1px solid {c['border']}; }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{ background: transparent; padding: 8px 16px; color: {c['muted']};
                    border-bottom: 2px solid transparent; margin-right: 2px; }}
    QTabBar::tab:hover {{ color: {c['text']}; }}
    QTabBar::tab:selected {{ color: {c['text']}; border-bottom-color: {c['accent']}; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: #3a4247; border-radius: 3px; min-height: 28px; min-width: 28px; }}
    QScrollBar::handle:hover {{ background: #4b555c; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QSplitter::handle {{ background: {c['border']}; }}
    QSplitter::handle:hover {{ background: {c['accent_strong']}; }}
    QProgressBar {{ background: {c['field']}; border: 1px solid {c['border_strong']}; border-radius: 6px;
                    text-align: center; min-height: 14px; color: {c['text']}; }}
    QProgressBar::chunk {{ background: {c['accent_strong']}; border-radius: 5px; }}
    QToolTip {{ background: {c['raised']}; color: {c['text']}; border: 1px solid {c['border_strong']};
                padding: 6px; }}
    QMenu {{ background: {c['raised']}; border: 1px solid {c['border_strong']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['accent_soft']}; }}
    QDialog {{ background: {c['window']}; }}
    QFrame#toast {{ background: {c['raised']}; border: 1px solid {c['border_strong']};
                    border-left: 3px solid {c['accent']}; border-radius: 8px; }}
    QFrame#toast[tone="ok"] {{ border-left-color: {c['ok']}; }}
    QFrame#toast[tone="warn"] {{ border-left-color: {c['warn']}; }}
    QFrame#toast[tone="error"] {{ border-left-color: {c['danger']}; }}
    QFrame#toast QLabel {{ background: transparent; }}
    QPushButton#toastAction {{ background: transparent; border: 1px solid {c['accent_strong']};
                               color: {c['accent']}; font-weight: 600; padding: 4px 10px; }}
    QPushButton#toastAction:hover {{ background: {c['accent_soft']}; }}
    """
