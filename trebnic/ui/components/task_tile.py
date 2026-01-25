import flet as ft

from config import COLORS, BORDER_RADIUS
from models.entities import Task
from services.crypto import LOCKED_PLACEHOLDER
from ui.controller import UIController
from ui.presenters.task_presenter import TaskPresenter, TaskDisplayData
from ui.dialogs.base import create_option_item


class TaskTile:
    def __init__(
        self, 
        task: Task, 
        is_done: bool, 
        ctrl: UIController, 
    ) -> None: 
        self.task = task
        self.is_done = is_done
        self.ctrl = ctrl
        project = ctrl.get_project(task.project_id) 
        self.display = TaskPresenter.create_display_data(task, project) 

    def _on_check(self, e: ft.ControlEvent) -> None: 
        if self.is_done and not e.control.value:
            self.ctrl.uncomplete(self.task)
        elif not self.is_done and e.control.value:
            self.ctrl.complete(self.task)

    def _build_project_tag_content(self) -> ft.Control:
        """Build the project tag content, showing lock icon if project name is locked."""
        is_project_locked = self.display.project_name == LOCKED_PLACEHOLDER
        if is_project_locked:
            return ft.Row(
                [
                    ft.Icon(ft.Icons.LOCK, color=COLORS["white"], size=10),
                    ft.Text("Encrypted", size=10, color=COLORS["white"], italic=True),
                ],
                spacing=4,
                tight=True,
            )
        return ft.Row(
            [
                ft.Text(self.display.project_icon, size=10),
                ft.Text(self.display.project_name, size=10, color=COLORS["white"]),
            ],
            spacing=4,
            tight=True,
        )

    def _tags(self) -> ft.Control:
        is_project_locked = self.display.project_name == LOCKED_PLACEHOLDER
        if self.is_done:
            project_display = "Encrypted" if is_project_locked else (self.display.project_name or "Unassigned")
            parts = [project_display]
            if self.display.due_date_display:
                parts.append(self.display.due_date_display)
            content = ft.Row(
                [
                    ft.Icon(ft.Icons.LOCK, color=COLORS["done_text"], size=10) if is_project_locked else ft.Container(),
                    ft.Text(" - ".join(parts), size=10, color=COLORS["done_text"]),
                ],
                spacing=4,
                tight=True,
            ) if is_project_locked else ft.Text(" - ".join(parts), size=10, color=COLORS["done_text"])
            return ft.Container(
                content=content,
                bgcolor=COLORS["done_tag"],
                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                border_radius=5,
            )

        tags = []
        if self.display.project_name:
            project_tag = ft.Container(
                content=self._build_project_tag_content(),
                bgcolor=self.display.project_color,
                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                border_radius=5,
                on_click=lambda e: self.ctrl.assign_project(self.task),
                ink=True,
            )
            tags.append(project_tag)
        else:
            unassigned_tag = ft.Container(
                content=ft.Text( 
                    "Unassigned", 
                    size=10, 
                    color=COLORS["unassigned"], 
                ), 
                bgcolor=COLORS["input_bg"],
                border=ft.border.all(1, COLORS["border"]),
                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                border_radius=5,
                on_click=lambda e: self.ctrl.assign_project(self.task),
                ink=True,
            ) 
            tags.append(unassigned_tag)

        if self.display.due_date_display: 
            due_tag = ft.Container(
                content=ft.Text( 
                    self.display.due_date_display, 
                    size=10, 
                    color=COLORS["done_text"], 
                ), 
                bgcolor=COLORS["input_bg"],
                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                border_radius=5,
                on_click=lambda e: self.ctrl.date_picker(self.task),
                ink=True,
            ) 
            tags.append(due_tag)

        return ft.Row(tags, spacing=8, tight=True, wrap=True)

    def _menu(self) -> ft.PopupMenuButton:
        items = []
        if self.ctrl.state.is_mobile:
            items.append(create_option_item(
                ft.Icons.TIMER_OUTLINED, 
                "Start timer", 
                lambda e: self.ctrl.start_timer(self.task), 
                as_popup=True, 
            )) 

        items.extend([
            create_option_item(
                ft.Icons.EDIT_OUTLINED, 
                "Rename", 
                lambda e: self.ctrl.rename(self.task), 
                as_popup=True, 
            ), 
            create_option_item(
                ft.Icons.SCHEDULE_OUTLINED, 
                "Reschedule", 
                lambda e: self.ctrl.date_picker(self.task), 
                as_popup=True, 
            ), 
            create_option_item(
                ft.Icons.NEXT_PLAN_OUTLINED, 
                "Postpone by 1 day", 
                lambda e: self.ctrl.postpone(self.task), 
                as_popup=True, 
            ), 
            create_option_item(
                ft.Icons.REPEAT, 
                "Set recurrence", 
                lambda e: self.ctrl.recurrence(self.task), 
                as_popup=True, 
            ), 
            create_option_item(
                ft.Icons.CONTENT_COPY_OUTLINED, 
                "Duplicate task", 
                lambda e: self.ctrl.duplicate(self.task), 
                as_popup=True, 
            ), 
            ft.PopupMenuItem(),
            create_option_item(
                ft.Icons.INSIGHTS, 
                "Stats", 
                lambda e: self.ctrl.stats(self.task), 
                as_popup=True, 
            ), 
            create_option_item(
                ft.Icons.STICKY_NOTE_2_OUTLINED, 
                "Notes", 
                lambda e: self.ctrl.notes(self.task), 
                as_popup=True, 
            ), 
            ft.PopupMenuItem(),
            create_option_item(
                ft.Icons.DELETE_OUTLINE, 
                "Delete", 
                lambda e: self.ctrl.delete(self.task), 
                color=COLORS["danger"], 
                text_color=COLORS["danger"], 
                as_popup=True, 
            ), 
        ])

        return ft.PopupMenuButton(
            icon=ft.Icons.MORE_HORIZ, 
            icon_color="grey", 
            tooltip="Task options", 
            menu_position=ft.PopupMenuPosition.UNDER, 
            items=items, 
        ) 

    def _build_title_row(self, title_color, title_style, size: int = None) -> ft.Control:
        """Build the title display, including lock icon if locked."""
        if self.display.is_locked:
            return ft.Row(
                [
                    ft.Icon(ft.Icons.LOCK, color=COLORS["done_text"], size=16),
                    ft.Text(
                        "Encrypted",
                        weight="bold",
                        color=title_color or COLORS["done_text"],
                        style=title_style,
                        size=size,
                        italic=True,
                    ),
                ],
                spacing=4,
                tight=True,
            )
        return ft.Text(
            self.display.title,
            weight="bold",
            color=title_color,
            style=title_style,
            size=size,
            expand=True if size else False,
        )

    def build(self) -> ft.Container:
        cb = ft.Checkbox(value=self.is_done, on_change=self._on_check)
        title_style = (
            ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
            if self.is_done else None
        )
        title_color = COLORS["done_text"] if self.is_done else None
        bg = COLORS["done_bg"] if self.is_done else COLORS["card"]

        time_txt = ft.Text(
            f"{self.display.spent_display} / {self.display.estimated_display}",
            font_family="monospace",
            color=COLORS["done_text"],
            visible=not self.ctrl.state.is_mobile,
        ) 

        if self.is_done:
            return ft.Container(
                padding=15,
                bgcolor=bg,
                border_radius=BORDER_RADIUS,
                opacity=0.6,
                content=ft.Row([
                    cb,
                    ft.Column(
                        [
                            self._build_title_row(title_color, title_style),
                            self._tags(),
                        ],
                        expand=True,
                        spacing=2,
                    ),
                    time_txt,
                ]),
            ) 

        if self.ctrl.state.is_mobile:
            return ft.Container(
                padding=8,
                bgcolor=bg,
                border_radius=BORDER_RADIUS,
                data=self.task,
                content=ft.Column(
                    [
                        ft.Row([
                            cb,
                            self._build_title_row(title_color, title_style, size=14),
                            self._menu(),
                        ]),
                        self._tags(),
                    ],
                    spacing=2,
                    tight=True,
                ),
            ) 

        # Desktop layout
        timer_btn = ft.IconButton(
            ft.Icons.PLAY_ARROW,
            icon_color=COLORS["accent"],
            tooltip="Start timer",
            on_click=lambda e: self.ctrl.start_timer(self.task),
        )

        return ft.Container(
            padding=15,
            bgcolor=bg,
            border_radius=BORDER_RADIUS,
            data=self.task,
            content=ft.Row([
                ft.Icon(ft.Icons.DRAG_INDICATOR, color=ft.Colors.GREY),
                cb,
                ft.Column(
                    [
                        self._build_title_row(title_color, title_style),
                        ft.Row([self._tags()], tight=True),
                    ],
                    expand=True,
                    spacing=2,
                ),
                timer_btn,
                time_txt,
                self._menu(),
            ]),
        )