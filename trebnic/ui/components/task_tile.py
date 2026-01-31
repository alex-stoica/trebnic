import flet as ft
from typing import Optional

from config import COLORS, BORDER_RADIUS
from events import event_bus, AppEvent
from models.entities import Task, Project, AppState
from services.crypto import LOCKED_PLACEHOLDER
from ui.dialogs.base import create_option_item
from ui.presenters.task_presenter import TaskPresenter


class TaskTile:
    """Single task row component that emits events for user interactions.

    Instead of calling controller methods directly, this component emits events
    to the EventBus. The app layer subscribes to these events and dispatches
    to appropriate handlers. This decouples the UI from business logic.
    """

    def __init__(
        self,
        task: Task,
        is_done: bool,
        state: AppState,
        project: Optional[Project] = None,
    ) -> None:
        self.task = task
        self.is_done = is_done
        self.state = state
        self.display = TaskPresenter.create_display_data(task, project) 

    def _on_check(self, e: ft.ControlEvent) -> None:
        if self.is_done and not e.control.value:
            event_bus.emit(AppEvent.TASK_UNCOMPLETE_REQUESTED, self.task)
        elif not self.is_done and e.control.value:
            event_bus.emit(AppEvent.TASK_COMPLETE_REQUESTED, self.task)

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
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                border_radius=5,
            )

        tags = []
        if self.display.project_name:
            project_tag = ft.Container(
                content=self._build_project_tag_content(),
                bgcolor=self.display.project_color,
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                border_radius=5,
                on_click=lambda e: event_bus.emit(AppEvent.TASK_ASSIGN_PROJECT_REQUESTED, self.task),
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
                border=ft.Border.all(1, COLORS["border"]),
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                border_radius=5,
                on_click=lambda e: event_bus.emit(AppEvent.TASK_ASSIGN_PROJECT_REQUESTED, self.task),
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
                padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                border_radius=5,
                on_click=lambda e: event_bus.emit(AppEvent.TASK_DATE_PICKER_REQUESTED, self.task),
                ink=True,
            )
            tags.append(due_tag)

        return ft.Row(tags, spacing=8, tight=True, wrap=True)

    def _menu(self) -> ft.PopupMenuButton:
        items = []
        if self.state.is_mobile:
            items.append(create_option_item(
                ft.Icons.TIMER_OUTLINED,
                "Start timer",
                lambda e: event_bus.emit(AppEvent.TASK_START_TIMER_REQUESTED, self.task),
                as_popup=True,
            ))

        items.extend([
            create_option_item(
                ft.Icons.EDIT_OUTLINED,
                "Rename",
                lambda e: event_bus.emit(AppEvent.TASK_RENAME_REQUESTED, self.task),
                as_popup=True,
            ),
            create_option_item(
                ft.Icons.SCHEDULE_OUTLINED,
                "Reschedule",
                lambda e: event_bus.emit(AppEvent.TASK_DATE_PICKER_REQUESTED, self.task),
                as_popup=True,
            ),
            create_option_item(
                ft.Icons.NEXT_PLAN_OUTLINED,
                "Postpone by 1 day",
                lambda e: event_bus.emit(AppEvent.TASK_POSTPONE_REQUESTED, self.task),
                as_popup=True,
            ),
            create_option_item(
                ft.Icons.REPEAT,
                "Set recurrence",
                lambda e: event_bus.emit(AppEvent.TASK_RECURRENCE_REQUESTED, self.task),
                as_popup=True,
            ),
            create_option_item(
                ft.Icons.CONTENT_COPY_OUTLINED,
                "Duplicate task",
                lambda e: event_bus.emit(AppEvent.TASK_DUPLICATE_REQUESTED, self.task),
                as_popup=True,
            ),
            ft.PopupMenuItem(),
            create_option_item(
                ft.Icons.INSIGHTS,
                "Stats",
                lambda e: event_bus.emit(AppEvent.TASK_STATS_REQUESTED, self.task),
                as_popup=True,
            ),
            create_option_item(
                ft.Icons.STICKY_NOTE_2_OUTLINED,
                "Notes",
                lambda e: event_bus.emit(AppEvent.TASK_NOTES_REQUESTED, self.task),
                as_popup=True,
            ),
            ft.PopupMenuItem(),
            create_option_item(
                ft.Icons.DELETE_OUTLINE,
                "Delete",
                lambda e: event_bus.emit(AppEvent.TASK_DELETE_REQUESTED, self.task),
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
            visible=not self.state.is_mobile,
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

        if self.state.is_mobile:
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
            on_click=lambda e: event_bus.emit(AppEvent.TASK_START_TIMER_REQUESTED, self.task),
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