import flet as ft
from typing import Callable
from flet_movable import Movable

from config import COLORS
from i18n import t
from ui.helpers import format_timer_display


class TimerWidget(ft.Container):
    def __init__(self, on_stop: Callable[[ft.ControlEvent], None]) -> None:
        self.display = ft.Text("00:00", size=22, weight=ft.FontWeight.W_600, color="#F8FAFC")
        self.task_text = ft.Text("", size=10, color=COLORS["white"],
                                 width=130, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
        self.stop_button = ft.IconButton(
            ft.Icons.STOP,
            icon_color=COLORS["white"],
            tooltip=t("stop_timer"),
            on_click=on_stop,
        )
        self.drag_handle = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.DRAG_INDICATOR, size=18, color="#94A3B8"),
                ft.Column([self.display, self.task_text], tight=True, spacing=2),
            ], spacing=6, tight=True),
        )
        self.card = ft.Container(
            content=ft.Row([
                self.drag_handle,
                self.stop_button,
            ], tight=True, spacing=4),
            bgcolor="#182334",
            border=ft.Border.all(1, "#334155"),
            shadow=ft.BoxShadow(blur_radius=14, spread_radius=0, color="#44000000", offset=ft.Offset(0, 4)),
            padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            border_radius=22,
        )

        self.movable = Movable(
            content=self.card, x=152, y=590, item_width=232, item_height=72,
            edge_padding=8, long_press_duration=0.5, haptic=True,
            drag_border=ft.Border.all(2, COLORS["accent"]), drag_border_radius=22,
            left=0, top=0, right=0, bottom=0,
        )
        super().__init__(
            content=ft.Stack([self.movable], expand=True),
            left=0, top=0, right=0, bottom=0, visible=False,
        )

    def start(self, task_title: str) -> None:
        self.display.value = "00:00"
        self.task_text.value = task_title
        self.visible = True

    def update_time(self, seconds: int) -> None:
        self.display.value = format_timer_display(seconds)

    def stop(self) -> None:
        self.visible = False
