import flet as ft 
from constants import COLORS, BORDER_RADIUS 
from models import Task, AppController 
from helpers import seconds_to_time 


def _create_menu_item(icon, text, on_click, color=COLORS["accent"], text_color=None): 
    return ft.PopupMenuItem( 
        content=ft.Container( 
            content=ft.Row(
                [ft.Icon(icon, size=18, color=color), ft.Text(text, size=14, color=text_color)],
                spacing=12
            ),
            padding=ft.padding.symmetric(vertical=5, horizontal=10) 
        ), 
        on_click=on_click, 
    ) 


class TaskComponent: 
    def __init__(self, task: Task, is_completed: bool, controller: AppController): 
        self.task = task 
        self._is_completed = is_completed 
        self.controller = controller 
 
    @property 
    def state(self): 
        return self.controller.state 
 
    @property 
    def is_completed(self): 
        return self._is_completed 
 
    @is_completed.setter 
    def is_completed(self, value: bool): 
        self._is_completed = value 
 
    @property 
    def _title_style(self): 
        return (
            ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
            if self.is_completed else None
        )
 
    @property 
    def _title_color(self): 
        return COLORS["done_text"] if self.is_completed else None 
 
    @property 
    def _bg_color(self): 
        return COLORS["done_bg"] if self.is_completed else COLORS["card"] 
 
    @property 
    def _opacity(self): 
        return 0.6 if self.is_completed else 1.0 
 
    def _format_title(self): 
        return f"↻ {self.task.title}" if self.task.recurrent else self.task.title 
 
    def _on_check_change(self, e): 
        if self.is_completed and not e.control.value: 
            self.controller.uncomplete(self.task) 
        elif not self.is_completed and e.control.value: 
            self.controller.complete(self.task) 
 
    def _create_tags_row(self): 
        project = self.controller.get_project(self.task.project_id) 
        due_str = self.controller.format_due_date(self.task.due_date) 
     
        if self.is_completed: 
            info_parts = [project["name"] if project else "Unassigned"] 
            if due_str: 
                info_parts.append(due_str) 
            return ft.Container( 
                content=ft.Text(
                    " • ".join(info_parts), size=10, color=COLORS["done_text"]
                ),
                bgcolor=COLORS["done_tag"], 
                padding=ft.padding.symmetric(horizontal=8, vertical=2), 
                border_radius=5, 
            ) 
     
        tag_items = [] 
        if project: 
            project_tag = ft.Container( 
                content=ft.Row(
                    [
                        ft.Text(project["icon"], size=10),
                        ft.Text(project["name"], size=10, color=COLORS["white"])
                    ],
                    spacing=4, tight=True
                ),
                bgcolor=project["color"], 
                padding=ft.padding.symmetric(horizontal=8, vertical=2), 
                border_radius=5, 
                on_click=lambda e: self.controller.assign_project(self.task), 
                ink=True, 
            ) 
        else: 
            project_tag = ft.Container( 
                content=ft.Text("Unassigned", size=10, color=COLORS["unassigned"]), 
                bgcolor=COLORS["input_bg"], 
                border=ft.border.all(1, COLORS["border"]), 
                padding=ft.padding.symmetric(horizontal=8, vertical=2), 
                border_radius=5, 
                on_click=lambda e: self.controller.assign_project(self.task), 
                ink=True, 
            ) 
        tag_items.append(project_tag) 
     
        if due_str: 
            tag_items.append(ft.Container( 
                content=ft.Text(due_str, size=10, color=COLORS["done_text"]), 
                bgcolor=COLORS["input_bg"], 
                padding=ft.padding.symmetric(horizontal=8, vertical=2), 
                border_radius=5, 
                on_click=lambda e: self.controller.date_picker(self.task), 
                ink=True, 
            )) 
        return ft.Row(tag_items, spacing=8, tight=True, wrap=True) 
 
    def _create_menu(self): 
        items = [] 
        if self.state.is_mobile: 
            items.append(_create_menu_item(
                ft.Icons.TIMER_OUTLINED, "Start timer",
                lambda e: self.controller.start_timer(self.task)
            ))
        items.extend([ 
            _create_menu_item(
                ft.Icons.EDIT_OUTLINED, "Rename",
                lambda e: self.controller.rename(self.task)
            ),
            _create_menu_item(
                ft.Icons.SCHEDULE_OUTLINED, "Reschedule",
                lambda e: self.controller.date_picker(self.task)
            ),
            _create_menu_item(
                ft.Icons.NEXT_PLAN_OUTLINED, "Postpone by 1 day",
                lambda e: self.controller.postpone(self.task)
            ),
            _create_menu_item(
                ft.Icons.REPEAT, "Set recurrence",
                lambda e: self.controller.recurrence(self.task)
            ),
            _create_menu_item(
                ft.Icons.CONTENT_COPY_OUTLINED, "Duplicate task",
                lambda e: self.controller.duplicate(self.task)
            ),
            ft.PopupMenuItem(), 
            _create_menu_item(
                ft.Icons.INSIGHTS, "Stats", lambda e: self.controller.stats(self.task)
            ),
            _create_menu_item(
                ft.Icons.STICKY_NOTE_2_OUTLINED, "Notes",
                lambda e: self.controller.notes(self.task)
            ),
            ft.PopupMenuItem(), 
            _create_menu_item(
                ft.Icons.DELETE_OUTLINE, "Delete",
                lambda e: self.controller.delete(self.task),
                color=COLORS["danger"], text_color=COLORS["danger"]
            ),
        ]) 
        return ft.PopupMenuButton(
            icon=ft.Icons.MORE_HORIZ, icon_color="grey",
            tooltip="Task options", menu_position=ft.PopupMenuPosition.UNDER, items=items
        )
 
    def build(self) -> ft.Container: 
        checkbox = ft.Checkbox(value=self.is_completed, on_change=self._on_check_change) 
        title_text = ft.Text(
            self._format_title(), weight="bold",
            color=self._title_color, style=self._title_style
        )
        tags_row = self._create_tags_row() 
        time_display = ft.Text(
            f"{seconds_to_time(self.task.spent_seconds)} / "
            f"{seconds_to_time(self.task.estimated_seconds)}",
            font_family="monospace", color=COLORS["done_text"],
            visible=not self.state.is_mobile
        )
     
        if self.is_completed: 
            return ft.Container(
                padding=15, bgcolor=self._bg_color,
                border_radius=BORDER_RADIUS, opacity=self._opacity,
                content=ft.Row([
                    checkbox,
                    ft.Column([title_text, tags_row], expand=True, spacing=2),
                    time_display
                ])
            )
     
        if self.state.is_mobile: 
            return ft.Container(
                padding=8, bgcolor=self._bg_color,
                border_radius=BORDER_RADIUS, data=self.task,
                content=ft.Column([
                    ft.Row([
                        checkbox,
                        ft.Text(self._format_title(), weight="bold", expand=True, size=14),
                        self._create_menu()
                    ]),
                    tags_row
                ], spacing=2, tight=True)
            )
     
        return ft.Container(
            padding=15, bgcolor=self._bg_color,
            border_radius=BORDER_RADIUS, data=self.task,
            content=ft.Row([
                ft.Icon(ft.Icons.DRAG_INDICATOR, color=ft.Colors.GREY),
                checkbox,
                ft.Column(
                    [title_text, ft.Row([tags_row], tight=True)],
                    expand=True, spacing=2
                ),
                ft.IconButton(
                    ft.Icons.PLAY_ARROW, icon_color=COLORS["accent"],
                    tooltip="Start timer",
                    on_click=lambda e: self.controller.start_timer(self.task)
                ),
                time_display,
                self._create_menu()
            ])
        )