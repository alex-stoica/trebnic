import flet as ft
from typing import Callable 

from config import COLORS
from i18n import t
from ui.helpers import format_timer_display


class TimerWidget(ft.Container):
    def __init__(self, on_stop: Callable[[ft.ControlEvent], None]) -> None: 
        self.display = ft.Text("00:00", size=20, weight="bold")
        self.task_text = ft.Text("", size=10, color=COLORS["white"])
        super().__init__(
            content=ft.Column(
                [ 
                    ft.Row( 
                        [ft.Icon(ft.Icons.TIMER), self.display], 
                        tight=True, 
                    ), 
                    self.task_text, 
                ], 
                tight=True,
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ), 
            bgcolor=COLORS["accent"],
            padding=ft.Padding.symmetric(horizontal=15, vertical=5),
            border_radius=20,
            visible=False,
            on_click=on_stop,
            ink=True,
            tooltip=t("click_to_stop_timer"),
        ) 

    def start(self, task_title: str) -> None: 
        self.display.value = "00:00"
        self.task_text.value = task_title
        self.visible = True

    def update_time(self, seconds: int) -> None: 
        self.display.value = format_timer_display(seconds)

    def stop(self) -> None: 
        self.visible = False