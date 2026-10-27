"""Measure configurations in the real game, in a temporary user folder.

The game runs with -userpath pointing at a throwaway folder that contains only a
small measuring addon and the mods being measured (hard links or junctions, never
copies that could drift). The addon spawns each configuration on a small level,
reads values from the vehicle's own powertrain and physics, writes a result file
and quits. Installed mods, settings and saves are never opened for writing.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from storage import OperationCancelled

ADDON_NAME = "infogen_measure.zip"
JOB_PATH = "settings/infogen_measure_job.json"
RESULT_NAME = "infogen_measure_result.json"
LEVEL = "levels/smallgrid/main.level.json"
EXE = Path("Bin64") / "BeamNG.drive.x64.exe"

MOD_SCRIPT = '''-- Deferred so the mod manager's temporary extensions.load wrapper is gone.
core_jobsystem.create(function(job)
  job.sleep(0.5)
  setExtensionUnloadMode("infogenMeasure", "manual")
  extensions.load("infogenMeasure")
end)
'''

# Original code by Holorigg (MIT); it only calls public game and vehicle APIs.
GE_EXTENSION = r'''-- Measures the configurations listed in a job file, then quits the game.
local M = {}
local tag = "infogenMeasure"
local jobPath = "/settings/infogen_measure_job.json"
local resultPath = "/settings/infogen_measure_result.json"
local results = {}
local pending = nil
local levelReady = false
local started = false

-- Runs in the vehicle VM and reports one table back.
local vehicleProbe = [[
local function band(curve, peak, maxRPM)
  if type(curve) ~= "table" or not peak or peak <= 0 then return nil end
  local best, low, high = 0, nil, nil
  for rpm = 0, maxRPM do
    local v = curve[rpm]
    if v and v > best then best = v end
  end
  if best <= 0 then return nil end
  for rpm = 0, maxRPM do
    local v = curve[rpm]
    if v and v >= best * 0.98 then
      low = low or rpm
      high = rpm
    end
  end
  return {low, high}
end

local function probe(id)
  local r = {id = id}
  local ok, err = pcall(function()
    r.weight = obj:calcBeamStats().total_weight
    local power, torque, electric = 0, 0, false
    for _, e in ipairs(powertrain.getDevicesByCategory("engine") or {}) do
      if e.type == "electricMotor" then electric = true end
      if e.getTorqueData then
        local td = e:getTorqueData()
        power = power + (td.maxPower or 0)
        torque = torque + (td.maxTorque or 0)
        if not r.powerBand then
          local curves = td.curves and td.curves[td.finalCurveName]
          r.powerBand = curves and band(curves.power, td.maxPower, td.maxRPM or 0)
          r.torqueBand = curves and band(curves.torque, td.maxTorque, td.maxRPM or 0)
          r.powerRPM, r.torqueRPM = td.maxPowerRPM, td.maxTorqueRPM
        end
      end
    end
    r.power, r.torque, r.electric = power, torque, electric
    local turbo, sc, n2o = false, false, false
    for _, e in ipairs(powertrain.getDevicesByType("combustionEngine") or {}) do
      turbo = turbo or (e.turbocharger and e.turbocharger.isExisting) or false
      sc = sc or (e.supercharger and e.supercharger.isExisting) or false
      n2o = n2o or (e.nitrousOxideInjection and e.nitrousOxideInjection.isExisting) or false
    end
    r.turbo, r.supercharger, r.nitrous = turbo, sc, n2o
    r.gearboxes = {}
    for _, g in ipairs(powertrain.getDevicesByCategory("gearbox") or {}) do
      table.insert(r.gearboxes, g.type)
    end
    r.storages = {}
    for _, s in pairs(energyStorage.getStorages() or {}) do
      table.insert(r.storages, {type = s.type, energy = s.energyType})
    end
    if extensions.dynamicVehicleData == nil then extensions.load("dynamicVehicleData") end
    if dynamicVehicleData and dynamicVehicleData.getPowertrainLayout then
      r.layout = dynamicVehicleData.getPowertrainLayout()
    end
  end)
  if not ok then r.error = tostring(err) end
  obj:queueGameEngineLua("infogenMeasure.report(" .. serialize(r) .. ")")
end
]]

M.report = function(data)
  if pending and type(data) == "table" and data.id == pending.id then
    pending.result = data
  end
end

local function save(done)
  jsonWriteFile(resultPath, {done = done, results = results}, true)
end

local function work(job)
  while not (core_modmanager and core_modmanager.isReady and core_modmanager.isReady()) do job.sleep(0.5) end
  local task = jsonReadFile(jobPath)
  if type(task) ~= "table" or type(task.configs) ~= "table" then
    log("E", tag, "No measuring job")
    jsonWriteFile(resultPath, {done = true, error = "no job", results = {}}, true)
    shutdown(1)
    return
  end
  core_levels.startLevel(task.level)
  while not levelReady do job.sleep(0.5) end
  job.sleep(2)
  save(false)
  for index, item in ipairs(task.configs) do
    local entry = {model = item.model, config = item.config}
    local ok, err = pcall(function() core_vehicles.replaceVehicle(item.model, {config = item.config}) end)
    if not ok then
      entry.error = "spawn: " .. tostring(err)
    else
      job.sleep(task.settle or 3)
      local veh = getPlayerVehicle(0)
      if not veh then
        entry.error = "no vehicle"
      else
        entry.spawned = veh.partConfig
        pending = {id = index}
        veh:queueLuaCommand(vehicleProbe .. " probe(" .. index .. ")")
        local waited = 0
        while not pending.result and waited < 20 do
          job.sleep(0.25)
          waited = waited + 0.25
        end
        entry.data = pending.result
        if not entry.data then entry.error = "timeout" end
        pending = nil
      end
    end
    results[#results + 1] = entry
    save(false)
  end
  save(true)
  job.sleep(1)
  shutdown(0)
end

M.onClientStartMission = function()
  levelReady = true
end

M.onExtensionLoaded = function()
  if started then return end
  started = true
  extensions.core_jobsystem.create(work)
end

return M
'''


@dataclass
class Session:
    root: Path
    user: Path
    configs: list
    process: object = None
    linked: list = field(default_factory=list)

    @property
    def result_path(self):
        return self.user / "current" / "settings" / RESULT_NAME


def config_key(entry) -> tuple[str, str] | None:
    """Return (model, config) as the game names them, from a scanner entry."""
    parts = PurePosixPath(str(entry.pc_path).replace("\\", "/")).parts
    # The game only loads configurations at vehicles/<model>/<config>.pc.
    if len(parts) >= 3 and parts[-3].casefold() == "vehicles":
        return parts[-2], PurePosixPath(parts[-1]).stem
    return None


def game_executable(game_dir) -> Path:
    return Path(game_dir) / EXE


def _link_file(source: Path, target: Path):
    try:
        os.link(source, target)
    except OSError:
        # Different volume or no hard-link support: a copy is still read-only for the game.
        shutil.copy2(source, target)


def _link_folder(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(source), str(target))
    else:
        os.symlink(source, target, target_is_directory=True)


def build_addon(path: Path, job: dict):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("scripts/infogen_measure/modScript.lua", MOD_SCRIPT)
        archive.writestr("lua/ge/extensions/infogenMeasure.lua", GE_EXTENSION)
        archive.writestr(JOB_PATH, json.dumps(job, indent=2))


def prepare(entries, settle=3, base_dir=None) -> Session:
    """Create the temporary user folder with the addon and the measured mods."""
    configs, sources = [], {}
    for entry in entries:
        key = config_key(entry)
        if key is None:
            continue
        configs.append({"model": key[0], "config": key[1]})
        sources[os.path.normcase(str(entry.source_path))] = entry
    if not configs:
        raise ValueError("No measurable configurations selected")
    root = Path(tempfile.mkdtemp(prefix="beamng-infogen-measure-", dir=base_dir))
    user = root / "user"
    mods = user / "current" / "mods"
    mods.mkdir(parents=True)
    session = Session(root, user, configs)
    build_addon(mods / ADDON_NAME, {"level": LEVEL, "settle": settle, "configs": configs})
    used = {ADDON_NAME.casefold()}
    for entry in sources.values():
        source = Path(entry.source_path)
        name = source.name
        stem, suffix = os.path.splitext(name)
        counter = 1
        while name.casefold() in used:
            counter += 1
            name = f"{stem}_{counter}{suffix}"
        used.add(name.casefold())
        if entry.source == "zip":
            _link_file(source, mods / name)
        else:
            _link_folder(source, mods / "unpacked" / name)
        session.linked.append(str(source))
    return session


def launch(session: Session, game_dir) -> subprocess.Popen:
    exe = game_executable(game_dir)
    if not exe.is_file():
        raise FileNotFoundError(f"Game executable not found: {exe}")
    session.process = subprocess.Popen(
        [str(exe), "-userpath", str(session.user), "-nosteam"], cwd=str(game_dir))
    return session.process


def read_results(session: Session) -> dict:
    try:
        return json.loads(session.result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def wait(session: Session, cancel=None, progress=None, timeout=None, poll=1.0):
    """Wait for the game to finish; returns the result document."""
    total = len(session.configs)
    timeout = timeout or 180 + 60 * total
    started = time.monotonic()
    try:
        while True:
            if cancel is not None and cancel.is_set():
                raise OperationCancelled()
            data = read_results(session)
            done = len(data.get("results", []))
            if progress:
                progress(done, total, f"{done} / {total}")
            if data.get("done"):
                return data
            if session.process is not None and session.process.poll() is not None:
                return data
            if time.monotonic() - started > timeout:
                raise TimeoutError("The game did not finish measuring in time")
            time.sleep(poll)
    finally:
        stop(session)


def stop(session: Session):
    process = session.process
    if process is not None and process.poll() is None:
        process.kill()
        try:
            process.wait(10)
        except subprocess.TimeoutExpired:
            pass


def cleanup(session: Session):
    """Remove the temporary folder; junctions are removed without touching their targets."""
    stop(session)
    unpacked = session.user / "current" / "mods" / "unpacked"
    if unpacked.is_dir():
        for item in unpacked.iterdir():
            try:
                if os.path.islink(item):
                    os.unlink(item)
                else:
                    os.rmdir(item)  # Removes a junction itself; fails on a real folder.
            except OSError:
                # Never risk deleting through a link to the user's mod.
                return False
    # The game's browser helper can hold a log file for a moment after the game exits.
    for _ in range(20):
        shutil.rmtree(session.root, ignore_errors=True)
        if not session.root.exists():
            break
        time.sleep(0.5)
    return True


def _rpm_text(band, peak):
    if isinstance(band, list) and len(band) == 2 and band[0] is not None:
        low = int(math.ceil(band[0] / 50.0) * 50)
        high = int(math.floor(band[1] / 50.0) * 50)
        if band[1] - band[0] >= 500 and high > low:
            return f"{low} - {high}"
        return low
    if isinstance(peak, (int, float)) and peak > 0:
        return int(round(peak / 50.0) * 50)
    return None


TRANSMISSIONS = {"automaticGearbox": "Automatic", "manualGearbox": "Manual", "dctGearbox": "DCT",
                 "cvtGearbox": "CVT", "sequentialGearbox": "Sequential"}


def to_info(data: dict) -> dict:
    """Translate a probe result into info file fields, rounded like the game's stock files."""
    info = {}
    weight = data.get("weight")
    if isinstance(weight, (int, float)) and weight > 0:
        info["Weight"] = int(math.ceil(weight / 5.0) * 5)
    power, torque = data.get("power"), data.get("torque")
    if isinstance(power, (int, float)) and power > 0:
        info["Power"] = int(math.floor(power))
        rpm = _rpm_text(data.get("powerBand"), data.get("powerRPM"))
        if rpm is not None:
            info["PowerPeakRPM"] = rpm
        if "Weight" in info:
            info["Weight/Power"] = round(info["Weight"] / info["Power"], 3)
    if isinstance(torque, (int, float)) and torque > 0:
        info["Torque"] = int(math.ceil(torque / 5.0) * 5)
        rpm = _rpm_text(data.get("torqueBand"), data.get("torqueRPM"))
        if rpm is not None:
            info["TorquePeakRPM"] = rpm
    layout = data.get("layout")
    if isinstance(layout, str) and layout and layout != "Other":
        info["Drivetrain"] = layout
    gearboxes = [g for g in data.get("gearboxes") or [] if isinstance(g, str) and "range" not in g.casefold()]
    if gearboxes:
        info["Transmission"] = TRANSMISSIONS.get(gearboxes[0], "Other")
    storages = [s for s in data.get("storages") or [] if isinstance(s, dict) and s.get("type") != "n2oTank"]
    energies = {(s.get("type"), s.get("energy")) for s in storages}
    if any(kind == "fuelTank" and energy == "diesel" for kind, energy in energies):
        info["Fuel Type"] = "Diesel"
    elif any(kind == "fuelTank" and energy == "gasoline" for kind, energy in energies):
        info["Fuel Type"] = "Gasoline"
    elif storages and all(kind == "electricBattery" for kind, _ in energies):
        info["Fuel Type"] = "Battery"
    elif storages:
        info["Fuel Type"] = "Other"
    if data.get("electric") or info.get("Fuel Type") == "Battery":
        info["Propulsion"] = "Electric"
    elif power:
        info["Propulsion"] = "ICE"
    if power and not data.get("electric"):
        base = "Turbo" if data.get("turbo") else "SC" if data.get("supercharger") else "NA"
        info["Induction Type"] = base + (" + N2O" if data.get("nitrous") and base != "NA" else "")
    return info


def match_results(entries, document: dict) -> tuple[dict, list]:
    """Map results back to entries by (model, config); returns ({id: info}, errors)."""
    by_key = {}
    for item in document.get("results", []):
        if isinstance(item, dict):
            by_key[(str(item.get("model")).casefold(), str(item.get("config")).casefold())] = item
    measured, errors = {}, []
    for entry in entries:
        key = config_key(entry)
        item = by_key.get((key[0].casefold(), key[1].casefold())) if key else None
        if item is None:
            errors.append(f"{entry.config_name}: not measured")
        elif item.get("error") or not isinstance(item.get("data"), dict) or item["data"].get("error"):
            errors.append(f"{entry.config_name}: {item.get('error') or (item.get('data') or {}).get('error')}")
        else:
            info = to_info(item["data"])
            if info:
                measured[id(entry)] = info
            else:
                errors.append(f"{entry.config_name}: no data")
    return measured, errors
