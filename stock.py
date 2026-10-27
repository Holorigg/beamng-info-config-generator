"""Read suggested metadata from the installed game's stock vehicles (read-only)."""
import statistics
import zipfile
from functools import lru_cache
from pathlib import Path

import json_utils

MAX_INFO_BYTES = 4 * 1024 * 1024
MODEL_FIELDS = ("Body Style", "InsuranceClass", "Region", "Years", "defaultPaintName1")
NUMERIC_FIELDS = ("Value", "Power", "Torque", "Weight")


def _vehicle_archive(game_dir, key) -> Path | None:
    if not game_dir or not key:
        return None
    path = Path(game_dir) / "content" / "vehicles" / f"{key}.zip"
    return path if path.is_file() else None


def is_stock_model(game_dir, key) -> bool:
    return _vehicle_archive(game_dir, key) is not None


def _median(values):
    values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0]
    if not values:
        return None
    value = statistics.median(values)
    return int(round(value)) if float(value).is_integer() or value > 100 else round(value, 1)


@lru_cache(maxsize=256)
def _read_model(archive_path: str, mtime: float, key: str):
    """Return (model info, list of config infos) from one stock vehicle archive."""
    model, configs = {}, []
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        for info in archive.infolist():
            name = info.filename
            if info.file_size > MAX_INFO_BYTES or not name.startswith(f"vehicles/{key}/"):
                continue
            leaf = name.rsplit("/", 1)[-1]
            if name.count("/") != 2 or not leaf.endswith(".json"):
                continue
            if leaf == "info.json":
                try:
                    model = json_utils.load_bytes(archive.read(info))
                except ValueError:
                    model = {}
            elif leaf.startswith("info_") and f"vehicles/{key}/{leaf[5:-5]}.pc" in names:
                try:
                    data = json_utils.load_bytes(archive.read(info))
                except ValueError:
                    continue
                if isinstance(data, dict):
                    configs.append(data)
    return model if isinstance(model, dict) else {}, configs


def suggestions(game_dir, key) -> dict:
    """Typical stock values for a model: model-level fields plus factory medians."""
    archive = _vehicle_archive(game_dir, key)
    if archive is None:
        return {}
    try:
        model, configs = _read_model(str(archive), archive.stat().st_mtime, key)
    except (OSError, zipfile.BadZipFile):
        return {}
    result = {}
    for field in MODEL_FIELDS:
        value = model.get(field)
        if value not in (None, "", [], {}):
            result[field] = value
    factory = [c for c in configs if str(c.get("Config Type", "")).casefold() == "factory"] or configs
    for field in NUMERIC_FIELDS:
        value = _median(c.get(field) for c in factory)
        if value is not None:
            result[field] = value
    if "Value" in result:
        result["Value"] = max(500, int(round(result["Value"] / 500.0)) * 500)
    for field in ("Body Style", "Years", "InsuranceClass", "Region"):
        if field not in result:
            # Some models keep these per configuration only.
            values = [c.get(field) for c in factory if c.get(field) not in (None, "", [], {})]
            if values:
                result[field] = values[0]
    brand = model.get("Brand")
    result["_label"] = f"{brand} {key}" if isinstance(brand, str) and brand else key
    result["_configs"] = len(configs)
    return result
