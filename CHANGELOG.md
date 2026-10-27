# Changelog

## v1.4.0 - 2026-10-27

- **Measure in game** starts BeamNG.drive with a temporary user folder, spawns the selected configurations, and reads power, torque, peak RPM, weight, drivetrain, transmission, fuel, and induction from the vehicle itself. Results open in the write preview. Installed mods, settings, and saves are not changed.

## v1.3.0 - 2026-10-27

### Added

- RLS Contracts supports RLS Career Overhaul 2.8 (BeamNG 0.40), which moved its contract files to a new `overhaul` layout. RLS 2.7 installations keep working unchanged; the addon detects which layout is installed.
- Editor fields for `InsuranceClass` (career insurance tier) and `Years`. Clearing them removes the keys.
- Analyze warns about values written by earlier versions that BeamNG 0.40 does not use, such as Induction `Natural`.
- Stock vehicle data: the game installation is found through Steam libraries, or chosen in Settings when it is not found. **From stock** fills the form with a stock model's typical price, power, torque, weight, years, body style, region, paint, and insurance class. Generation and Fix use the same data for mods based on stock models (can be turned off).
- Preview before bulk writes: Generate and Fix show every file and changed field, can be limited to the configurations shown by search and filters, and offer backups.
- Editor fields for `Region`, `Population`, and the default paint.
- Optional Russian interface in Settings. English remains the default.

### Changed

- Field choices follow BeamNG 0.40 stock vehicles: Induction `NA`/`Turbo`/`SC`/`Turbo + N2O`/`SC + N2O`, Fuel `Battery` for electric vehicles, plus the stock Config Type, Drivetrain, Transmission, and Body Style values. Choice fields accept custom values. Existing files are never rewritten silently.
- Redesigned interface: grouped Details form, status chips, neutral list with status icons, status badge, a vehicle-selector style Preview, and clearer RLS Contracts status cells.
- Compact form that reflows into one to three columns, an empty state with the detected mods folder, problem counts per mod, and notifications instead of status-bar text. A one-time notice suggests turning on backups.
- The main window was split into smaller modules (`widgets`, `dialogs`, `editor_form`, `vocabulary`).

## v1.2.0 - 2026-10-15

- Added RLS Contracts diagnostics grouped by vehicle model, with Drift, Drag, and Race eligibility checks.
- Added a separate switchable addon for selected contract-pool additions, with automatic backups and no edits to RLS, vehicle archives, or saves.
- Verified against RLS 2.7.2 files and its real selector in an isolated Lua 5.1 environment. No in-game testing; other versions remain available with a warning.

## v1.1.0 - 2026-10-15

### Added

- New SVG-based desktop workspace with search, status filters, tree and sortable table views, multi-selection, and Details, JSON, and Preview editors.
- Session operation history with exported JSON, cooperative cancellation, progress reporting, and actual write-success counts.
- Automatic, disk, and RAM ZIP write modes, plus optional dated backups.
- Scan support for ZIPs, extracted mods, common `repo`/`unpacked` containers, and a single extracted mod folder. Symlink/junction cycles in containers no longer cause repeated scanning. Thumbnails load when a configuration is selected.
- About dialog with Holorigg attribution, project and issue links, and bundled license notices; generated application icon.
- Windows executable build and smoke-test workflow, cross-platform tests, and rotating application error logs.

### Improved

- Form saves retain additional metadata such as display names, years, paints, statistics, and mod-specific fields; the JSON editor exposes the full document. Unsaved drafts are protected when changing configurations, rescanning, or closing.
- New metadata filenames follow the actual `.pc` stem, including names beginning with `config_`; existing filename variants remain readable and existing files are updated in place.
- JSON reading accepts JSON5 syntax, UTF-8 BOM, cp1251 fallback, and common missing commas between fields on different lines. Saves normalize content to standard JSON; comments and source formatting are not retained.
- Required-field validation rejects blank text and non-finite or non-positive prices. Optional decimal statistics are supported, and generated prices stay positive and within the requested range.
- Bulk repair skips malformed info files. Unreadable files are reported; atomic folder writes and temporary-file ZIP replacement reduce exposure to partial writes.
- ZIP entries are streamed during rebuilds, archive comments and entry metadata are retained, and automatic append can roll back its directory update after a caught error.
- Build environment isolation and packaged smoke checks reduce interference from unrelated DLLs and verify JSON/ZIP behavior without touching installed mods.

### Notes

- Vehicle-property detection from part names is heuristic. Performance figures are not measured or computed by the application.
- Automatic append rollback does not protect against power loss or forced termination. ZIP rebuilds require temporary disk space; RAM mode also holds the rebuilt compressed archive in memory and may not be faster.
- Passing the tool's metadata checks does not guarantee a dealership listing in-game.
