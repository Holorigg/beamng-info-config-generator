"""
JsonView — syntax-highlighted, editable JSON widget (PySide6).
Keys in blue, strings in orange, numbers in green, bools in purple.
Missing/invalid fields highlighted in red (entire line, bold).
"""
import json
import re

from PySide6.QtGui import (
    QColor, QFont, QSyntaxHighlighter, QTextCharFormat,
)
from PySide6.QtWidgets import QTextEdit, QWidget, QVBoxLayout
import json_utils


class _JsonHighlighter(QSyntaxHighlighter):
    CLR_KEY     = QColor("#9cdcfe")
    CLR_STRING  = QColor("#ce9178")
    CLR_NUMBER  = QColor("#b5cea8")
    CLR_BOOL    = QColor("#569cd6")
    CLR_MISSING = QColor("#e74c3c")

    _RE_LINE = re.compile(r'(\s*)("(?:[^"\\]|\\.)*")(\s*:\s*)(.*)')

    def __init__(self, document):
        super().__init__(document)
        self._missing: set = set()

    def set_missing(self, missing: set):
        self._missing = missing
        self.rehighlight()

    def highlightBlock(self, text: str):
        m = self._RE_LINE.match(text)
        if not m:
            return

        key_s   = len(m.group(1))
        key_e   = key_s + len(m.group(2))
        val_s   = key_e + len(m.group(3))
        val_raw = m.group(4).rstrip(",").strip()

        key_str = m.group(2)[1:-1]  # strip surrounding quotes

        # Missing fields: whole line in red bold
        if key_str in self._missing:
            fmt = QTextCharFormat()
            fmt.setForeground(self.CLR_MISSING)
            fmt.setFontWeight(QFont.Bold)
            self.setFormat(0, len(text), fmt)
            return

        # Key
        key_fmt = QTextCharFormat()
        key_fmt.setForeground(self.CLR_KEY)
        self.setFormat(key_s, key_e - key_s, key_fmt)

        # Value
        val_fmt = QTextCharFormat()
        if val_raw.startswith('"'):
            val_end = text.rfind('"') + 1
            if val_end > val_s:
                val_fmt.setForeground(self.CLR_STRING)
                self.setFormat(val_s, val_end - val_s, val_fmt)
        elif val_raw in ("true", "false", "null"):
            val_fmt.setForeground(self.CLR_BOOL)
            self.setFormat(val_s, len(val_raw), val_fmt)
        elif re.fullmatch(r"-?\d+(\.\d+)?", val_raw):
            val_fmt.setForeground(self.CLR_NUMBER)
            self.setFormat(val_s, len(val_raw), val_fmt)


class JsonView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._editor = QTextEdit()
        self._editor.setFont(QFont("Courier New", 10))
        self._editor.setAcceptRichText(False)
        self._editor.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #444444;
                border-radius: 4px;
            }
        """)

        self._hl = _JsonHighlighter(self._editor.document())
        layout.addWidget(self._editor)

    # ------------------------------------------------------------------ #

    def set_raw(self, text: str, highlight_fields: set = None):
        """Show raw file text — no re-serialization."""
        self._hl.set_missing(highlight_fields or set())
        self._editor.setPlainText(text.rstrip())

    def set_content(self, data: dict, highlight_fields: set = None):
        """Populate from a dict (used for missing-file templates)."""
        self._hl.set_missing(highlight_fields or set())
        self._editor.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))

    def get_content(self) -> tuple:
        """Returns (dict, None) or (None, error_str)."""
        raw = self._editor.toPlainText().strip()
        try:
            return json_utils.loads(raw), None
        except ValueError as exc:
            return None, str(exc)

    def get_raw_text(self) -> str:
        return self._editor.toPlainText()
