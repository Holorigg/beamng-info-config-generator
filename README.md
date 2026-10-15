# BeamNG Info Config Generator

A Windows desktop editor for BeamNG.drive vehicle configuration metadata. Scan ZIP archives and extracted mods, create missing info files, repair incomplete metadata, and edit individual configs without extracting entire archives.

The app helps prepare metadata for systems such as RLS Career Overhaul. Passing its metadata checks does not guarantee an in-game dealership listing; that also depends on the installed game, mod version, and seller filters.

## Install

Download the Windows executable from [GitHub Releases](https://github.com/Holorigg/beamng-info-config-generator/releases). The standalone executable includes Python and the application dependencies.

To run from source, install Python 3.10 or newer, then in PowerShell:

```powershell
python -m pip install -r requirements.txt
python main.py
```

You can open a particular mods directory at startup:

```powershell
python main.py --mods-path "C:/Users/you/AppData/Local/BeamNG/BeamNG.drive/current/mods"
```

## Features

- Scan ZIP mods, extracted mod folders, and mods under common `repo` and `unpacked` containers. A single extracted mod folder can also be opened.
- Search configurations and filter by missing, incomplete, or valid metadata; switch between tree and sortable table views, with multi-selection.
- Edit details in a form or JSON editor, inspect a metadata preview, and copy form values from another configuration.
- Save edits while retaining existing fields the form does not edit, including display names, years, paints, statistics, and mod-specific properties. Unsaved edits are protected when switching configurations, rescanning, or closing.
- Generate missing info files, repair invalid required fields, regenerate a selected file after confirmation, or analyze metadata issues.
- Review session operation history, including errors and cancellations, and export it as JSON.

Search and status filters only affect browsing. **Generate missing** and **Fix incomplete** operate on all loaded configurations; only **Generate selected** is limited to the current selection.

Drivetrain, transmission, and fuel detection from part names is heuristic. Check inferred values when accuracy matters. The app does not run vehicle performance tests or calculate statistics from JBeam parts; enter power, torque, weight, acceleration, and braking values only when supported by measurements or known data.

## ZIP Writes And Backups

Choose a write mode and optional backup setting in **Settings**:

| Mode | New files | Replacements | Memory use |
| --- | --- | --- | --- |
| Automatic (default) | Append to archive | Rebuild on disk | Bounded buffers for archive copying |
| Disk | Rebuild on disk | Rebuild on disk | Bounded buffers for archive copying |
| RAM | Rebuild in memory | Rebuild in memory | Holds the rebuilt compressed archive in memory |

Writes to each archive are grouped. Disk and RAM rebuilds are assembled in a temporary file beside the original and committed by replacement. They require enough free disk space for the replacement archive; RAM mode additionally requires memory for the compressed output and is not necessarily faster. Large replacements can take time. Rebuilt archives preserve the archive comment and existing entry metadata; entries are streamed rather than loaded all at once.

Automatic append keeps the previous central-directory tail for rollback if a write raises a caught error. This is not protection against power loss, forced process termination, or every possible filesystem failure. **Back up before writes** makes dated `.bak` copies beside originals; a ZIP backup needs space for the complete original archive. Folder JSON writes use a temporary file and replacement. Cancellation stops later work and can abort an archive rebuild, but groups already completed remain saved. Check **History** for failures and actual success counts.

## Metadata And JSON

New info files use the actual `.pc` filename stem:

```text
vehicles/car/sport.pc       -> vehicles/car/info_sport.json
vehicles/car/config_race.pc -> vehicles/car/info_config_race.json
```

Existing naming alternatives remain readable, and existing files are updated at their current paths. `Configuration` is a display name and does not have to match the `.pc` filename.

The validity check requires nonempty `Configuration`, `Config Type`, `Drivetrain`, `Transmission`, and `Fuel Type` strings, plus a finite positive `Value`. The reader accepts standard JSON and common JSON5 syntax, UTF-8 BOM, and cp1251-encoded files. Saving writes standard JSON; comments and the original formatting are not retained.

The form merges its edited values into the existing document and retains additional fields. **Regenerate** deliberately replaces the full info document after confirmation. Bulk repair skips malformed info files so their raw contents are not silently overwritten.

See the [BeamNG configuration guide](https://documentation.beamng.com/modding/vehicle/tutorials/configs/) and [performance statistics discussion](https://beamng.com/threads/performance-statistics-feedback-thread.28306/) for metadata context. The discussion includes older launch instructions; verify them against your game version before use. More implementation references are in [docs/RESEARCH.md](docs/RESEARCH.md).

## Settings And About

The About dialog identifies the author as Holorigg and includes project, issue, and bundled license information. The application and window use a generated icon; interface icons are bundled Lucide SVGs and work offline. See [icons/lucide/SOURCE.md](icons/lucide/SOURCE.md) for icon attribution.

Window layout, view mode, last directory, and ZIP settings are stored in `~/.beamng_infogen.json`. Unexpected application errors are written to `~/.beamng_infogen.log` with log rotation.

| Shortcut | Action |
| --- | --- |
| Ctrl+S | Save the active draft |
| F5 | Rescan |

## Development And Windows Build

Run the tests and UI smoke test with:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python main.py --smoke-test
```

On Windows, build and smoke-test the standalone executable with:

```powershell
python build_windows.py
```

For a console-enabled diagnostic build, use `python build_windows.py --debug`. The build script limits the DLL and Qt plugin search environment to reduce accidental inclusion of unrelated libraries. Its smoke test initializes the packaged UI and checks temporary ZIP/JSON roundtrips; it does not write to installed mods.

GitHub Actions runs tests on Windows and Linux with Python 3.10 and 3.14. Pushing a `v*` tag runs the Windows build and release workflow; the workflow can also be run manually without publishing a release.
