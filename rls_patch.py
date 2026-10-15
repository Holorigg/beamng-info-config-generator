"""A small, reversible addon; never rewrite RLS or vehicle archives."""
import json
import hashlib
import os
import re
import tempfile
import zipfile
from pathlib import Path

import json_utils
from rls_contracts import KNOWN_POOL_SHA256, MAX_METADATA_BYTES, POOL_PATH, PROGRESSION_PATH
from storage import backup_file

PATCH_NAME = "infogen_rls_contracts.zip"
MANIFEST = "settings/infogen_rls_contracts.json"
EXTENSION = "infogenRlsContracts"
OWNER = "Holorigg.BeamNGInfoConfigGenerator.RlsContracts"
MAX_PATCH_BYTES = 2 * 1024 * 1024

BOOTSTRAP = '''extensions.load("infogenRlsContracts")
setExtensionUnloadMode("infogenRlsContracts", "manual")
'''

LUA_EXTENSION = '''local M = {}
local tag = "infogenRlsContracts"
local manifestPath = "/settings/infogen_rls_contracts.json"
local modulePath = "gameplay/fre/config"
local config, original, wrapper
local elapsed = 0
local warned = false

local function detach()
  if config and config.getContractVehicleModels == wrapper then
    config.getContractVehicleModels = original
  end
  config, original, wrapper = nil, nil, nil
end

local function attach()
  if not FS:fileExists(manifestPath) then
    detach()
    return
  end
  if not FS:fileExists("/lua/ge/extensions/gameplay/fre/config.lua") then
    detach()
    return
  end
  local ok, current = pcall(require, modulePath)
  if not ok or type(current) ~= "table" then return end
  -- Do not wrap another addon's wrapper repeatedly on every update.
  if current == config then return end
  detach()
  if type(current.getContractVehicleModels) ~= "function" then
    if not warned then log("W", tag, "RLS contract model API is unavailable; addon inactive.") end
    warned = true
    return
  end
  local data = jsonReadFile(manifestPath)
  if type(data) ~= "table" or data.owner ~= "Holorigg.BeamNGInfoConfigGenerator.RlsContracts"
      or data.schema ~= 1 or type(data.models) ~= "table" then return end
  if data.verifiedRules ~= true and not warned then
    log("W", tag, "RLS version has not been verified; using compatible contract model API.")
    warned = true
  end
  config = current
  original = current.getContractVehicleModels
  local getBase = original
  wrapper = function(...)
    local base = getBase(...)
    -- An empty list means all known models in RLS, not no models.
    if type(base) ~= "table" or #base == 0 then return base end
    local out, seen = {}, {}
    for _, key in ipairs(base) do
      out[#out + 1] = key
      if type(key) == "string" then seen[string.lower(key)] = true end
    end
    for _, key in ipairs(data.models) do
      if type(key) == "string" and key ~= "" and not seen[string.lower(key)] then
        key = string.lower(key)
        seen[key] = true
        out[#out + 1] = key
      end
    end
    return out
  end
  current.getContractVehicleModels = wrapper
  log("I", tag, "Contract model additions active; RLS filters remain unchanged.")
end

-- Mod scripts run during mounting; defer require until the update loop.
M.onUpdate = function(dtReal)
  elapsed = elapsed + (dtReal or 0)
  if elapsed < 0.5 then return end
  elapsed = 0
  attach()
end
M.onExtensionUnloaded = detach
return M
'''


def _paths(mods_root):
    root = Path(mods_root)
    if not root.is_dir():
        raise ValueError("Select a valid mods directory")
    return root / PATCH_NAME, root / (PATCH_NAME + ".disabled")


def _model_keys(keys):
    result = set()
    for key in keys:
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", key):
            raise ValueError(f"Invalid vehicle model key: {key!r}")
        result.add(key.lower())
    if len(result) > 10000:
        raise ValueError("Too many vehicle models")
    return sorted(result)


def read_patch(mods_root):
    enabled, disabled = _paths(mods_root)
    present = [p for p in (enabled, disabled) if p.exists()]
    if len(present) > 1:
        raise ValueError("Both enabled and disabled contract patches exist; resolve the duplicate first")
    if not present:
        return None
    path = present[0]
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PATCH_BYTES:
        raise ValueError(f"Not a managed contract patch: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(MANIFEST)
            if info.file_size > MAX_PATCH_BYTES:
                raise ValueError("Contract patch manifest is too large")
            data = json.loads(archive.read(info))
        if not isinstance(data, dict) or data.get("owner") != OWNER or data.get("schema") != 1:
            raise ValueError("Unrecognized contract patch owner or schema")
        if not isinstance(data.get("models"), list):
            raise ValueError("Invalid contract patch model list")
        data["models"] = _model_keys(data["models"])
    except (KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        raise ValueError(f"Not a managed contract patch: {path}") from exc
    return {**data, "enabled": path == enabled, "path": str(path)}


def install_patch(mods_root, installation, model_keys):
    """Replace only our own addon, retaining a dated backup on every update."""
    enabled, disabled = _paths(mods_root)
    keys = _model_keys(model_keys)
    if not keys:
        raise ValueError("Select at least one vehicle model")
    source = Path(installation.path)
    members = ("lua/ge/extensions/gameplay/fre/config.lua", PROGRESSION_PATH, POOL_PATH)
    contents = {}
    if source.is_dir():
        for member in members:
            path = source / member
            if path.stat().st_size > MAX_METADATA_BYTES:
                raise ValueError("RLS metadata exceeds the 16 MiB limit")
            contents[member] = path.read_bytes()
    else:
        with zipfile.ZipFile(source) as archive:
            for member in members:
                info = archive.getinfo(member)
                if info.file_size > MAX_METADATA_BYTES:
                    raise ValueError("RLS metadata exceeds the 16 MiB limit")
                contents[member] = archive.read(info)
    json_utils.load_bytes(contents[PROGRESSION_PATH])
    if b"getContractVehicleModels" not in contents[members[0]]:
        raise ValueError("RLS contract model API is missing; this addon cannot connect to it")
    old = read_patch(mods_root)  # Refuse collisions with unrelated files.
    # Keep an intentionally disabled addon disabled while updating its selection.
    target = disabled if old and not old["enabled"] else enabled
    pool_hash = hashlib.sha256(contents[POOL_PATH]).hexdigest()
    data = {"owner": OWNER, "schema": 1, "models": keys,
            "rlsVersion": installation.version, "rlsPoolHash": pool_hash,
            "verifiedRules": installation.supported and pool_hash == KNOWN_POOL_SHA256}
    fd, temporary = tempfile.mkstemp(prefix=".infogen-contracts-", suffix=".tmp", dir=target.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST, json.dumps(data, indent=2) + "\n")
            archive.writestr("scripts/infogenRlsContracts/modScript.lua", BOOTSTRAP)
            archive.writestr(f"lua/ge/extensions/{EXTENSION}.lua", LUA_EXTENSION)
        with open(temporary, "r+b") as stream:
            os.fsync(stream.fileno())
        backup_file(target)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def set_patch_enabled(mods_root, enabled):
    active_path, inactive_path = _paths(mods_root)
    current = read_patch(mods_root)
    if current is None:
        raise ValueError("No managed contract patch is installed")
    target = active_path if enabled else inactive_path
    source = Path(current["path"])
    if source != target:
        backup_file(source)
        os.replace(source, target)
    return target
