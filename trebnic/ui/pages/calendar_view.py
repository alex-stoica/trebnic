import flet as ft
from datetime import date, timedelta

from config import COLORS, CALENDAR_HEADER_HEIGHT
from models.entities import AppState


class CalendarView:
    def __init__(self, state: AppState):
        self.state = state

    def build(self) -> ft.Column:
        today = date.today()
        start = today - timedelta(days=today.weekday())
        days = [start + timedelta(days=i) for i in range(7)]
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        def get_tasks(d):
            return [t for t in self.state.tasks if t.due_date == d], [t for t in self.state.done_tasks if t.due_date == d]

        def chip(task, is_done=False):
            project = self.state.get_project_by_id(task.project_id)
            color = project["color"] if project else COLORS["card"]
            if is_done:
                return ft.Container(content=ft.Text(task.title, size=9, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                                    style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH), color=COLORS["done_text"]),
                                    bgcolor=COLORS["done_bg"], padding=ft.padding.symmetric(horizontal=4, vertical=2), border_radius=4, margin=ft.margin.only(bottom=2))
            return ft.Container(content=ft.Text(task.title, size=9, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=COLORS["white"]),
                                bgcolor=color, padding=ft.padding.symmetric(horizontal=4, vertical=2), border_radius=4, margin=ft.margin.only(bottom=2))

        def day_col(i, d):
            pending, done = get_tasks(d)
            is_today, is_past = d == today, d < today
            items = [chip(t) for t in pending] + [chip(t, True) for t in done]
            header_bg = COLORS["accent"] if is_today else (COLORS["done_bg"] if is_past else COLORS["card"])
            header_color = COLORS["white"] if is_today else COLORS["done_text"]
            header = ft.Container(content=ft.Column([ft.Text(names[i], size=9, color=header_color),
                                                     ft.Text(str(d.day), size=14, weight="bold", color=header_color)],
                                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                                  bgcolor=header_bg, padding=ft.padding.symmetric(horizontal=4, vertical=6), border_radius=6,
                                  height=CALENDAR_HEADER_HEIGHT, alignment=ft.alignment.center)
            content = ft.Container(content=ft.Column(items, scroll=ft.ScrollMode.AUTO, spacing=2) if items else ft.Text("—", size=10, color=COLORS["done_text"], text_align=ft.TextAlign.CENTER),
                                   padding=4, expand=True, alignment=ft.alignment.top_center)
            return ft.Container(content=ft.Column([header, content], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                                expand=True, border=ft.border.all(1, COLORS["accent"] if is_today else COLORS["border"]), border_radius=6)

        date_range = f"{days[0].strftime('%b %d')} - {days[6].strftime('%b %d, %Y')}"
        return ft.Column([ft.Row([ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK, color=COLORS["accent"], size=20),
                                  ft.Text("Weekly Calendar", size=16, weight="bold"), ft.Container(expand=True),
                                  ft.Text(date_range, color=COLORS["done_text"], size=11)], spacing=8),
                          ft.Container(content=ft.Row([day_col(i, d) for i, d in enumerate(days)], spacing=4,
                                                      vertical_alignment=ft.CrossAxisAlignment.START), expand=True, padding=ft.padding.only(top=10))], expand=True)