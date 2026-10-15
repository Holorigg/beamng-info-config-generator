"""Qt workers with cooperative cancellation and GUI-thread progress delivery."""
import threading
import traceback

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout

from storage import OperationCancelled
from ui_icons import icon


class TaskWorker(QThread):
    progress = Signal(int, int, str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.cancel_event = threading.Event()
        self.value = None
        self.error = None
        self.cancelled = False

    def run(self):
        try:
            self.value = self.task(self.cancel_event, self.progress.emit)
        except OperationCancelled:
            self.cancelled = True
        except Exception:
            self.error = traceback.format_exc()


class TaskDialog(QDialog):
    def __init__(self, title, task, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.worker = TaskWorker(task, self)
        self._finished = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        self.label = QLabel(title)
        self.label.setWordWrap(True)
        self.label.setMinimumHeight(52)
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        layout.addWidget(self.bar)
        self.count = QLabel("")
        layout.addWidget(self.count)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setIcon(icon("x"))
        self.cancel_button.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_button)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)

    @Slot(int, int, str)
    def on_progress(self, current, total, message):
        self.bar.setRange(0, max(1, total))
        self.bar.setValue(current)
        self.label.setText(message)
        self.count.setText(f"{current} / {total}")

    @Slot()
    def cancel(self):
        self.worker.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Cancelling...")

    @Slot()
    def on_finished(self):
        self._finished = True
        self.accept()

    def reject(self):
        if self._finished:
            super().reject()
        else:
            self.cancel()

    def closeEvent(self, event):
        if self._finished:
            event.accept()
        else:
            self.cancel()
            event.ignore()

    def execute(self):
        self.worker.start()
        self.exec()
        self.worker.wait()
        return self.worker
