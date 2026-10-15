"""Restrained desktop styling for a config editing workspace."""


def make_dark_style():
    return """
    QWidget { background: #202224; color: #e2e5e7; font-family: "Segoe UI"; font-size: 10pt; }
    QLabel { background: transparent; }
    QLabel#brand { font-size: 16pt; font-weight: 600; }
    QLabel#sectionTitle { font-size: 12pt; font-weight: 600; }
    QLabel#muted, QLabel#sourceLabel { color: #999fa4; }
    QWidget#topBar, QWidget#botBar { background: #272a2c; }
    QPushButton { background: #34383b; border: 1px solid #484e52; border-radius: 4px;
                  padding: 6px 12px; min-height: 20px; }
    QPushButton:hover { background: #42484c; border-color: #6a737a; }
    QPushButton:pressed, QPushButton:checked { background: #414a50; border-color: #9aa6ae; }
    QPushButton:disabled { color: #727a80; background: #282c2f; border-color: #363c40; }
    QPushButton#primary { background: #237657; border-color: #348d6c; color: white; }
    QPushButton#primary:hover { background: #2a8a66; }
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox {
        background: #191c1e; border: 1px solid #41474c; border-radius: 4px; padding: 5px 8px;
        selection-background-color: #3e6257; }
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: #65b496; }
    QComboBox { min-height: 22px; }
    QComboBox QAbstractItemView { background: #24292c; selection-background-color: #3e6257; }
    QTreeWidget, QTableWidget, QListWidget { background: #1a1d1f; border: none; outline: none;
                                           alternate-background-color: #202426; gridline-color: #303639; }
    QTreeWidget::item, QListWidget::item { padding: 5px 4px; }
    QTreeWidget::item:hover, QTableWidget::item:hover { background: #2b3336; }
    QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {
        background: #354b43; color: white; }
    QHeaderView::section { background: #292e31; color: #b7bfc4; border: none;
                           border-bottom: 1px solid #434a4f; padding: 8px; }
    QTabWidget::pane { border: none; border-top: 1px solid #41474b; }
    QTabBar::tab { background: transparent; padding: 9px 20px; color: #a1abb1;
                  border-bottom: 2px solid transparent; }
    QTabBar::tab:selected { color: white; border-bottom-color: #62b796; }
    QScrollArea { border: none; }
    QScrollBar:vertical { background: #202426; width: 10px; }
    QScrollBar:horizontal { background: #202426; height: 10px; }
    QScrollBar::handle { background: #50585e; border-radius: 4px; min-height: 24px; min-width: 24px; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
    QSplitter::handle { background: #373d41; }
    QProgressBar { border: 1px solid #464e53; border-radius: 4px; text-align: center; min-height: 16px; }
    QProgressBar::chunk { background: #3a9874; }
    QToolTip { background: #30383d; color: white; border: 1px solid #66727a; padding: 5px; }
    QFrame#cardPreview { background: #242b2e; border: 1px solid #434f55; border-radius: 6px; }
    """
