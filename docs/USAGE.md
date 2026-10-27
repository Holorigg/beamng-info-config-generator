# Usage Notes

## Finding Mods

Select the directory containing your ZIP and extracted mods. The scanner also
looks inside common `repo` and `unpacked` containers. A single extracted mod
folder can be selected directly. Use the BeamNG launcher to locate your current
user folder rather than relying on a path from an older game version.

The application only writes metadata after you use a save, generate, or repair
action. Scanning and selecting configurations do not change mod files.

## Status And Actions

| Status | Meaning |
| --- | --- |
| Missing | No matching info file was found. |
| Incomplete | Required fields are invalid or missing, or the info file cannot be read. |
| Valid | The required metadata fields passed the tool's checks. |

The required fields are nonempty `Configuration`, `Config Type`, `Drivetrain`,
`Transmission`, and `Fuel Type` strings, plus a finite positive `Value`.
Valid does not mean the car has been tested in-game or is guaranteed to appear
at a dealership.

Search and status filters only change what is shown. **Generate missing** and
**Fix incomplete** apply to all loaded configurations unless you choose
**Only those shown by search and filters** in the preview that opens first.
**Generate selected** uses the current selection. Both tree and table views
support multi-selection. The preview lists each file, whether it is created or
updated, and which fields change, and can turn on backups.

Bulk repair skips unreadable info documents instead of silently replacing their
contents. Check History for scan issues and write errors.

## Metadata Files

New metadata follows the actual PC filename stem:

```text
vehicles/car/sport.pc       -> vehicles/car/info_sport.json
vehicles/car/config_race.pc -> vehicles/car/info_config_race.json
```

Existing naming alternatives remain readable and are updated at their current
paths. `Configuration` is the display name, not a requirement to match the PC
filename.

The reader accepts standard JSON, common JSON5 syntax, UTF-8 BOM, cp1251 text,
and some missing-comma errors between fields on different lines. Saving writes
standard JSON, so comments and original formatting are not retained.

Ordinary form saves merge edited values into the existing document. Fields
outside the form, such as years, paints, and mod-specific properties, are kept.
Explicit **Regenerate** replaces the full info document after confirmation.

Choice fields use the values found in BeamNG 0.40 stock vehicles, for example
Induction `NA`, `Turbo`, `SC` and Fuel `Battery` for electric vehicles. Custom
values can still be typed. Earlier versions of this editor wrote `Natural`,
`Supercharger`, and `Electric`; **Analyze** points these out, and they are
never rewritten silently. Clearing Insurance, Years, Region, or Paint removes
that key from the file.

## Stock Vehicle Data

The BeamNG.drive installation is found through Steam's library folders. If it
is not found, choose it in **Settings** or when **From stock** asks for it.
For a mod whose model key matches a stock vehicle (for example
`vehicles/etk800/...`), **From stock** fills the form with the model's years,
body style, region, paint, and insurance class, plus the median price, power,
torque, and weight of its factory configurations. Generation and Fix use the
same data when **Use stock vehicle data when generating** is on. The game files
are only read.

Drivetrain, transmission, and fuel detection from part names is heuristic.
The application does not simulate the car or calculate performance figures.
See BeamNG's [configuration guide](https://documentation.beamng.com/modding/vehicle/tutorials/configs/)
and [performance statistics discussion](https://beamng.com/threads/performance-statistics-feedback-thread.28306/).
The latter includes older launch commands; check them against your game version.

## File Handling And Safety

- **Automatic:** appends new files without reading unrelated archive payloads.
  Existing-file replacements use a disk rebuild.
- **Disk:** copies archive entries as streams to a temporary ZIP beside the
  original, then commits it by replacement.
- **RAM:** assembles the compressed output in memory, writes a temporary file
  beside the original, then commits it by replacement.

Both rebuild modes need free disk space for the replacement archive. RAM mode
also needs memory for the compressed output and may not be faster. Writes are
grouped by archive. Existing archive comments and entry metadata are preserved.

Automatic append saves the central-directory tail for rollback on caught write
errors. It cannot guarantee recovery from power loss, a killed process, or every
filesystem failure. Optional backups create dated `.bak` copies beside the
originals. A ZIP backup needs space for the complete original archive.

Folder JSON writes use a temporary file and replacement. Cancellation stops
later work and can abort a rebuild; already completed groups remain saved.
History reports actual completed writes, cancellations, and failures.

## Settings And Logs

The single-file EXE stores settings at `~/.beamng_infogen.json` and rotating
error logs at `~/.beamng_infogen.log`.

The portable ZIP keeps those files in `data` beside its executable. Extract the
entire portable folder to a writable location. To move it to another computer,
copy the whole folder; to reset its saved preferences, remove the settings file
inside `data` while the app is closed.

Do not copy an unredacted settings file or operation history into a public bug
report: it may contain local paths and mod names.
