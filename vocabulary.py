"""Field vocabulary used by BeamNG.drive 0.40 stock vehicle info files.

Values were collected from the stock content/vehicles archives. Existing
values outside these lists are preserved; the lists only seed the editor.
"""

CONFIG_TYPES = ["Factory", "Custom", "Race", "Drift", "Rally", "Police", "Service"]
DRIVETRAINS = ["RWD", "FWD", "AWD", "4WD", "4x2", "4x4", "6x2", "6x4", "6x6", "8x4", "8x8"]
TRANSMISSIONS = ["Manual", "Automatic", "DCT", "Sequential", "CVT", "Other"]
FUEL_TYPES = ["Gasoline", "Diesel", "Battery", "Other"]
INDUCTION_TYPES = ["NA", "Turbo", "SC", "Turbo + N2O", "SC + N2O"]
BODY_STYLES = [
    "Sedan", "Coupe", "Hatchback", "Liftback", "Wagon", "Convertible", "SUV", "Pickup",
    "Van", "Bus", "Box Truck", "Flatbed", "Dump Truck", "Fifth Wheel Truck",
]
# Career insurance tier; blank keeps the field out of the file.
INSURANCE_CLASSES = ["", "dailyDriver", "commercial", "prestige"]

# Values written by earlier releases of this editor, mapped to the game's own terms.
LEGACY_VALUES = {
    "Induction Type": {"Natural": "NA", "Supercharger": "SC", "Twin Turbo": "Turbo"},
    "Fuel Type": {"Electric": "Battery"},
}

DEFAULT_INDUCTION = "NA"


def canonical(field: str, value):
    """Return the game's spelling for a legacy editor value; others pass through."""
    if isinstance(value, str):
        return LEGACY_VALUES.get(field, {}).get(value, value)
    return value


def is_electric(fuel_type) -> bool:
    return isinstance(fuel_type, str) and fuel_type.casefold() in {"battery", "electric"}


def propulsion_for(fuel_type) -> str:
    return "Electric" if is_electric(fuel_type) else "ICE"
