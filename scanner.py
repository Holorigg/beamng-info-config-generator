"""
Mod and .pc file discovery for both extracted folders and zip archives.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import json_utils
from parser import parse_pc
from generator import validate
from storage import check_cancel

MAX_METADATA_BYTES = 16 * 1024 * 1024


@dataclass
class ConfigEntry:
    pc_path: str
    info_path: Optional[str]
    status: str                  # "ok" | "bad" | "missing"
    source: str                  # "folder" | "zip"
    source_path: str             # zip file path or mod root folder
    pc_content: dict
    info_content: Optional[dict]  # parsed dict, {} if parse failed, None if missing
    info_raw: Optional[str]       # raw file text; None if file doesn't exist
    missing_fields: list
    config_name: str
    auto_detected: dict
    thumbnail: Optional[bytes] = None
    thumbnail_path: Optional[str] = None
    parse_error: Optional[str] = None


def _info_config_path(pc_path: Path) -> Path:
    """Prefer info_{PC stem}.json, retaining historical naming fallbacks."""
    stem = pc_path.stem
    candidates = [f"info_{stem}.json", f"info_config_{stem}.json"]
    if stem.lower().startswith("config_"):
        stripped = stem[len("config_"):]
        candidates += [f"info_config_{stripped}.json", f"info_{stripped}.json"]

    for name in candidates:
        p = pc_path.parent / name
        if p.exists():
            return p

    return pc_path.parent / candidates[0]  # fallback — caller checks existence


def _scan_folder_mod(mod_root: Path, issues=None, cancel=None) -> list[ConfigEntry]:
    entries = []
    def on_error(exc):
        if issues is not None:
            issues.append(str(exc))
    for root, _dirs, files in os.walk(mod_root, onerror=on_error):
        check_cancel(cancel)
        for fname in sorted(files):
            check_cancel(cancel)
            if not fname.lower().endswith(".pc"):
                continue
            if ".bak." in fname.lower():
                continue

            pc_path = Path(root) / fname
            config_name = pc_path.stem
            info_path = _info_config_path(pc_path)

            try:
                if pc_path.stat().st_size > MAX_METADATA_BYTES:
                    raise ValueError("Config exceeds the 16 MiB metadata limit")
                pc_content = json_utils.load_file(pc_path)
            except Exception as exc:
                if issues is not None:
                    issues.append(f"{pc_path}: {exc}")
                continue

            auto = parse_pc(pc_content)

            thumbnail_path = None
            for ext in ('.jpg', '.jpeg', '.png'):
                img_path = pc_path.with_suffix(ext)
                if img_path.exists():
                    thumbnail_path = str(img_path)
                    break

            if info_path.exists():
                info_raw = None
                parse_error = None
                try:
                    if info_path.stat().st_size > MAX_METADATA_BYTES:
                        raise ValueError("Info file exceeds the 16 MiB metadata limit")
                    info_raw = json_utils.decode(info_path.read_bytes())
                    info_content = json_utils.loads(info_raw)
                except Exception as exc:
                    parse_error = str(exc)
                    if issues is not None:
                        issues.append(f"{info_path}: {exc}")
                    info_content = {}
                missing = validate(info_content)
                status = "ok" if not missing else "bad"
            else:
                info_raw     = None
                info_content = None
                missing      = []
                status       = "missing"
                parse_error  = None

            entries.append(ConfigEntry(
                pc_path=str(pc_path),
                info_path=str(info_path) if info_content is not None else None,
                status=status,
                source="folder",
                source_path=str(mod_root),
                pc_content={},
                info_content=info_content,
                info_raw=info_raw,
                missing_fields=missing,
                config_name=config_name,
                auto_detected=auto,
                thumbnail_path=thumbnail_path,
                parse_error=parse_error,
            ))

    return entries


def scan_mods_folder(mods_path: str, issues=None, progress=None, cancel=None) -> dict[str, list[ConfigEntry]]:
    """
    Scan a folder containing mods (zips and/or subfolders).
    Returns {mod_display_name: [ConfigEntry, ...]} — only mods with at least one .pc.
    """
    from zip_handler import scan_zip

    result: dict[str, list[ConfigEntry]] = {}
    mods_root = Path(mods_path)
    check_cancel(cancel)

    if not mods_root.is_dir():
        raise ValueError("Select a valid mods directory")
    items = []
    visited_dirs = set()
    discovered_roots = set()

    def resolved_key(path):
        try:
            return os.path.normcase(str(path.resolve()))
        except (OSError, RuntimeError):
            return None

    def discover(root):
        for item in sorted(root.iterdir()):
            check_cancel(cancel)
            if item.is_dir():
                key = resolved_key(item)
                if key is None or key in visited_dirs:
                    continue
                visited_dirs.add(key)
                if item.name.lower() in ("repo", "unpacked"):
                    discover(item)
                elif not item.name.startswith("."):
                    if key not in discovered_roots:
                        discovered_roots.add(key)
                        items.append(item)
            elif item.is_file() and item.suffix.lower() == ".zip":
                if item.name.lower().endswith((".tmp.zip", ".backup.zip")) or item.name.startswith("."):
                    continue
                key = resolved_key(item)
                if key is not None and key not in discovered_roots:
                    discovered_roots.add(key)
                    items.append(item)
    if (mods_root / "vehicles").is_dir() or any(mods_root.glob("*.pc")):
        items.append(mods_root)
    else:
        discover(mods_root)
    for index, item in enumerate(items):
        check_cancel(cancel)
        name = str(item.relative_to(mods_root)) if item != mods_root else mods_root.name
        if progress:
            progress(index, len(items), name)
        if item.is_file():
            entries = scan_zip(item, issues=issues, cancel=cancel)
            if entries:
                result[name] = entries
        elif item.is_dir():
            entries = _scan_folder_mod(item, issues=issues, cancel=cancel)
            if entries:
                result[name] = entries
    if progress:
        progress(len(items), len(items), "Scan complete")

    return result


def load_thumbnail(entry: ConfigEntry) -> bytes:
    if entry.thumbnail is not None:
        return entry.thumbnail
    if not entry.thumbnail_path:
        return b""
    if entry.source == "zip":
        import zipfile
        with zipfile.ZipFile(entry.source_path) as archive:
            if archive.getinfo(entry.thumbnail_path).file_size > MAX_METADATA_BYTES:
                raise ValueError("Thumbnail exceeds the 16 MiB limit")
            return archive.read(entry.thumbnail_path)
    path = Path(entry.thumbnail_path)
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("Thumbnail exceeds the 16 MiB limit")
    return path.read_bytes()
