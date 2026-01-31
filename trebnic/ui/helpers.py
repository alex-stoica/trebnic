import flet as ft
from datetime import date
from typing import Optional

from config import COLORS, SNACK_DURATION_MS
from ui.formatters import TimeFormatter


def format_duration(minutes: int) -> str:
    """Format duration - delegates to TimeFormatter."""
    return TimeFormatter.minutes_to_display(minutes)


def seconds_to_time(seconds: int) -> str:
    """Format seconds - delegates to TimeFormatter."""
    return TimeFormatter.seconds_to_display(seconds)


def format_timer_display(seconds: int) -> str:
    """Format timer display - delegates to TimeFormatter."""
    return TimeFormatter.seconds_to_timer(seconds)


def format_due_date(due_date: Optional[date]) -> Optional[str]:
    if due_date is None:
        return None
    delta = (due_date - date.today()).days
    date_str = due_date.strftime("%b %d")
    if delta < 0:
        return f"🔴 {date_str}"
    elif delta == 0:
        return "📅 Today"
    elif delta == 1:
        return "📆 Tomorrow"
    elif delta <= 7:
        return f"🗓️ {date_str}"
    return f"📋 {date_str}"


def accent_btn(text: str, on_click) -> ft.Button:
    return ft.Button(
        text,
        on_click=on_click,
        bgcolor=COLORS["accent"],
        color=COLORS["white"],
    )


def danger_btn(
    text: str,
    on_click,
    icon: Optional[str] = None,
) -> ft.Button:
    return ft.Button(
        text,
        on_click=on_click,
        bgcolor=COLORS["danger"],
        color=COLORS["white"],
        icon=icon,
    )


class SnackService:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.snack = ft.SnackBar(
            content=ft.Text(""),
            bgcolor=COLORS["card"],
            duration=SNACK_DURATION_MS,
        )
        page.overlay.append(self.snack)

    def show(
        self,
        message: str,
        color: Optional[str] = None,
        update: bool = True,
    ) -> None:
        self.snack.content = ft.Text(message, color=COLORS["white"])
        self.snack.bgcolor = color or COLORS["card"]
        self.snack.open = True
        if update:
            self.page.update()