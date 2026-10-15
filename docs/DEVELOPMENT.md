# Development

## Run From Source

Install Python 3.10 or newer, then:

```powershell
python -m pip install -r requirements.txt
python main.py
```

To select a directory at startup:

```powershell
python main.py --mods-path "C:/path/to/mods"
```

## Checks

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m ruff check --select F,E9 .
python main.py --smoke-test
```

Tests use temporary fixtures and do not modify installed mods. The smoke test
initializes the UI, renders icons, About, and RLS Contracts, and checks temporary ZIP/JSON
roundtrips. It does not scan or write your installed mods.

Lupa is a development-only dependency for executing the addon's Lua 5.1
lifecycle tests; it is not required to run the application. Optional verification
against your own RLS archive is documented in [RLS Contracts](RLS_CONTRACTS.md#verification).

## Windows Packages

```powershell
python build_windows.py
```

The default build produces the single-file EXE, portable ZIP, and SHA-256 file
in `dist`. For just the portable ZIP, use `python build_windows.py --portable`.
For a console-enabled diagnostic build, use `python build_windows.py --debug`.

The build script limits DLL and Qt plugin search paths to avoid collecting
unrelated libraries. Each package is smoke-tested. The portable runtime hook
redirects the application's settings and logs to its local `data` folder; it
does not modify the installed user's environment.

GitHub Actions tests Windows and Linux with Python 3.10 and 3.14. Tag builds
prepare a draft release. Manual builds upload artifacts without publishing a
release; `portable_only` limits a manual build to the portable package.

## Documentation Screenshots

Install Pillow, then capture a real library with:

```powershell
python -m pip install Pillow
python scripts/capture_readme.py --mods "C:/path/to/mods"
```

The script only scans mods. It uses temporary application settings, captures
the UI in memory, and blurs names, descriptions, and paths before writing the
images in `docs/images`. Inspect the final PNGs before publishing them.
