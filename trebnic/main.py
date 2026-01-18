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
    ft.app(target=main) 