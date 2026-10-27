"""Execute an installed RLS pool in an isolated Lua 5.1 VM, never launch BeamNG.

Usage: python scripts/verify_rls_files.py --rls path/to/rls.zip
Optional --vehicles points to BeamNG.drive/content/vehicles for stock metadata.
No RLS or game code is copied into the repository.
"""
import argparse
import copy
import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json_utils
from rls_contracts import LAYOUTS, OVERHAUL_LAYOUT
from rls_patch import LUA_EXTENSION, OWNER


def check(rls_path, vehicles_path=None):
    from lupa.lua51 import LuaRuntime

    with zipfile.ZipFile(rls_path) as archive:
        names = set(archive.namelist())
        layout = next((item for item in LAYOUTS if item.pool in names), None)
        if layout is None:
            raise SystemExit("No known RLS contract layout in this archive")
        config_source = archive.read(layout.config_lua).decode("utf-8-sig")
        pool_bytes = archive.read(layout.pool)
        raw = json_utils.load_bytes(archive.read(layout.progression))
    # 2.8 renamed the inventory module and requires its helpers instead of a global.
    inventory = ("overhaul_career_garage_inventory" if layout is OVERHAUL_LAYOUT
                 else "career_modules_inventory")
    configured = raw.get("contractVehicleModels", [])
    models = {}
    stock = {}
    if vehicles_path:
        for key in configured:
            path = Path(vehicles_path) / f"{key}.zip"
            if not path.is_file():
                continue
            with zipfile.ZipFile(path) as archive:
                name = f"vehicles/{key}/info.json"
                names = set(archive.namelist())
                if name not in names:
                    continue
                model = json_utils.load_bytes(archive.read(name))
                types = set()
                for info in archive.infolist():
                    if (info.filename.startswith(f"vehicles/{key}/info_")
                            and info.filename.endswith(".json") and info.file_size < 16 * 1024 * 1024):
                        stem = Path(info.filename).stem.removeprefix("info_")
                        if f"vehicles/{key}/{stem}.pc" not in names:
                            continue
                        value = json_utils.load_bytes(archive.read(info)).get("Config Type")
                        if isinstance(value, str):
                            types.add(value)
                model["aggregates"] = {"Config Type": {value: True for value in types}}
                models[key] = model
                stock[key] = sorted(types)
    # Ensure the fixture also works without installed stock content.
    for key in configured:
        models.setdefault(key, {"Type": "Car", "aggregates": {"Config Type": {"Race": True}}})
    additions = {"infogen_test_race": "Race", "infogen_test_factory": "Factory"}
    for key, config_type in additions.items():
        if key in configured:
            raise AssertionError("Fixture model unexpectedly already configured")
        models[key] = {"Type": "Car", "aggregates": {"Config Type": {config_type: True}}}
    models["infogen_test_trailer"] = {"Type": "Trailer"}
    runtime = LuaRuntime(unpack_returned_tuples=True)
    lua = runtime.globals()
    to_lua = lambda value: runtime.table_from(value, recursive=True)
    manifest = {"owner": OWNER, "schema": 1, "verifiedRules": True,
                "models": [*additions, "infogen_test_trailer"]}
    lua.jsonReadFile = lambda path: to_lua(manifest if "infogen_rls" in path else raw)
    lua.log = lambda *_: None
    lua.config_file = "/" + layout.config_lua
    # Only the inspected layout's config exists, so the addon must pick the right module.
    lua.FS = runtime.eval(
        "{fileExists = function(_, path) return path == config_file or path:find('infogen_rls') ~= nil end}")
    lua.core = to_lua({"getModelList": lambda: to_lua({"models": models})})
    lua[inventory] = to_lua({"getVehicles": lambda: to_lua({})})
    runtime.execute('package.preload["core/vehicles"] = function() return core end')
    lua.config_source = config_source
    lua.config_module = layout.config_module
    runtime.execute('package.preload[config_module] = assert(loadstring(config_source))')
    config = runtime.eval('require(config_module)')
    helpers = runtime.eval("{pickRandomFromList = function(list) return list[math.random(#list)] end}")
    lua.gameplay_events_freContracts_helpers = helpers
    lua.fre_helpers = helpers
    runtime.execute('package.preload["overhaul/events/fre/helpers"] = function() return fre_helpers end')
    pool = runtime.execute(pool_bytes.decode("utf-8-sig"))

    def picks(discipline):
        runtime.execute("math.randomseed(111)")
        return {pool.pickContractModel(discipline)[0] for _ in range(2000)} - {None}

    before = {d: picks(d) for d in ("drift", "drag", "roadracing")}
    for values in before.values():
        assert not values.intersection(additions), "Unpatched pool contains fixture additions"
    original = list(config.getContractVehicleModels().values())
    extension = runtime.execute(LUA_EXTENSION)
    extension.onUpdate(0.5)
    after = {d: picks(d) for d in before}
    for discipline in ("drift", "drag"):
        assert set(additions) <= after[discipline], f"Missing additions in {discipline}"
    assert "infogen_test_race" in after["roadracing"]
    assert "infogen_test_factory" not in after["roadracing"], "Race whitelist was bypassed"
    assert all("infogen_test_trailer" not in values for values in after.values())
    assert list(config.getConfig().contractVehicleModels.values()) == original, "Base config mutated"
    lua[inventory] = to_lua({
        "getVehicles": lambda: to_lua({1: {"model": "infogen_test_factory"}})
    })
    assert pool.isModelAllowedForDiscipline("roadracing", "infogen_test_factory"), "Owned exemption changed"
    lua[inventory] = to_lua({"getVehicles": lambda: to_lua({})})
    extension.onExtensionUnloaded()
    assert list(config.getContractVehicleModels().values()) == original, "Unload did not restore base"
    restored = {d: picks(d) for d in before}
    assert restored == before, "Pool not restored after unloading"
    # The real loader's reload path must remain effective through our wrapper.
    extension.onUpdate(0.5)
    saved_raw = copy.deepcopy(raw)
    raw["contractVehicleModels"] = []
    config.reload()
    assert not list(config.getContractVehicleModels().values()), "Empty fallback narrowed"
    raw.clear()
    raw.update(saved_raw)
    config.reload()
    for discipline in raw.get("disciplines", []):
        if discipline.get("id") == "drift":
            discipline.setdefault("contracts", {})["vehicleBlacklist"] = ["infogen_test_race"]
    config.reload()
    assert "infogen_test_race" not in picks("drift"), "Discipline blacklist was bypassed"
    assert "infogen_test_race" in picks("drag"), "Blacklist leaked into other disciplines"
    return {"rlsArchive": Path(rls_path).name,
            "layout": layout.name,
            "vehiclePoolSha256": hashlib.sha256(pool_bytes).hexdigest(),
            "checks": "Lua 5.1, 2000 seeded picks per discipline before/after/unload; no game launch",
            "stockConfigTypes": stock,
            "poolSizes": {d: {"before": len(before[d]), "after": len(after[d])} for d in before},
            "passed": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rls", required=True, type=Path)
    parser.add_argument("--vehicles", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.rls, args.vehicles), indent=2))
