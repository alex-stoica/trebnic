import flet as ft
from datetime import date, timedelta
from typing import Callable, List, Optional, Tuple

from config import COLORS, CALENDAR_HEADER_HEIGHT
from models.entities import AppState, Task


class CalendarView:
    def __init__(self, state: AppState, on_update: Optional[Callable[[], None]] = None) -> None:
        self.state = state
        self.on_update = on_update

    def _get_tasks_for_date(self, d: date) -> Tuple[List[Task], List[Task]]: 
        pending = [t for t in self.state.tasks if t.due_date == d] 
        done = [t for t in self.state.done_tasks if t.due_date == d] 
        return pending, done 

    def _create_chip(self, task: Task, is_done: bool = False) -> ft.Container: 
        project = self.state.get_project_by_id(task.project_id)
        color = project.color if project else COLORS["card"] 

        if is_done:
            return ft.Container(
                content=ft.Text(
                    task.title,
                    size=9,
                    max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH),
                    color=COLORS["done_text"], 
                ), 
                bgcolor=COLORS["done_bg"],
                padding=ft.padding.symmetric(horizontal=4, vertical=2),
                border_radius=4,
                margin=ft.margin.only(bottom=2),
            ) 

        return ft.Container(
            content=ft.Text(
                task.title,
                size=9,
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
                color=COLORS["white"], 
            ), 
            bgcolor=color,
            padding=ft.padding.symmetric(horizontal=4, vertical=2),
            border_radius=4,
            margin=ft.margin.only(bottom=2),
        ) 

    def _create_day_column(self, idx: int, d: date, today: date) -> ft.Container: 
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        pending, done = self._get_tasks_for_date(d)

        is_today = d == today
        is_past = d < today

        items = [self._create_chip(t) for t in pending] 
        items.extend([self._create_chip(t, True) for t in done]) 

        header_bg = (
            COLORS["accent"] if is_today 
            else (COLORS["done_bg"] if is_past else COLORS["card"]) 
        ) 
        header_color = COLORS["white"] if is_today else COLORS["done_text"]

        header = ft.Container(
            content=ft.Column(
                [ 
                    ft.Text(day_names[idx], size=9, color=header_color), 
                    ft.Text(str(d.day), size=14, weight="bold", color=header_color), 
                ], 
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ), 
            bgcolor=header_bg,
            padding=ft.padding.symmetric(horizontal=4, vertical=6),
            border_radius=6,
            height=CALENDAR_HEADER_HEIGHT,
            alignment=ft.alignment.center,
        ) 

        content_control = (
            ft.Column(items, scroll=ft.ScrollMode.AUTO, spacing=2) 
            if items 
            else ft.Text( 
                "—", 
                size=10, 
                color=COLORS["done_text"], 
                text_align=ft.TextAlign.CENTER, 
            ) 
        ) 

        content = ft.Container(
            content=content_control, 
            padding=4,
            expand=True,
            alignment=ft.alignment.top_center,
        ) 

        border_color = COLORS["accent"] if is_today else COLORS["border"]

        return ft.Container(
            content=ft.Column(
                [header, content], 
                spacing=4, 
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH, 
            ), 
            expand=True,
            border=ft.border.all(1, border_color),
            border_radius=6,
        ) 

    def _navigate_week(self, delta: int) -> None:
        """Navigate forward or backward by delta weeks."""
        self.state.calendar_week_offset += delta
        if self.on_update:
            self.on_update()

    def build(self) -> ft.Column:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        start = week_start + timedelta(weeks=self.state.calendar_week_offset)
        days = [start + timedelta(days=i) for i in range(7)]

        date_range = f"{days[0].strftime('%b %d')} - {days[6].strftime('%b %d, %Y')}"

        # Navigation controls grouped together to prevent overflow on mobile
        nav_controls = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_LEFT,
                    icon_color=COLORS["accent"],
                    tooltip="Previous week",
                    on_click=lambda e: self._navigate_week(-1),
                ),
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_RIGHT,
                    icon_color=COLORS["accent"],
                    tooltip="Next week",
                    on_click=lambda e: self._navigate_week(1),
                ),
            ],
            spacing=0,
            tight=True,
        )

        header_row = ft.Row(
            [
                ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK, color=COLORS["accent"], size=20),
                ft.Text("Calendar", size=16, weight="bold"),
                ft.Container(expand=True),
                ft.Text(date_range, color=COLORS["done_text"], size=11),
                nav_controls,
            ],
            spacing=4,
        )

        day_columns = [self._create_day_column(i, d, today) for i, d in enumerate(days)]

        calendar_row = ft.Row(
            day_columns,
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        calendar_container = ft.Container(
            content=calendar_row,
            expand=True,
            padding=ft.padding.only(top=10),
        )

        return ft.Column([header_row, calendar_container], expand=True)