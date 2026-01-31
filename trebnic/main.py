"""Entry point for Trebnic - starts the Flet application.

Run with: python main.py (desktop) or flet run main.py (with hot reload).
Sets up sys.path and delegates to app.create_app() which builds the full UI.
"""
import sys
import os

_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import flet as ft

from app import create_app


def main(page: ft.Page) -> None:
    """Main entry point for the Trebnic application."""
    create_app(page)


if __name__ == "__main__":
    ft.run(main)
