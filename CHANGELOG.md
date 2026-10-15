# Changelog

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
