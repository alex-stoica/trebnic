import flet as ft
import json
import urllib.request
import urllib.error
from typing import Callable

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    RESEND_API_KEY,
    FEEDBACK_EMAIL,
    FONT_SIZE_SM,
    FONT_SIZE_MD,
    FONT_SIZE_XS,
)
from i18n import t
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

    def _send_feedback_sync(self, category: str, message: str, message_field: ft.TextField) -> None:
        """Send feedback via Resend email API using urllib (no external dependencies)."""
        if not RESEND_API_KEY or not FEEDBACK_EMAIL:
            self.snack.show(t("feedback_not_configured"), COLORS["danger"])
            return

        # Format message with line breaks preserved
        formatted_message = message.replace("\n", "<br>")

        html_content = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 24px; border-radius: 12px 12px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 20px;">📬 New Feedback</h1>
            </div>
            <div style="background: #f8fafc; padding: 24px; border: 1px solid #e2e8f0; border-top: none; border-radius: 0 0 12px 12px;">
                <div style="background: white; padding: 16px; border-radius: 8px; border-left: 4px solid #6366f1;">
                    <p style="margin: 0 0 8px 0; color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Category</p>
                    <p style="margin: 0; color: #1e293b; font-weight: 600;">{category}</p>
                </div>
                <div style="margin-top: 16px; background: white; padding: 16px; border-radius: 8px;">
                    <p style="margin: 0 0 8px 0; color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Message</p>
                    <p style="margin: 0; color: #1e293b; line-height: 1.6;">{formatted_message}</p>
                </div>
                <p style="margin: 24px 0 0 0; color: #94a3b8; font-size: 12px; text-align: center;">Sent from Trebnic App</p>
            </div>
        </div>
        """

        payload = json.dumps({
            "from": "Trebnic <onboarding@resend.dev>",
            "to": [FEEDBACK_EMAIL],
            "subject": f"[{category}] Trebnic feedback",
            "html": html_content,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    self.snack.show(t("feedback_sent"), COLORS["green"])
                    message_field.value = ""
                    message_field.update()
                else:
                    self.snack.show(f"{t('feedback_failed')}: HTTP {response.status}", COLORS["danger"])
        except urllib.error.HTTPError as e:
            self.snack.show(f"{t('feedback_failed')}: {e.code} {e.reason}", COLORS["danger"])
        except urllib.error.URLError as e:
            self.snack.show(f"{t('network_error')}: {e.reason}", COLORS["danger"])

    def _send_feedback(self, category: str, message: str, message_field: ft.TextField) -> None:
        """Validate and send feedback."""
        if not message.strip():
            self.snack.show(t("please_enter_message"), COLORS["danger"])
            return

        self.snack.show(t("sending_feedback"), COLORS["accent"])
        self._send_feedback_sync(category, message, message_field)

    def build(self) -> ft.Column:
        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"],
        )
        header = ft.Row([back_btn, ft.Text(t("feedback_and_support"), size=24, weight="bold")])

        # Donation Section
        donation_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([
                        ft.Icon(ft.Icons.FAVORITE, color=COLORS["danger"]),
                        ft.Text(t("support_trebnic"), weight="bold", size=16),
                    ], spacing=10),
                    ft.Text(
                        t("support_desc_1"),
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                    ),
                    ft.Text(
                        t("support_desc_2"),
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                    ),
                    ft.Container(height=5),
                    ft.Button(
                        t("make_donation"),
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
            label=t("category"),
            value=t("issue"),
            options=[
                ft.dropdown.Option(t("issue")),
                ft.dropdown.Option(t("feature_request")),
                ft.dropdown.Option(t("other")),
            ],
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
            label_style=ft.TextStyle(size=FONT_SIZE_SM),
        )

        message_field = ft.TextField(
            label=t("message"),
            multiline=True,
            min_lines=5,
            max_lines=10,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
            hint_text=t("message_hint"),
            label_style=ft.TextStyle(size=FONT_SIZE_SM),
        )

        feedback_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([
                        ft.Icon(ft.Icons.FEEDBACK, color=COLORS["accent"]),
                        ft.Text(t("send_feedback"), weight="bold", size=16),
                    ], spacing=10),
                    ft.Text(
                        t("found_bug"),
                        size=FONT_SIZE_MD,
                        color=COLORS["done_text"],
                    ),
                    ft.Container(height=5),
                    category_dd,
                    message_field,
                    ft.Container(
                        content=accent_btn(
                            t("send_feedback"),
                            lambda e: self._send_feedback(category_dd.value, message_field.value, message_field)
                        ),
                        alignment=ft.Alignment(1, 0),
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
                t("need_help_link"),
                icon=ft.Icons.HELP_OUTLINE,
                on_click=lambda e: self.navigate(PageType.HELP),
            ),
            alignment=ft.Alignment(0, 0),
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
