"""Build in a controlled DLL search environment, then verify the executable."""

import argparse
import ast
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def build_environment():
    env = os.environ.copy()
    windows = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    python = Path(sys.executable).parent
    env["PATH"] = os.pathsep.join(str(p) for p in (
        python, python / "Scripts", windows / "System32", windows,
    ))
    for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH",
                "QT_QPA_PLATFORM"):
        env.pop(key, None)
    return env


def app_metadata(root):
    tree = ast.parse((root / "about.py").read_text(encoding="utf-8"))
    return {target.id: ast.literal_eval(node.value)
            for node in tree.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name)
            and target.id in ("APP_NAME", "APP_AUTHOR", "APP_VERSION")}


def version_file(root, name):
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable,
        VarFileInfo, VarStruct, VSVersionInfo,
    )
    metadata = app_metadata(root)
    version = metadata["APP_VERSION"]
    numbers = tuple(int(part) for part in version.split(".")) + (0,)
    details = {
        "CompanyName": metadata["APP_AUTHOR"],
        "FileDescription": metadata["APP_NAME"],
        "FileVersion": version,
        "InternalName": name,
        "OriginalFilename": f"{name}.exe",
        "ProductName": metadata["APP_NAME"],
        "ProductVersion": version,
    }
    resource = VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
        kids=[StringFileInfo([StringTable("040904B0", [StringStruct(k, v) for k, v in details.items()])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])],
    )
    output = root / "build" / "windows-version.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(str(resource), encoding="utf-8")
    return output


def merge_checksum(path, filename, digest):
    entries = {}
    if path.exists():
        for line in path.read_text(encoding="ascii").splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                entries[parts[1].lstrip("* ")] = parts[0]
    entries[filename] = digest
    path.write_text("".join(f"{value}  {name}\n" for name, value in entries.items()),
                    encoding="ascii")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_readme():
    return """BeamNG Info Config Generator

Extract the entire ZIP to a writable folder, then run beamng-infogen-portable.exe.
Keep the _internal folder beside it. No Python installation is required.
Select a folder containing BeamNG.drive ZIP or extracted mods to review and
edit vehicle configuration metadata. Back up important mods before saving.

This portable copy stores its settings and application log in the data folder
beside the executable. Keep that folder with the application. No installer is
required. Created by Holorigg.
"""


def package_portable(bundle, archive):
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(item for item in bundle.rglob("*") if item.is_dir()):
            output.writestr(path.relative_to(bundle.parent).as_posix() + "/", "")
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(bundle.parent).as_posix())


def build_portable(root, env, metadata_file):
    name = "beamng-infogen-portable"
    root_build = root / "build"
    dist = root / "dist"
    portable_dist = root_build / "portable-dist"
    portable_work = root_build / "portable-work"
    portable_spec = root_build / "portable-spec"
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        "--onedir", "--windowed", "--name", name,
        "--distpath", str(portable_dist), "--workpath", str(portable_work),
        "--specpath", str(portable_spec), "--icon", str(root / "icons" / "app.ico"),
        "--version-file", str(metadata_file),
        "--runtime-hook", str(root / "packaging" / "portable_hook.py"),
        "--hidden-import", "decimal", "--hidden-import", "pprint",
        "--add-data", f"{root / 'icons'};icons",
        "--add-data", f"{root / 'LICENSE'};.", str(root / "main.py"),
    ], cwd=root, env=env, check=True)

    built = portable_dist / name
    archive = dist / "beamng-infogen-portable.zip"
    dist.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="beamng-portable-", dir=root_build) as temporary:
        bundle = Path(temporary) / "BeamNG-Info-Config-Generator"
        shutil.copytree(built, bundle)
        (bundle / "data").mkdir()
        (bundle / "README.txt").write_text(portable_readme(), encoding="utf-8")
        shutil.copy2(root / "LICENSE", bundle / "LICENSE")

        with tempfile.TemporaryDirectory(prefix="beamng-portable-test-") as test_dir:
            extracted = Path(test_dir) / "extracted"
            extracted.mkdir()
            package_portable(bundle, archive)
            with zipfile.ZipFile(archive) as source:
                source.extractall(extracted)
            extracted_bundle = extracted / bundle.name
            executable = extracted_bundle / f"{name}.exe"
            subprocess.run([str(executable), "--smoke-test"], cwd=test_dir,
                           env=env, check=True, timeout=90)
            if not (extracted_bundle / "data" / ".beamng_infogen.log").is_file():
                raise RuntimeError("Portable smoke test did not create its data log")
            if any("mods_data" in item.parts or "fixture" in item.name.lower()
                   for item in extracted_bundle.rglob("*")):
                raise RuntimeError("Portable bundle unexpectedly includes mod fixtures")

    checksum_file = dist / "SHA256SUMS.txt"
    merge_checksum(checksum_file, archive.name, sha256(archive))
    print(f"Verified portable archive: {archive}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="Build a console/onedir diagnostic version")
    parser.add_argument("--portable", action="store_true", help="Build only the portable ZIP bundle")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows executable builds must run on Windows")
    root = Path(__file__).resolve().parent
    env = build_environment()
    if args.portable:
        metadata_file = version_file(root, "beamng-infogen-portable")
        build_portable(root, env, metadata_file)
        return

    name = "beamng-infogen-debug" if args.debug else "beamng-infogen"
    metadata_file = version_file(root, name)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        "--onedir" if args.debug else "--onefile",
        "--console" if args.debug else "--windowed", "--name", name,
        "--icon", "icons/app.ico",
        "--version-file", str(metadata_file),
        "--hidden-import", "decimal", "--hidden-import", "pprint",
        "--add-data", "icons;icons", "--add-data", "LICENSE;.", "main.py",
    ], cwd=root, env=env, check=True)
    executable = root / "dist" / name
    executable = executable / f"{name}.exe" if args.debug else executable.with_suffix(".exe")
    subprocess.run([str(executable), "--smoke-test"], cwd=root, env=env, check=True, timeout=60)
    if not args.debug:
        merge_checksum(root / "dist" / "SHA256SUMS.txt", executable.name, sha256(executable))
        metadata_file = version_file(root, "beamng-infogen-portable")
        build_portable(root, env, metadata_file)
    print(f"Verified executable: {executable}")


if __name__ == "__main__":
    main()
