import flet as ft
from typing import Callable, Optional  

from config import (
    COLORS,
    FONT_SIZE_MD,
    ICON_SIZE_MD,
    ICON_SIZE_XL,
    PROJECT_ICONS,
    PROJECT_COLORS,
    DIALOG_WIDTH_SM,
    DIALOG_WIDTH_MD,
    ICON_PICKER_HEIGHT,
    COLOR_PICKER_HEIGHT, 
    ICON_GRID_RUNS_COUNT, 
    ICON_GRID_MAX_EXTENT, 
    ICON_GRID_SPACING, 
    FONT_SIZE_LG, 
    FONT_SIZE_3XL, 
    FONT_SIZE_5XL, 
    BORDER_RADIUS_MD, 
    SPACING_SM, 
    SPACING_MD, 
    SPACING_LG, 
    SPACING_XL, 
    SPACING_2XL, 
    PADDING_SM, 
    PADDING_MD, 
    PADDING_LG, 
    PADDING_XL, 
)  
from models.entities import AppState, Project 
from services.logic import TaskService  
from ui.helpers import accent_btn, danger_btn, SnackService
from ui.dialogs.base import open_dialog


class ProjectDialogs:
    def __init__(
        self, 
        page: ft.Page, 
        state: AppState, 
        service: TaskService, 
        snack: SnackService, 
        refresh: Callable[[], None], 
        rebuild_sidebar: Callable[[], None], 
    ) -> None: 
        self.page = page
        self.state = state
        self.service = service 
        self.snack = snack
        self.refresh = refresh
        self.rebuild_sidebar = rebuild_sidebar
        self._icon = PROJECT_ICONS[0]
        self._color = PROJECT_COLORS[0]["value"]
        self._dialog: Optional[ft.AlertDialog] = None 
        self._name_field = ft.TextField(
            hint_text="Project name", 
            border_color=COLORS["border"], 
            bgcolor=COLORS["input_bg"], 
            border_radius=BORDER_RADIUS_MD, 
            autofocus=True, 
        ) 
        self._error = ft.Text("", color=COLORS["danger"], size=FONT_SIZE_MD, visible=False) 
        self._icon_display = ft.Text(self._icon, size=FONT_SIZE_3XL) 
        self._color_display = ft.Container(
            width=FONT_SIZE_3XL, 
            height=FONT_SIZE_3XL, 
            border_radius=SPACING_LG, 
            bgcolor=self._color, 
        ) 

    def open(self, project: Optional[Project] = None) -> None: 
        if project:
            self.state.editing_project_id = project.id 
            self._name_field.value = project.name 
            self._icon = project.icon 
            self._color = project.color 
        else:
            self.state.editing_project_id = None
            self._name_field.value = ""
            self._icon = PROJECT_ICONS[0]
            self._color = PROJECT_COLORS[0]["value"]

        self._icon_display.value = self._icon
        self._color_display.bgcolor = self._color
        self._error.visible = False
        self._show_main()
        self.page.open(self._dialog)

    def _show_main(self) -> None: 
        icon_btn = ft.Container(
            content=ft.Row(
                [self._icon_display, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=FONT_SIZE_3XL)], 
                tight=True, 
            ), 
            padding=ft.padding.symmetric(horizontal=PADDING_LG, vertical=PADDING_SM), 
            border_radius=BORDER_RADIUS_MD, 
            bgcolor=COLORS["input_bg"],
            border=ft.border.all(1, COLORS["border"]),
            on_click=self._show_icon_picker,
            ink=True,
        ) 

        color_btn = ft.Container(
            content=ft.Row(
                [self._color_display, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=FONT_SIZE_3XL)], 
                spacing=SPACING_MD, 
                tight=True, 
            ), 
            padding=ft.padding.symmetric(horizontal=PADDING_LG, vertical=PADDING_SM), 
            border_radius=BORDER_RADIUS_MD, 
            bgcolor=COLORS["input_bg"],
            border=ft.border.all(1, COLORS["border"]),
            on_click=self._show_color_picker,
            ink=True,
        ) 

        content = ft.Column(
            [ 
                ft.Row( 
                    [ft.Text("Icon:", size=FONT_SIZE_LG, width=50), icon_btn], 
                    spacing=SPACING_LG, 
                ), 
                ft.Row( 
                    [ft.Text("Color:", size=FONT_SIZE_LG, width=50), color_btn], 
                    spacing=SPACING_LG, 
                ), 
                self._name_field, 
                self._error, 
            ], 
            spacing=SPACING_2XL, 
            tight=True,
        ) 

        title = "Edit Project" if self.state.editing_project_id else "Create New Project"
        actions = [ft.TextButton("Cancel", on_click=self._close)]

        if self.state.editing_project_id:
            actions.append(ft.TextButton(
                "Delete", 
                on_click=self._confirm_delete, 
                style=ft.ButtonStyle(color=COLORS["danger"]), 
            )) 

        actions.append(accent_btn(
            "Save" if self.state.editing_project_id else "Create", 
            self._save, 
        )) 

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Container(width=DIALOG_WIDTH_MD, content=content),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        ) 

    def _show_icon_picker(self, e: ft.ControlEvent) -> None: 
        temp = self._icon
        temp_display = ft.Text(temp, size=FONT_SIZE_5XL) 

        def on_tap(icon: str) -> None: 
            nonlocal temp
            temp = icon
            temp_display.value = icon
            for ctrl in grid.controls:
                ctrl.bgcolor = (
                    COLORS["accent"] if ctrl.data == icon else COLORS["card"] 
                ) 
            self.page.update()

        def confirm(e: ft.ControlEvent) -> None: 
            self._icon = temp
            self._icon_display.value = temp
            self._show_main()
            self.page.update()

        grid_controls = [] 
        for i in PROJECT_ICONS: 
            container = ft.Container(
                content=ft.Text(i, size=FONT_SIZE_3XL), 
                alignment=ft.alignment.center, 
                border_radius=BORDER_RADIUS_MD, 
                bgcolor=COLORS["accent"] if i == self._icon else COLORS["card"], 
                data=i, 
                on_click=lambda e, ic=i: on_tap(ic), 
                ink=True, 
            ) 
            grid_controls.append(container) 

        grid = ft.GridView(
            runs_count=ICON_GRID_RUNS_COUNT, 
            max_extent=ICON_GRID_MAX_EXTENT, 
            spacing=ICON_GRID_SPACING, 
            run_spacing=ICON_GRID_SPACING, 
            height=ICON_PICKER_HEIGHT, 
            controls=grid_controls, 
        ) 

        preview_container = ft.Container(
            content=temp_display, 
            alignment=ft.alignment.center, 
            bgcolor=COLORS["card"], 
            border_radius=SPACING_LG, 
            padding=PADDING_XL, 
            margin=ft.margin.only(bottom=SPACING_LG), 
        ) 

        self._dialog.title = ft.Text("Select icon")
        self._dialog.content = ft.Container(
            width=DIALOG_WIDTH_MD,
            height=375,
            content=ft.Column(
                [preview_container, grid], 
                tight=True, 
                scroll=ft.ScrollMode.AUTO, 
            ), 
        ) 
        self._dialog.actions = [
            ft.TextButton(
                "Back", 
                on_click=lambda e: self._show_main() or self.page.update(), 
            ), 
            accent_btn("Select", confirm),
        ] 
        self.page.update()

    def _show_color_picker(self, e: ft.ControlEvent) -> None: 
        temp = self._color

        def on_tap(cv: str) -> None: 
            nonlocal temp
            temp = cv
            for ctrl in color_list.controls:
                ctrl.content.controls[2].visible = ctrl.data == cv
            self.page.update()

        def confirm(e: ft.ControlEvent) -> None: 
            self._color = temp
            self._color_display.bgcolor = temp
            self._show_main()
            self.page.update()

        opts = [] 
        for c in PROJECT_COLORS: 
            color_circle = ft.Container(
                width=ICON_SIZE_XL, 
                height=ICON_SIZE_XL, 
                border_radius=SPACING_XL, 
                bgcolor=c["value"], 
            ) 
            check_icon = ft.Icon(
                ft.Icons.CHECK, 
                color=COLORS["accent"], 
                size=ICON_SIZE_MD, 
                visible=c["value"] == self._color, 
            ) 
            row = ft.Row(
                [ 
                    color_circle, 
                    ft.Text(c["name"], size=FONT_SIZE_LG, expand=True), 
                    check_icon, 
                ], 
                spacing=SPACING_XL, 
            ) 
            container = ft.Container(
                content=row, 
                padding=ft.padding.symmetric(vertical=PADDING_MD, horizontal=PADDING_XL), 
                border_radius=BORDER_RADIUS_MD, 
                ink=True, 
                data=c["value"], 
                on_click=lambda e, cv=c["value"]: on_tap(cv), 
            ) 
            opts.append(container) 

        color_list = ft.ListView(controls=opts, spacing=SPACING_SM, height=COLOR_PICKER_HEIGHT) 

        self._dialog.title = ft.Text("Select Color")
        self._dialog.content = ft.Container(width=DIALOG_WIDTH_SM, content=color_list)
        self._dialog.actions = [
            ft.TextButton(
                "Back", 
                on_click=lambda e: self._show_main() or self.page.update(), 
            ), 
            accent_btn("Select", confirm),
        ] 
        self.page.update()

    def _save(self, e: ft.ControlEvent) -> None: 
        name = self._name_field.value.strip()
        error = self.service.validate_project_name(name, self.state.editing_project_id)

        if error:
            self._error.value = error
            self._error.visible = True
            self.page.update()
            return

        if self.state.editing_project_id:
            for p in self.state.projects:
                if p.id == self.state.editing_project_id: 
                    p.name = name 
                    p.icon = self._icon 
                    p.color = self._color 
                    self.service.save_project(p) 
                    break
            msg = f"Project '{name}' updated"
        else:
            new_id = self.service.generate_project_id(name)
            new_p = Project( 
                id=new_id, 
                name=name, 
                icon=self._icon, 
                color=self._color, 
            ) 
            self.state.projects.append(new_p)
            self.service.save_project(new_p) 
            msg = f"Project '{name}' created"

        self._name_field.value = ""
        self._icon = PROJECT_ICONS[0]
        self._color = PROJECT_COLORS[0]["value"]
        self._icon_display.value = self._icon
        self._color_display.bgcolor = self._color
        self.state.editing_project_id = None
        self._error.visible = False
        self.page.close(self._dialog)
        self.snack.show(msg)
        self.rebuild_sidebar()
        self.refresh()
        self.page.update()

    def _confirm_delete(self, e: ft.ControlEvent) -> None: 
        project = self.state.get_project_by_id(self.state.editing_project_id)
        if not project:
            return

        def do_delete(e: ft.ControlEvent) -> None: 
            count = self.service.delete_project(project.id) 
            self.state.editing_project_id = None
            close()
            self.page.close(self._dialog)
            self.snack.show(
                f"Project '{project.name}' deleted ({count} tasks removed)", 
                COLORS["danger"], 
            ) 
            self.rebuild_sidebar()
            self.refresh()

        content = ft.Text(f"Delete '{project.name}' and all its tasks?") 
        _, close = open_dialog(
            self.page, 
            "Delete project", 
            content, 
            lambda c: [ 
                ft.TextButton("Cancel", on_click=c), 
                danger_btn("Delete", do_delete), 
            ], 
        ) 

    def _close(self, e: ft.ControlEvent) -> None: 
        self.state.editing_project_id = None
        self._error.visible = False
        self.page.close(self._dialog)