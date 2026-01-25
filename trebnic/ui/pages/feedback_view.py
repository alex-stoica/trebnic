import flet as ft
import httpx
from typing import Callable

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    FEEDBACK_EMAIL,
    FONT_SIZE_SM,
)
from ui.helpers import accent_btn, SnackService


class FeedbackPage:
    def __init__(
        self,
        page: ft.Page,
        navigate: Callable[[PageType], None],
        snack: SnackService,
    ) -> None:
        self.page = page
        self.navigate = navigate
        self.snack = snack

    async def _send_feedback_async(self, category: str, message: str, message_field: ft.TextField) -> None:
        """Send feedback directly via formsubmit.co."""
        subject = f"[{category}] Trebnic feedback"

        data = {
            "_subject": subject,
            "message": message,
            "_template": "table",
            "_captcha": "false",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://formsubmit.co/ajax/{FEEDBACK_EMAIL}",
                    data=data,
                    timeout=15.0,
                )

            if response.status_code == 200:
                self.snack.show("Feedback sent, thank you!", COLORS["green"])
                message_field.value = ""
                message_field.update()
            else:
                self.snack.show("Failed to send feedback. Please try again.", COLORS["danger"])
        except httpx.TimeoutException:
            self.snack.show("Request timed out. Check your connection.", COLORS["danger"])
        except httpx.RequestError as e:
            self.snack.show(f"Network error: {e}", COLORS["danger"])

    def _send_feedback(self, category: str, message: str, message_field: ft.TextField) -> None:
        """Validate and trigger async feedback send."""
        if not message.strip():
            self.snack.show("Please enter a message", COLORS["danger"])
            return

        self.snack.show("Sending feedback...", COLORS["accent"])
        self.page.run_task(self._send_feedback_async, category, message, message_field)

    def build(self) -> ft.Column:
        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"],
        )
        header = ft.Row([back_btn, ft.Text("Feedback & Support", size=24, weight="bold")])

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
                            "Send feedback",
                            lambda e: self._send_feedback(category_dd.value, message_field.value, message_field)
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

        # Link to Help
        help_link = ft.Container(
            content=ft.TextButton(
                "Need help using Trebnic? View the guide",
                icon=ft.Icons.HELP_OUTLINE,
                on_click=lambda e: self.navigate(PageType.HELP),
            ),
            alignment=ft.alignment.center,
        )

        return ft.Column(
            [
                header,
                ft.Divider(height=20, color="transparent"),
                donation_card,
                feedback_card,
                help_link,
            ],
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
        )
