"""Build in a controlled DLL search environment, then verify the executable."""

import argparse
import ast
import hashlib
import os
from pathlib import Path
import subprocess
import sys


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="Build a console/onedir diagnostic version")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows executable builds must run on Windows")
    root = Path(__file__).resolve().parent
    name = "beamng-infogen-debug" if args.debug else "beamng-infogen"
    env = build_environment()
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
        digest = hashlib.sha256()
        with executable.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        (root / "dist" / "SHA256SUMS.txt").write_text(f"{digest.hexdigest()}  {executable.name}\n", encoding="ascii")
    print(f"Verified executable: {executable}")


if __name__ == "__main__":
    main()
