"""
info_config JSON generation and validation.
"""
import random
import math

from vocabulary import DEFAULT_INDUCTION, canonical, propulsion_for

_DESC_TEMPLATES = [
    "A well-rounded configuration suited for everyday driving.",
    "A capable variant offering a balanced blend of performance and comfort.",
    "Designed for those who demand reliability without sacrificing style.",
    "A versatile setup ready for both city streets and open highways.",
    "This configuration delivers a confident driving experience across all conditions.",
    "An accessible variant with a focus on practicality and dependability.",
    "Built for drivers who value smooth performance and long-distance comfort.",
    "A solid choice for anyone looking for a dependable daily driver.",
]


def _default_description() -> str:
    return random.choice(_DESC_TEMPLATES)

REQUIRED_FIELDS = ["Value", "Config Type", "Configuration", "Drivetrain", "Transmission", "Fuel Type"]


def validate(data: dict) -> list[str]:
    """Returns list of missing or invalid required field names."""
    if not isinstance(data, dict):
        return list(REQUIRED_FIELDS)
    missing = []
    for f in REQUIRED_FIELDS:
        if f not in data:
            missing.append(f)
        elif f == "Value":
            try:
                if isinstance(data[f], bool) or not math.isfinite(float(data[f])) or float(data[f]) <= 0:
                    missing.append(f)
            except (TypeError, ValueError):
                missing.append(f)
        elif not isinstance(data[f], str) or not data[f].strip():
            missing.append(f)
    return missing


def generate(config_name: str, auto_detected: dict, defaults: dict) -> dict:
    """Build a new info_config dict from auto-detection + user defaults."""
    data = {
        "Configuration":  config_name,
        "Config Type":    defaults.get("config_type", "Factory"),
        "Drivetrain":     auto_detected.get("Drivetrain",   "RWD"),
        "Transmission":   auto_detected.get("Transmission", "Automatic"),
        "Fuel Type":      canonical("Fuel Type", auto_detected.get("Fuel Type", "Gasoline")),
        "Propulsion":     propulsion_for(auto_detected.get("Fuel Type")),
        "Induction Type": canonical("Induction Type", defaults.get("induction") or DEFAULT_INDUCTION),
        "Body Style":     defaults.get("body_style", "Sedan"),
        "Value":          _random_price(defaults),
        "Population":     5000,
        "Off-Road Score": 20,
        "Description":    defaults.get("description") or _default_description(),
    }
    if defaults.get("insurance_class"):
        data["InsuranceClass"] = defaults["insurance_class"]
    _apply_stats(data, defaults)
    return data


def fix(existing: dict, config_name: str, auto_detected: dict, defaults: dict) -> dict:
    """Add only missing required fields; leave all existing fields untouched."""
    result = dict(existing)
    invalid = set(validate(result))
    if "Configuration" in invalid:
        result["Configuration"] = config_name
    if "Config Type" in invalid:
        result["Config Type"] = defaults.get("config_type", "Factory")
    if "Drivetrain" in invalid:
        result["Drivetrain"] = auto_detected.get("Drivetrain", "RWD")
    if "Transmission" in invalid:
        result["Transmission"] = auto_detected.get("Transmission", "Automatic")
    if "Fuel Type" in invalid:
        result["Fuel Type"] = canonical("Fuel Type", auto_detected.get("Fuel Type", "Gasoline"))
    if "Value" in invalid:
        result["Value"] = _random_price(defaults)
    return result


def _random_price(defaults: dict) -> int:
    try:
        lo = int(defaults.get("price_min", 10000))
        hi = int(defaults.get("price_max", 50000))
    except (ValueError, TypeError):
        lo, hi = 10000, 50000
    if lo > hi:
        lo, hi = hi, lo
    lo, hi = max(1, lo), max(1, hi)
    return min(hi, max(lo, round(random.randint(lo, hi) / 500) * 500))


def _apply_stats(data: dict, defaults: dict):
    for key, dkey in [("Power", "power"), ("Torque", "torque"), ("Weight", "weight")]:
        val = defaults.get(dkey, "")
        try:
            number = float(val)
            if math.isfinite(number) and number > 0:
                data[key] = int(number) if number.is_integer() else number
        except (ValueError, TypeError):
            pass
