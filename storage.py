"""Small, atomic file writes and optional versioned backups."""
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


class OperationCancelled(Exception):
    pass


def check_cancel(cancel=None):
    if cancel is not None and cancel.is_set():
        raise OperationCancelled("Operation cancelled")


def backup_file(path):
    path = Path(path)
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = path.with_name(f"{path.name}.{stamp}.bak")
        shutil.copy2(path, target)
        return target
    return None


def write_text_atomic(path, content, backup=False):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if backup:
            backup_file(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
