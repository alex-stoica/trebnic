import flet as ft 

from config import COLORS 
from ui.controller import UIController 


class ProjectSidebarItem(ft.Container): 
    def __init__(self, project: dict, ctrl: UIController): 
        self.project = project 
        self.ctrl = ctrl 
        super().__init__( 
            content=ft.Row([ft.Text(project["icon"], size=16), ft.Text(project["name"], size=14)], spacing=10), 
            padding=ft.padding.only(left=50, top=10, bottom=10, right=10), border_radius=5, 
            data=project["id"], on_click=self._click) 

    def _click(self, e): 
        self.ctrl.toggle_project(self.project["id"]) 

    def update_content(self, project: dict): 
        self.project = project 
        self.content = ft.Row([ft.Text(project["icon"], size=16), ft.Text(project["name"], size=14)], spacing=10) 

    def set_selected(self, selected: bool): 
        self.bgcolor = COLORS["accent"] if selected else None 