"""Read-only RLS contract metadata discovery and vehicle diagnostics."""
from __future__ import annotations

import hashlib
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping

import json_utils
from storage import check_cancel

MAX_METADATA_BYTES = 16 * 1024 * 1024
KNOWN_POOL_SHA256 = "3623b1f4d275c27e11fbd730ddd0ca013e38160692c3885ab38dd3e5f4b1cf31"
PROGRESSION_PATH = "gameplay/fre/freProgression.config.json"
POOL_PATH = "lua/ge/extensions/gameplay/events/freContracts/vehiclePool.lua"


@dataclass
class RlsInstallation:
    path: str
    version: str
    config: dict
    pool_hash: str
    supported: bool
    issue: str = ""


@dataclass
class VehicleModel:
    key: str
    config_types: tuple[str, ...]
    sources: tuple[str, ...]
    issue: str = ""
    excluded: bool = False


@dataclass
class ModelDiagnosis:
    model: VehicleModel
    drift: str
    drag: str
    race: str


def _read_file(path: Path) -> bytes:
    if path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("Metadata exceeds the 16 MiB limit")
    return path.read_bytes()


def _read_zip(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > MAX_METADATA_BYTES:
        raise ValueError("Metadata exceeds the 16 MiB limit")
    return archive.read(info)


def _version_from_name(value: str) -> str:
    match = re.search(r"(?<!\d)(\d+\.\d+(?:\.\d+)+)(?!\d)", value)
    return match.group(1) if match else ""


def _version_from_mod_info(read_mod_info) -> str:
    try:
        data = json_utils.load_bytes(read_mod_info())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return ""
    for key in ("version", "modVersion", "mod_version"):
        value = data.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def _zip_mod_info(archive: zipfile.ZipFile) -> bytes:
    names = sorted((name for name in archive.namelist()
                    if name.replace("\\", "/").casefold().endswith("mod_info.json")),
                   key=str.casefold)
    if not names:
        raise KeyError("mod_info.json not found")
    return _read_zip(archive, names[0])


def _installation(path: Path, read_member, name: str) -> RlsInstallation | None:
    try:
        config = json_utils.load_bytes(read_member(PROGRESSION_PATH))
        pool_data = read_member(POOL_PATH)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return None

    pool_hash = hashlib.sha256(pool_data).hexdigest()
    version = _version_from_name(name)
    if not version:
        version = _version_from_mod_info(lambda: read_member("mod_info.json"))
    supported = pool_hash == KNOWN_POOL_SHA256
    warnings = []
    if not supported:
        warnings.append("Vehicle pool hash is not the verified 2.7.2 rule source")
    if version != "2.7.2":
        warnings.append("Version is unknown or differs from the verified 2.7.2 rule source")
    issue = "; ".join(warnings)
    return RlsInstallation(str(path), version, config, pool_hash, supported, issue)


def discover_rls(mods_root: str | os.PathLike) -> list[RlsInstallation]:
    """Find RLS archives/unpacked installs at root, repo, or unpacked levels."""
    root = Path(mods_root)
    if not root.is_dir():
        return []

    search_roots = [root]
    search_roots.extend(root / name for name in ("repo", "unpacked") if (root / name).is_dir())
    candidates: dict[str, Path] = {}

    def add_candidate(path: Path) -> None:
        if path.name.casefold().startswith(("infogen_rls_contracts", ".")):
            return
        try:
            key = os.path.normcase(str(path.resolve()))
        except (OSError, RuntimeError):
            key = os.path.normcase(str(path.absolute()))
        candidates[key] = path

    for search_root in search_roots:
        if (search_root / PROGRESSION_PATH).is_file() and (search_root / POOL_PATH).is_file():
            add_candidate(search_root)
        try:
            items = sorted(search_root.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            continue
        for item in items:
            if item.name.casefold().startswith(("infogen_rls_contracts", ".")):
                continue
            if item.is_file() and item.suffix.casefold() == ".zip":
                add_candidate(item)
            elif item.is_dir() and (item / PROGRESSION_PATH).is_file() and (item / POOL_PATH).is_file():
                add_candidate(item)

    found = []
    for path in sorted(candidates.values(), key=lambda item: str(item).casefold()):
        try:
            if path.is_dir():
                def read_folder_member(name, base=path):
                    if name == "mod_info.json":
                        for relative in ("mod_info.json", "mod_info/mod_info.json"):
                            candidate = base / relative
                            if candidate.is_file():
                                return _read_file(candidate)
                        raise FileNotFoundError(name)
                    return _read_file(base.joinpath(*PurePosixPath(name).parts))

                installation = _installation(
                    path,
                    read_folder_member,
                    path.name,
                )
            else:
                with zipfile.ZipFile(path, "r") as archive:
                    def read_archive_member(name, zf=archive):
                        if name == "mod_info.json":
                            return _zip_mod_info(zf)
                        return _read_zip(zf, name)

                    installation = _installation(
                        path,
                        read_archive_member,
                        path.name,
                    )
            if installation is not None:
                found.append(installation)
        except (OSError, zipfile.BadZipFile):
            continue
    return found


def _model_key(pc_path: str) -> str | None:
    normalized = pc_path.replace("\\", "/")
    parts = normalized.split("/")
    for index, part in enumerate(parts[:-1]):
        if part.casefold() == "vehicles" and index + 1 < len(parts) - 1:
            key = parts[index + 1].strip().casefold()
            return key if re.fullmatch(r"[a-z0-9_-]+", key) else None
    return None


def model_key(entry) -> str | None:
    """Return the normalized vehicle model key for a scanner ConfigEntry."""
    return _model_key(str(getattr(entry, "pc_path", entry)))


def _config_types(info: dict | None) -> set[str]:
    if not isinstance(info, dict):
        return set()
    value = next((v for k, v in info.items() if str(k).casefold() == "config type"), None)
    result = set()

    def add_values(candidate):
        if isinstance(candidate, str) and candidate.strip():
            result.add(candidate.strip())
        elif isinstance(candidate, (list, tuple, set)):
            result.update(item.strip() for item in candidate if isinstance(item, str) and item.strip())
        elif isinstance(candidate, dict):
            result.update(str(name).strip() for name, present in candidate.items()
                          if present and str(name).strip())

    add_values(value)
    aggregates = next((v for k, v in info.items() if str(k).casefold() == "aggregates"), None)
    if isinstance(aggregates, dict):
        aggregate_types = next((v for k, v in aggregates.items()
                                if str(k).casefold() == "config type"), None)
        add_values(aggregate_types)
    return result


def _metadata_info(archive: zipfile.ZipFile, key: str) -> dict | None:
    suffix = f"vehicles/{key}/info.json"
    member = next((name for name in archive.namelist() if name.replace("\\", "/").casefold().endswith(suffix.casefold())), None)
    if member is None:
        return None
    return json_utils.load_bytes(_read_zip(archive, member))


def _is_excluded(info: dict | None) -> bool:
    if not isinstance(info, dict):
        return False
    for key, value in info.items():
        if str(key).casefold() not in {"type", "category", "class"}:
            continue
        values = value if isinstance(value, (list, tuple, set)) else [value]
        if any(any(token in str(item).casefold() for token in ("trailer", "prop", "device")) for item in values):
            return True
    return False


def collect_models(entries: Iterable, cancel=None, progress=None) -> list[VehicleModel]:
    """Group scanner ConfigEntry objects by vehicle model key."""
    if isinstance(entries, Mapping):
        flattened = (entry for values in entries.values() for entry in values)
    else:
        flattened = iter(entries)
    groups: dict[str, dict] = {}
    source_models: dict[str, set[str]] = {}
    source_entries: dict[str, list] = {}
    entry_list = list(flattened)
    total = len(entry_list)
    for index, entry in enumerate(entry_list):
        check_cancel(cancel)
        key = model_key(entry)
        if key is None:
            continue
        group = groups.setdefault(key, {"types": set(), "sources": set()})
        group["types"].update(_config_types(getattr(entry, "info_content", None)))
        source = str(getattr(entry, "source_path", "") or "")
        if source:
            group["sources"].add(source)
            source_models.setdefault(source, set()).add(key)
            source_entries.setdefault(source, []).append(entry)
        if progress:
            progress(index + 1, total, key)

    model_metadata: dict[str, list[dict | None]] = {key: [] for key in groups}
    for source, keys in sorted(source_models.items(), key=lambda pair: pair[0].casefold()):
        check_cancel(cancel)
        current_entries = source_entries[source]
        is_zip = any(getattr(entry, "source", "") == "zip" for entry in current_entries)
        if is_zip:
            try:
                with zipfile.ZipFile(source, "r") as archive:
                    for key in sorted(keys):
                        check_cancel(cancel)
                        try:
                            model_metadata[key].append(_metadata_info(archive, key))
                        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                            model_metadata[key].append(None)
            except (OSError, zipfile.BadZipFile):
                for key in keys:
                    model_metadata[key].append(None)
        else:
            for key in sorted(keys):
                check_cancel(cancel)
                first = next((entry for entry in current_entries if model_key(entry) == key), None)
                info_path = None
                if first:
                    pc_path = Path(first.pc_path)
                    info_path = next((parent / "info.json" for parent in pc_path.parents
                                      if parent.name.casefold() == key
                                      and parent.parent.name.casefold() == "vehicles"), None)
                try:
                    data = json_utils.load_bytes(_read_file(info_path)) if info_path and info_path.is_file() else None
                except (OSError, ValueError):
                    data = None
                model_metadata[key].append(data)

    models = []
    for key in sorted(groups):
        group = groups[key]
        metadata = model_metadata[key]
        for info in metadata:
            group["types"].update(_config_types(info))
        excluded = any(_is_excluded(info) for info in metadata if info is not None)
        issues = []
        if not metadata or any(info is None for info in metadata):
            issues.append("Model info missing; common for vanilla-based configuration packs")
        if len(group["sources"]) > 1:
            issues.append("Found in multiple archives; effective override precedence is uncertain")
        models.append(VehicleModel(
            key,
            tuple(sorted(group["types"], key=str.casefold)),
            tuple(sorted(group["sources"], key=str.casefold)),
            "; ".join(issues),
            excluded,
        ))
    if progress:
        progress(total, total, "Model collection complete")
    return models


def _lookup(values) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {value.casefold() for value in values if isinstance(value, str) and value.strip()}


def _diagnose(model: VehicleModel, configured: set[str], blacklist: set[str], whitelist: set[str]) -> str:
    key = model.key.casefold()
    if model.excluded:
        return "Excluded model"
    if key in blacklist:
        return "Blacklisted"
    if whitelist and not whitelist.intersection(value.casefold() for value in model.config_types):
        if "model info missing" in model.issue.casefold():
            return "Config type unverified"
        return "Needs " + "/".join(value.title() for value in sorted(whitelist)) + " config"
    if configured and key not in configured:
        return "Not in pool"
    return "In pool"


def diagnose(installation: RlsInstallation, models: Iterable[VehicleModel],
             patched_models: Iterable[str] = ()) -> list[ModelDiagnosis]:
    """Compare local models with the verified RLS contract model settings."""
    config = installation.config if isinstance(installation.config, dict) else {}
    models = list(models)
    configured = _lookup(config.get("contractVehicleModels"))
    patched = {value.casefold() for value in patched_models if isinstance(value, str)}
    if configured:
        configured |= patched
    global_contracts = config.get("contracts", {})
    if not isinstance(global_contracts, dict):
        global_contracts = {}
    discipline_settings = {}
    for item in config.get("disciplines", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        contract = item.get("contracts") if isinstance(item.get("contracts"), dict) else {}
        discipline_settings[item["id"].casefold()] = (
            _lookup(contract.get("vehicleBlacklist")),
            _lookup(contract.get("contractVehicleConfigTypeWhitelist",
                                 global_contracts.get("contractVehicleConfigTypeWhitelist"))),
        )

    results = []
    for model in models:
        default = (set(), _lookup(global_contracts.get("contractVehicleConfigTypeWhitelist")))
        drift_blacklist, drift_whitelist = discipline_settings.get("drift", default)
        drag_blacklist, drag_whitelist = discipline_settings.get("drag", default)
        race_blacklist, race_whitelist = discipline_settings.get("roadracing", default)
        drift = _diagnose(model, configured, drift_blacklist, drift_whitelist)
        drag = _diagnose(model, configured, drag_blacklist, drag_whitelist)
        race = _diagnose(model, configured, race_blacklist, race_whitelist)
        if not installation.supported or installation.issue:
            warning = (" (RLS rules unverified estimate)" if not installation.supported
                       else " (RLS version warning)")
            drift += warning
            drag += warning
            race += warning
        results.append(ModelDiagnosis(model, drift, drag, race))
    return results
