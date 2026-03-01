import asyncio
import logging
import flet as ft
import json
import urllib.request
import urllib.error
from typing import Callable

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    FONT_SIZE_SM,
    FONT_SIZE_MD,
    FONT_SIZE_XS,
)
from database import db
from i18n import t
from ui.helpers import accent_btn, SnackService

logger = logging.getLogger(__name__)


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
        self._api_key_field: ft.TextField | None = None
        self._email_field: ft.TextField | None = None
        self._status_text: ft.Text | None = None
        self._category_dd: ft.Dropdown | None = None
        self._message_field: ft.TextField | None = None

    @staticmethod
    def _send_http(
        api_key: str, email: str, category: str, message: str,
    ) -> str | None:
        """Send feedback via Resend API. Returns None on success, error string on failure.

        Pure I/O - no Flet UI calls so it's safe to run in a background thread.
        """
        formatted_message = message.replace("\n", "<br>")

        html_content = (
            '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto,'
            ' sans-serif; max-width: 600px; margin: 0 auto;">'
            '<div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);'
            ' padding: 24px; border-radius: 12px 12px 0 0;">'
            '<h1 style="color: white; margin: 0; font-size: 20px;">New Feedback</h1></div>'
            '<div style="background: #f8fafc; padding: 24px; border: 1px solid #e2e8f0;'
            ' border-top: none; border-radius: 0 0 12px 12px;">'
            '<div style="background: white; padding: 16px; border-radius: 8px;'
            ' border-left: 4px solid #6366f1;">'
            '<p style="margin: 0 0 8px 0; color: #64748b; font-size: 12px;'
            ' text-transform: uppercase; letter-spacing: 0.5px;">Category</p>'
            f'<p style="margin: 0; color: #1e293b; font-weight: 600;">{category}</p></div>'
            '<div style="margin-top: 16px; background: white; padding: 16px;'
            ' border-radius: 8px;">'
            '<p style="margin: 0 0 8px 0; color: #64748b; font-size: 12px;'
            ' text-transform: uppercase; letter-spacing: 0.5px;">Message</p>'
            f'<p style="margin: 0; color: #1e293b; line-height: 1.6;">{formatted_message}</p>'
            '</div>'
            '<p style="margin: 24px 0 0 0; color: #94a3b8; font-size: 12px;'
            ' text-align: center;">Sent from Trebnic App</p></div></div>'
        )

        payload = json.dumps({
            "from": "Trebnic <onboarding@resend.dev>",
            "to": [email],
            "subject": f"[{category}] Trebnic feedback",
            "html": html_content,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Trebnic/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    return None
                return f"HTTP {response.status}"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except OSError:
                pass
            return f"{e.code} {body}" if body else f"{e.code} {e.reason}"
        except urllib.error.URLError as e:
            return f"Network: {e.reason}"

    async def _open_donation_url(self, _e: ft.ControlEvent) -> None:
        await self.page.launch_url("https://github.com/sponsors/alex-stoica")

    async def _on_send_click(self, e: ft.ControlEvent) -> None:
        """Handle send feedback button click (async — Flet awaits this natively)."""
        try:
            message = (self._message_field.value if self._message_field else None) or ""
            category = (self._category_dd.value if self._category_dd else None) or ""

            if not message.strip():
                self.snack.show(t("please_enter_message"), COLORS["danger"])
                return

            # Read credentials from DB directly — avoids field-value timing issues
            api_key = await db.get_setting("resend_api_key", "")
            feedback_email = await db.get_setting("feedback_email", "")
            logger.debug("Feedback config: key=%s email=%s", bool(api_key), bool(feedback_email))

            if not api_key or not feedback_email:
                self.snack.show(t("feedback_not_configured"), COLORS["danger"])
                return

            self.snack.show(t("sending_feedback"), COLORS["accent"])

            # Blocking HTTP in a thread so the event loop stays free
            loop = asyncio.get_running_loop()
            error = await loop.run_in_executor(
                None, self._send_http, api_key, feedback_email, category, message,
            )
            logger.debug("Feedback send result: %s", error)

            if error is None:
                self.snack.show(t("feedback_sent"), COLORS["green"])
                if self._message_field:
                    self._message_field.value = ""
                    self._message_field.update()
            else:
                self.snack.show(
                    f"{t('feedback_failed')}: {error}", COLORS["danger"],
                )
        except Exception as exc:
            logger.exception("Send feedback failed")
            self.snack.show(t("error_generic").format(error=exc), COLORS["danger"])

    def _update_status_indicator(self) -> None:
        """Update the config status text based on current field values."""
        if not self._status_text:
            return
        has_key = bool((self._api_key_field.value or "").strip()) if self._api_key_field else False
        has_email = bool((self._email_field.value or "").strip()) if self._email_field else False
        if has_key and has_email:
            self._status_text.value = t("configured")
            self._status_text.color = COLORS["green"]
        else:
            self._status_text.value = t("not_configured")
            self._status_text.color = COLORS["orange"]
        self._status_text.update()

    def _save_config(self, e: ft.ControlEvent) -> None:
        """Save API key and email to database."""
        async def _save() -> None:
            api_key = (self._api_key_field.value or "").strip() if self._api_key_field else ""
            email = (self._email_field.value or "").strip() if self._email_field else ""
            await db.set_setting("resend_api_key", api_key)
            await db.set_setting("feedback_email", email)
            self.snack.show(t("config_saved"), COLORS["green"])
            self._update_status_indicator()

        self.page.run_task(_save)

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
                        size=FONT_SIZE_MD,
                        color=COLORS["done_text"],
                    ),
                    ft.Text(
                        t("support_desc_2"),
                        size=FONT_SIZE_MD,
                        color=COLORS["done_text"],
                    ),
                    ft.Container(height=5),
                    ft.Button(
                        t("make_donation"),
                        icon=ft.Icons.COFFEE,
                        bgcolor=COLORS["accent"],
                        color=COLORS["white"],
                        on_click=self._open_donation_url,
                    )
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        )

        # Feedback Form - store as instance attrs so _on_send_click can read them
        self._category_dd = ft.Dropdown(
            hint_text=t("category"),
            value=t("issue"),
            options=[
                ft.dropdown.Option(t("issue")),
                ft.dropdown.Option(t("feature_request")),
                ft.dropdown.Option(t("other")),
            ],
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
        )

        self._message_field = ft.TextField(
            hint_text=t("message_hint"),
            multiline=True,
            min_lines=5,
            max_lines=10,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
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
                    self._category_dd,
                    self._message_field,
                    ft.Container(
                        content=accent_btn(t("send_feedback"), self._on_send_click),
                        alignment=ft.Alignment(1, 0),
                    )
                ],
                spacing=15,
            ),
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        )

        # Email configuration section
        self._status_text = ft.Text(
            t("not_configured"),
            size=FONT_SIZE_XS,
            color=COLORS["orange"],
        )

        self._api_key_field = ft.TextField(
            label=t("resend_api_key"),
            password=True,
            can_reveal_password=True,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
            label_style=ft.TextStyle(size=FONT_SIZE_SM),
        )

        self._email_field = ft.TextField(
            label=t("feedback_email_label"),
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
            label_style=ft.TextStyle(size=FONT_SIZE_SM),
        )

        config_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row([
                                ft.Icon(ft.Icons.SETTINGS, color=COLORS["done_text"]),
                                ft.Text(t("email_config"), weight="bold", size=16),
                            ], spacing=10),
                            self._status_text,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        t("email_config_desc"),
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                    ),
                    ft.Container(height=5),
                    self._api_key_field,
                    self._email_field,
                    ft.Container(
                        content=accent_btn(t("save"), self._save_config),
                        alignment=ft.Alignment(1, 0),
                    ),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        )

        # Load saved config from DB
        async def _load_config() -> None:
            api_key = await db.get_setting("resend_api_key", "")
            email = await db.get_setting("feedback_email", "")
            if self._api_key_field:
                self._api_key_field.value = api_key or ""
                self._api_key_field.update()
            if self._email_field:
                self._email_field.value = email or ""
                self._email_field.update()
            self._update_status_indicator()

        self.page.run_task(_load_config)

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
                config_card,
                help_link,
            ],
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
        )
