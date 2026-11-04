# RLS Contracts

## Use

1. Scan the BeamNG mods directory containing RLS and your vehicle mods.
2. Optionally select configurations in the main editor, then open **RLS Contracts**. Multiple configurations of one model become one checkbox.
3. Review Drift, Drag, Race, config types, and metadata warnings. With multiple RLS installations, select the intended one; the tool cannot determine which duplicate BeamNG has enabled.
4. Select models and choose **Apply patch**. The confirmation shows the selection. Existing patched models absent from the scan are retained.
5. Restart BeamNG. New offers still follow RLS's unlocks, refresh cycle, random selection, and filters.

The checkbox selection replaces the models managed by this addon, not RLS's original list. Uncheck a scanned model and apply to remove that addition. The original RLS model list is always preserved. Updating a disabled addon leaves it disabled until **Enable patch** is used. A disabled addon's models are not counted as active in diagnostics.

## File Handling

The addon contains an original Lua extension, its mod bootstrap, and a small manifest of model keys. It wraps RLS's contract-model getter and returns a fresh list with additions. It does not overwrite RLS's progression configuration or ship copied RLS/game source. An empty original list retains RLS's all-known-models fallback.

The managed file is `mods/infogen_rls_contracts.zip`. Disabling renames it to `infogen_rls_contracts.zip.disabled`, outside BeamNG's ZIP discovery. Restart after changes; live unmounting or updating mods is not a reliable substitute. Removing this addon and restarting also restores ordinary RLS behavior.

Writes use a temporary file beside the addon followed by replacement. Updates and enable/disable changes create dated `.bak` copies regardless of the main editor's optional backup setting. Unrelated files occupying the managed filename are refused, not replaced. Backup creation must succeed before replacing an existing addon.

The RLS archive, vehicle archives, configuration info files, and career saves are not modified by these controls. Normal editor Save/Generate actions remain separate and can still edit vehicle metadata.

## Eligibility

These are file-based estimates of the random-offer pool, not a promise of a particular contract:

| Status | Meaning |
| --- | --- |
| In pool | The inspected settings and metadata permit this model in the random pool. BeamNG must still recognize it as an enabled, valid vehicle. |
| Not in pool | The configured pool does not contain the model. Applying the addon can add it. |
| Needs Race config | The Race whitelist is not satisfied by the inspected configuration types. Adding the model alone does not remove this filter. |
| Config type unverified | Required model metadata is missing, often because the mod extends a stock vehicle. Base-game metadata might supply the missing types. |
| Blacklisted | The discipline excludes this model. The addon deliberately does not bypass the blacklist. |
| Excluded model | Model metadata identifies a trailer, prop, or device. |

RLS 2.7.2 and 2.8.0 use model-level `Config Type` aggregates, not the selected configuration alone. Its stock Drift/Drag contracts have no type whitelist; random Road Racing contracts require `Race`. Owned models bypass this whitelist in the inspected version, but ownership and leaderboard state are not read by this application. Multiple mods defining the same model can also change the effective metadata through game mounting order.

Unknown RLS versions or changed rule-source hashes produce a warning and require confirmation, not a version lock. If the contract-model getter API or required files are absent, installation cannot proceed. A runtime API failure logs a warning instead of crashing the game.

## Verification

Checked without launching BeamNG against:

| RLS | Source | Layout | Vehicle-pool SHA-256 |
| --- | --- | --- | --- |
| 2.7.2 | Locally installed archive | `gameplay/fre`, `lua/ge/extensions/gameplay/...` | `3623b1f4d275c27e11fbd730ddd0ca013e38160692c3885ab38dd3e5f4b1cf31` |
| 2.8.0 | Public `v2.8.0` release archive | `gameplay/overhaul/fre`, `lua/ge/extensions/overhaul/...` | `40059b2ed44e32f44300cb8905eabd92fc47778f529b0607b108c0cbb0309dd4` |

RLS 2.8 moved its configuration module to `overhaul/events/freConfig` and renamed the inventory module, but its contract selection rules are the same as 2.7.2. The addon checks which module file exists and wraps that one, so one addon works with either version. A different hash produces a warning, not a block.

RLS 2.8.0 was also checked inside BeamNG.drive 0.40.4, in a temporary user folder with a started RLS career on West Coast. The addon stayed loaded across the level change. In the live modules, 300 selections per discipline included the added model for Drift and Drag and excluded it from Race because of the `Race` whitelist. Playing an actual contract was not tested. RLS 2.7.2 has not been checked in-game.

The verification script runs the installed RLS configuration loader and contract selector in an isolated Lua 5.1 VM. It checks 2,000 seeded selections per discipline before applying, after applying, and after unloading the addon. Checks cover additions, Race filtering, invalid trailers, owned-model exemption, unchanged base configuration, restoration, and empty-list fallback. Engine services are test doubles; this is not an in-game test.

Stock metadata examples inspected directly from the installed BeamNG content archives:

| Model | Race metadata examples |
| --- | --- |
| Moonhawk | `vehicles/moonhawk/info_race.json` |
| Pessima | `vehicles/pessima/info_race.json`, `info_hillclimb.json` |
| ETK 800 | `vehicles/etk800/info_844_track_M.json` |
| Hopper | `vehicles/hopper/info_race.json` |
| Scintilla | `vehicles/scintilla/info_race.json` |
| Barstow, Roamer | No Race configuration type found in the inspected stock archives; both still appear in RLS's common model list. |

To repeat the file-only check with your own installation:

```powershell
python -m pip install -r requirements-dev.txt
python scripts/verify_rls_files.py --rls "C:/path/to/rls_career_overhaul.zip" --vehicles "C:/path/to/BeamNG.drive/content/vehicles"
```

The script reads these archives without modifying them. Its generated test vehicle keys live only inside the isolated VM. No installed mods or saves are changed.

The addon follows BeamNG's documented [extension loading](https://documentation.beamng.com/modding/programming/extensions/) and [mod packaging](https://documentation.beamng.com/modding/mod-support/mod_packing/) conventions. RLS upstream: [RLS-Modding/rls_career_overhaul](https://github.com/RLS-Modding/rls_career_overhaul). The installed version's files, not the older public default branch, were the authority for these checks.
