"""
Analyze mods_data and report why configs may not appear in the dealer.
"""
from pathlib import Path

from generator import validate


def analyze(mods_data: dict) -> dict:
    """
    Returns {mod_name: [{config_name, critical: [...], warnings: [...]}]}
    Only mods/configs that have at least one issue are included.
    """
    result = {}
    for mod_name, entries in mods_data.items():
        mod_issues = []
        for entry in entries:
            critical = []
            warnings = []
            data = entry.info_content or {}

            if entry.status == "missing":
                critical.append("No info file")
            else:
                if entry.parse_error:
                    critical.append(f"Unreadable JSON: {entry.parse_error}")
                critical.extend(f"{field} is missing or invalid" for field in validate(data))

                if not data.get("Description"):
                    warnings.append("No description set")
                if not data.get("Population"):
                    warnings.append("Population is missing or zero (traffic/dealer selection may be affected)")

                stats_missing = [k for k in ("Power", "Torque", "Weight")
                                 if not data.get(k)]
                if stats_missing:
                    warnings.append(f"Stats not filled: {', '.join(stats_missing)}")

                if entry.info_path:
                    fname = Path(entry.info_path).name
                    expected = f"info_{entry.config_name}.json"
                    if fname != expected:
                        warnings.append(f"Nonstandard info name; expected {expected}")

            if critical or warnings:
                mod_issues.append({
                    "config_name": entry.config_name,
                    "critical": critical,
                    "warnings": warnings,
                })

        if mod_issues:
            result[mod_name] = mod_issues

    return result
