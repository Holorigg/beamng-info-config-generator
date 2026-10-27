"""Locate the BeamNG.drive user mods folder and game installation on this computer."""
import os
import re
import sys
from pathlib import Path

STEAM_APP_DIR = "BeamNG.drive"


def _local_appdata() -> Path | None:
    value = os.environ.get("LOCALAPPDATA")
    return Path(value) if value else None


def user_mods_candidates() -> list[Path]:
    """Existing mods folders, newest layout first (0.40 uses BeamNG.drive/current)."""
    base = _local_appdata()
    found = []
    if base:
        found.append(base / "BeamNG" / "BeamNG.drive" / "current" / "mods")
        legacy = base / "BeamNG.drive"
        if legacy.is_dir():
            versions = sorted((item for item in legacy.iterdir() if re.fullmatch(r"\d+\.\d+", item.name)),
                              key=lambda item: tuple(map(int, item.name.split("."))), reverse=True)
            found.extend(item / "mods" for item in versions)
    home = Path.home()
    found.append(home / ".local" / "share" / "BeamNG" / "BeamNG.drive" / "current" / "mods")
    return [path for path in found if path.is_dir()]


def detect_user_mods() -> str:
    candidates = user_mods_candidates()
    return str(candidates[0]) if candidates else ""


def _steam_roots() -> list[Path]:
    roots = []
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        for name in ("SteamPath", "InstallPath"):
                            try:
                                roots.append(Path(winreg.QueryValueEx(handle, name)[0]))
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        roots.append(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam")
    else:
        roots.extend((Path.home() / ".steam" / "steam", Path.home() / ".local" / "share" / "Steam"))
    return roots


def _library_folders(steam_root: Path) -> list[Path]:
    folders = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return folders
    for value in re.findall(r'"path"\s+"([^"]+)"', text):
        folders.append(Path(value.replace("\\\\", "\\")))
    return folders


def is_game_dir(path) -> bool:
    return bool(path) and (Path(path) / "content" / "vehicles").is_dir()


def detect_game_dir() -> str:
    """Return the BeamNG.drive installation folder, or an empty string."""
    seen = set()
    for root in _steam_roots():
        for library in _library_folders(root):
            candidate = library / "steamapps" / "common" / STEAM_APP_DIR
            key = os.path.normcase(str(candidate))
            if key in seen:
                continue
            seen.add(key)
            if is_game_dir(candidate):
                return str(candidate)
    return ""


def game_version(game_dir) -> str:
    """Read the game version from integrity.json without loading the whole file."""
    try:
        with open(Path(game_dir) / "integrity.json", "r", encoding="utf-8", errors="replace") as stream:
            head = stream.read(4096)
    except OSError:
        return ""
    match = re.search(r'"version"\s*:\s*"([^"]+)"', head)
    if match:
        return match.group(1)
    # The version usually follows the large integrity list.
    try:
        with open(Path(game_dir) / "integrity.json", "rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 4096))
            tail = stream.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    match = re.search(r'"version"\s*:\s*"([^"]+)"', tail)
    return match.group(1) if match else ""
