import flet as ft
from typing import Dict 

from config import COLORS
from ui.controller import UIController


class ProjectSidebarItem(ft.Container):
    def __init__(self, project: Dict[str, str], ctrl: UIController) -> None: 
        self.project = project
        self.ctrl = ctrl
        super().__init__(
            content=ft.Row(
                [ 
                    ft.Text(project["icon"], size=16), 
                    ft.Text(project["name"], size=14), 
                ], 
                spacing=10, 
            ), 
            padding=ft.padding.only(left=50, top=10, bottom=10, right=10),
            border_radius=5,
            data=project["id"],
            on_click=self._on_click, 
        ) 

    def _on_click(self, e: ft.ControlEvent) -> None: 
        self.ctrl.toggle_project(self.project["id"])

    def update_content(self, project: Dict[str, str]) -> None: 
        self.project = project
        self.content = ft.Row(
            [ 
                ft.Text(project["icon"], size=16), 
                ft.Text(project["name"], size=14), 
            ], 
            spacing=10, 
        ) 

    def set_selected(self, selected: bool) -> None: 
        self.bgcolor = COLORS["accent"] if selected else None