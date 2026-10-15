"""
BeamNG Info Config Generator
Run: python main.py
     python main.py --mods-path "C:/path/to/mods"
"""
import sys
import argparse
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import tempfile


def smoke_check():
    import json_utils
    from scanner import scan_mods_folder
    from zip_handler import write_many_to_zip
    with tempfile.TemporaryDirectory(prefix="beamng-smoke-") as directory:
        root = Path(directory)
        archive = root / "fixture.zip"
        write_many_to_zip(archive, {"vehicles/car/base.pc": '{parts: {engine: "engine_diesel"}}'})
        data = '{Configuration: "Base", "Config Type": "Factory", Drivetrain: "RWD", ' \
               'Transmission: "Manual", "Fuel Type": "Diesel", Value: 10000,}'
        for mode in ("auto", "disk", "ram"):
            write_many_to_zip(archive, {"vehicles/car/info_base.json": data}, mode=mode)
            entries = scan_mods_folder(str(root))
            entry = next(e for group in entries.values() for e in group)
            if entry.status != "ok" or entry.info_content != json_utils.loads(data):
                raise RuntimeError(f"Packaged file roundtrip failed in {mode} mode")


def smoke_check_ui(window):
    from about import AboutDialog
    from ui_icons import app_icon, icon, resource_path
    from PySide6.QtGui import QIcon
    if app_icon().pixmap(32, 32).isNull():
        raise RuntimeError("Packaged application icon could not be rendered")
    for path in resource_path("icons", "lucide").glob("*.svg"):
        for mode in (QIcon.Normal, QIcon.Disabled):
            if icon(path.stem).pixmap(24, 24, mode).isNull():
                raise RuntimeError(f"Packaged icon could not be rendered: {path.stem}")
    dialog = AboutDialog(window)
    dialog.show()
    dialog.close()
    from rls_dialog import ContractsDialog
    with tempfile.TemporaryDirectory(prefix="beamng-contracts-smoke-") as directory:
        contracts = ContractsDialog(directory, [], parent=window)
        contracts.show()
        contracts.close()


def main():
    parser = argparse.ArgumentParser(description="BeamNG Info Config Generator")
    parser.add_argument("--mods-path", metavar="PATH",
                        help="Mods folder to scan on startup")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Initialize the UI and exit without scanning or writing mods")
    args = parser.parse_args()
    log_path = Path.home() / ".beamng_infogen.log"
    try:
        handler = RotatingFileHandler(log_path, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
        logging.basicConfig(level=logging.WARNING, handlers=[handler],
                            format="%(asctime)s %(levelname)s %(message)s")
    except OSError:
        logging.basicConfig(handlers=[logging.NullHandler()])
    try:
        from PySide6.QtWidgets import QApplication
        from app import App, make_dark_style
    except ImportError:
        logging.exception("Application dependencies could not be loaded")
        if args.smoke_test:
            sys.exit(1)
        raise
    if args.smoke_test:
        args.mods_path = None

    app = QApplication(sys.argv)
    from about import APP_NAME, APP_AUTHOR, APP_VERSION
    from ui_icons import app_icon
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_AUTHOR)
    app.setWindowIcon(app_icon())
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Holorigg.BeamNGInfoConfigGenerator")
    app.setStyle("Fusion")
    app.setStyleSheet(make_dark_style())
    fatal_errors = []
    def report_error(exc_type, exc_value, exc_traceback):
        fatal_errors.append(str(exc_value))
        logging.error("Unhandled application error", exc_info=(exc_type, exc_value, exc_traceback))
        from PySide6.QtWidgets import QMessageBox
        if not args.smoke_test:
            QMessageBox.critical(None, "Application error", f"{exc_value}\n\nDetails: {log_path}")
    sys.excepthook = report_error

    window = App(mods_path=args.mods_path)
    if args.smoke_test:
        app.processEvents()
        smoke_check()
        smoke_check_ui(window)
        if fatal_errors:
            sys.exit(1)
        return
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
