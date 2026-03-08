import flet as ft
import httpx
from typing import Callable, Optional, Union

from config import COLORS, SNACK_DURATION_MS
from i18n import t
from ui.formatters import TimeFormatter


def friendly_http_error(exc: Union[Exception, str]) -> str:
    """Classify an HTTP exception or error string into a user-friendly translated message."""
    if isinstance(exc, httpx.TimeoutException):
        return t("error_timeout")
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 401:
            return t("invalid_api_key")
        if code == 403:
            return t("error_forbidden")
        if code == 429:
            return t("error_rate_limit")
        if 500 <= code < 600:
            return t("error_server")
        return t("error_unknown_http")
    if isinstance(exc, httpx.ConnectError):
        return t("error_connection")

    text = str(exc).lower()
    if "timeout" in text:
        return t("error_timeout")
    if "401" in text or "authentication" in text:
        return t("invalid_api_key")
    if "403" in text:
        return t("error_forbidden")
    if "429" in text:
        return t("error_rate_limit")
    if "connect" in text or "getaddrinfo" in text:
        return t("error_connection")
    if any(f"{c}" in text for c in range(500, 600)):
        return t("error_server")
    return t("error_unknown_http")


def format_duration(minutes: int) -> str:
    """Format duration - delegates to TimeFormatter."""
    return TimeFormatter.minutes_to_display(minutes)


def seconds_to_time(seconds: int) -> str:
    """Format seconds - delegates to TimeFormatter."""
    return TimeFormatter.seconds_to_display(seconds)


def format_timer_display(seconds: int) -> str:
    """Format timer display - delegates to TimeFormatter."""
    return TimeFormatter.seconds_to_timer(seconds)



def accent_btn(text: str, on_click: Callable[[ft.ControlEvent], None]) -> ft.Button:
    return ft.Button(
        text,
        on_click=on_click,
        bgcolor=COLORS["accent"],
        color=COLORS["white"],
    )


def danger_btn(
    text: str,
    on_click: Callable[[ft.ControlEvent], None],
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
        self.snack.open = False
        self.snack.content = ft.Text(message, color=COLORS["white"])
        self.snack.bgcolor = color or COLORS["card"]
        self.snack.open = True
        if update:
            self.page.update()