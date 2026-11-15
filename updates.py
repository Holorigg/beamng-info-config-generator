"""Look up the latest GitHub release once. Nothing is downloaded or installed."""
import json
import logging
import re
import threading
import urllib.request

from PySide6.QtCore import QObject, Signal

from about import APP_VERSION, PROJECT_URL

API_URL = "https://api.github.com/repos/Holorigg/beamng-info-config-generator/releases/latest"
RELEASES_URL = f"{PROJECT_URL}/releases/latest"
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(text):
    match = _VERSION.match(str(text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(tag, current=None) -> bool:
    remote, local = parse_version(tag), parse_version(APP_VERSION if current is None else current)
    return bool(remote and local and remote > local)


def release_from_api(data: dict):
    """The parts of a GitHub release the app uses, or None for anything unexpected."""
    tag = data.get("tag_name")
    version = parse_version(tag)
    if not version or data.get("draft") or data.get("prerelease"):
        return None
    url = str(data.get("html_url") or "")
    # Only ever open this project's own release pages.
    if not url.startswith(f"{PROJECT_URL}/releases/"):
        url = RELEASES_URL
    return {"tag": tag, "version": ".".join(str(part) for part in version), "url": url}


def fetch_latest(timeout=5.0):
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"beamng-infogen/{APP_VERSION}",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return release_from_api(json.loads(response.read(1024 * 1024).decode("utf-8")))


class UpdateCheck(QObject):
    """Runs one lookup in a background thread; finished(release or None, error text)."""
    finished = Signal(object, str)

    def start(self):
        threading.Thread(target=self._run, name="update-check", daemon=True).start()

    def _run(self):
        release, error = None, ""
        try:
            release = fetch_latest()
        except Exception as exc:
            error = str(exc) or type(exc).__name__
            logging.info("Update check failed: %s", error)
        try:
            self.finished.emit(release, error)
        except RuntimeError:
            pass  # The window closed first.
