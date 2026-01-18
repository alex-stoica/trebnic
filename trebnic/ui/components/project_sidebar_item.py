import flet as ft

from config import COLORS, FONT_SIZE_LG, FONT_SIZE_XL, SPACING_LG, BORDER_RADIUS_SM, SIDEBAR_ITEM_PADDING_LEFT, PADDING_LG 
from models.entities import Project 
from ui.controller import UIController


class ProjectSidebarItem(ft.Container):
    def __init__(self, project: Project, ctrl: UIController) -> None: 
        self.project = project
        self.ctrl = ctrl
        super().__init__(
            content=ft.Row(
                [ 
                    ft.Text(project.icon, size=FONT_SIZE_XL), 
                    ft.Text(project.name, size=FONT_SIZE_LG), 
                ], 
                spacing=SPACING_LG, 
            ), 
            padding=ft.padding.only(left=SIDEBAR_ITEM_PADDING_LEFT, top=PADDING_LG, bottom=PADDING_LG, right=PADDING_LG), 
            border_radius=BORDER_RADIUS_SM, 
            data=project.id, 
            on_click=self._on_click, 
        ) 

    def _on_click(self, e: ft.ControlEvent) -> None: 
        self.ctrl.toggle_project(self.project.id) 

    def update_content(self, project: Project) -> None: 
        self.project = project
        self.content = ft.Row(
            [ 
                ft.Text(project.icon, size=FONT_SIZE_XL), 
                ft.Text(project.name, size=FONT_SIZE_LG), 
            ], 
            spacing=SPACING_LG, 
        ) 

    def set_selected(self, selected: bool) -> None: 
        self.bgcolor = COLORS["accent"] if selected else None