"""
Auto-detection of vehicle properties from .pc file parts section.
"""
import re


def parse_pc(pc_data: dict) -> dict:
    parts = pc_data.get("parts", {})
    if not isinstance(parts, dict):
        parts = {}
    return {
        "Drivetrain":   _detect_drivetrain(parts),
        "Transmission": _detect_transmission(parts),
        "Fuel Type":    _detect_fuel(parts),
    }


def _detect_drivetrain(parts: dict) -> str:
    for key, val in parts.items():
        if not isinstance(val, str) or not val:
            continue
        kl, vl = key.lower(), val.lower()
        if "transfer_case" in kl:
            if "_rwd" in vl: return "RWD"
            if "_awd" in vl: return "AWD"
            if "_fwd" in vl: return "FWD"
        if "transaxle" in kl:
            return "FWD"
    return "RWD"


def _detect_transmission(parts: dict) -> str:
    for key, val in parts.items():
        if "shifter" in key.lower() and isinstance(val, str) and "dct" in val.lower():
            return "DCT"
    for key, val in parts.items():
        if "transmission" in key.lower() and isinstance(val, str) and val:
            vl = val.lower()
            if re.search(r"_\d*m\b", vl): return "Manual"
            if re.search(r"_\d*a\b", vl): return "Automatic"
            if "cvt" in vl:               return "CVT"
            if "dct" in vl:               return "DCT"
    return "Automatic"


def _detect_fuel(parts: dict) -> str:
    for key, val in parts.items():
        if not isinstance(val, str) or not val:
            continue
        kl, vl = key.lower(), val.lower()
        if "engine" in kl or "exhaust" in kl or "intake" in kl:
            if "diesel"   in vl: return "Diesel"
            if "electric" in vl: return "Electric"
            if "hybrid"   in vl: return "Hybrid"
    return "Gasoline"
