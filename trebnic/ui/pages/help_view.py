import flet as ft
import urllib.parse
from typing import Callable

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    FEEDBACK_EMAIL,
    FONT_SIZE_SM, 
)
from ui.helpers import accent_btn, SnackService


class HelpPage:
    def __init__(
        self,
        page: ft.Page,
        navigate: Callable[[PageType], None],
        snack: SnackService,
    ) -> None:
        self.page = page
        self.navigate = navigate
        self.snack = snack

    def _send_feedback(self, category: str, message: str) -> None:
        """Launch default mail client with pre-filled feedback."""
        if not message.strip():
            self.snack.show("Please enter a message", COLORS["danger"])
            return

        subject = f"[{category}] Trebnic feedback"
        body = f"{message}\n\n--\nSent from Trebnic app"
        
        # URL encode parameters
        params = {
            "subject": subject,
            "body": body
        }
        query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        url = f"mailto:{FEEDBACK_EMAIL}?{query}"
        
        try:
            self.page.launch_url(url)
            self.snack.show("Opening email client...", COLORS["green"])
        except Exception as e:
            self.snack.show(f"Could not open mail client: {e}", COLORS["danger"])

    def build(self) -> ft.Column:
        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"],
        )
        header = ft.Row([back_btn, ft.Text("Help & Feedback", size=24, weight="bold")])

        # Donation Section
        donation_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([
                        ft.Icon(ft.Icons.FAVORITE, color=COLORS["danger"]),
                        ft.Text("Support Trebnic", weight="bold", size=16),
                    ], spacing=10),
                    ft.Text(
                        "Trebnic is designed to be free, private, and offline-first. "
                        "We don't track you or sell your data.",
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                    ),
                    ft.Text(
                        "Development and maintenance costs are supported by users like you. "
                        "If you find this app useful, please consider making a donation.",
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                    ),
                    ft.Container(height=5),
                    ft.ElevatedButton(
                        "Make a donation",
                        icon=ft.Icons.COFFEE,
                        bgcolor=COLORS["accent"],
                        color=COLORS["white"],
                        on_click=lambda e: self.page.launch_url("https://github.com/sponsors/alex-stoica"),
                    )
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        )

        # Feedback Form
        category_dd = ft.Dropdown(
            label="Category",
            value="Issue",
            options=[
                ft.dropdown.Option("Issue"),
                ft.dropdown.Option("Feature request"),
                ft.dropdown.Option("Other"),
            ],
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
        )

        message_field = ft.TextField(
            label="Message",
            multiline=True,
            min_lines=5,
            max_lines=10,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
            hint_text="Describe the issue or feature request...",
        )

        feedback_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([
                        ft.Icon(ft.Icons.FEEDBACK, color=COLORS["accent"]),
                        ft.Text("Send feedback", weight="bold", size=16),
                    ], spacing=10),
                    ft.Text(
                        f"Found a bug? Have an idea? Let us know!",
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                    ),
                    ft.Container(height=5),
                    category_dd,
                    message_field,
                    ft.Container(
                        content=accent_btn(
                            "Send Email",
                            lambda e: self._send_feedback(category_dd.value, message_field.value)
                        ),
                        alignment=ft.alignment.center_right,
                    )
                ],
                spacing=15,
            ),
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        )

        return ft.Column(
            [
                header,
                ft.Divider(height=20, color="transparent"),
                donation_card,
                feedback_card,
            ],
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
        )