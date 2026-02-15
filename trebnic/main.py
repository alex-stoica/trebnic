"""Entry point for Trebnic - starts the Flet application.

Run with: python main.py (desktop) or flet run main.py (with hot reload).
Sets up sys.path and delegates to app.create_app() which builds the full UI.
"""
import sys
import os
import shutil
import subprocess

_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)


def _fix_flat_extraction(app_dir: str) -> None:
    """Fix broken zip extraction that creates flat files with backslash names.

    archive 4.0.7 (used by serious_python) has a bug where extracting zip files
    on Android creates flat files like 'services\\auth.py' instead of proper
    subdirectories. This detects the flat structure and recreates the correct
    directory layout.
    """
    entries = os.listdir(app_dir)
    needs_fix = any("\\" in e for e in entries)
    if not needs_fix:
        return

    subprocess.run(["log", "-t", "TREBNIC", "Fixing flat extraction (backslash filenames)"])

    for entry in entries:
        if "\\" not in entry:
            continue
        parts = entry.split("\\")
        target_dir = os.path.join(app_dir, *parts[:-1])
        os.makedirs(target_dir, exist_ok=True)
        src = os.path.join(app_dir, entry)
        dst = os.path.join(target_dir, parts[-1])
        shutil.move(src, dst)


if os.environ.get("FLET_PLATFORM") == "android":
    _fix_flat_extraction(_app_dir)

import flet as ft

from app import create_app


def _android_log(msg: str) -> None:
    """Log to Android logcat via subprocess."""
    subprocess.run(["log", "-t", "TREBNIC", msg[:1000]])


def main(page: ft.Page) -> None:
    """Main entry point for the Trebnic application."""
    if os.environ.get("FLET_PLATFORM") == "android":
        import logging
        import traceback

        class LogcatHandler(logging.Handler):
            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    subprocess.run(["log", "-t", "TREBNIC_PY", self.format(record)[:1000]])

        logging.root.addHandler(LogcatHandler())
        logging.root.setLevel(logging.WARNING)

        # Install global exception hook to log unhandled errors to logcat
        _original_excepthook = sys.excepthook

        def _logcat_excepthook(exc_type, exc_value, exc_tb):
            msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            _android_log(f"UNHANDLED: {msg[:900]}")
            _original_excepthook(exc_type, exc_value, exc_tb)

        sys.excepthook = _logcat_excepthook

    create_app(page)


if __name__ == "__main__":
    ft.run(main)
