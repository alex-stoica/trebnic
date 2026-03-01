"""Chat page UI for Claude AI assistant.

Provides a conversational interface where users can manage tasks via natural
language. Messages are sent to Claude which uses tool_use to call TrebnicAPI
methods. The conversation is ephemeral (resets on navigation).
"""
import logging
from typing import Any, Callable, Dict, List, Optional

import flet as ft

from config import (
    BORDER_RADIUS,
    BORDER_RADIUS_MD,
    COLORS,
    FONT_SIZE_MD,
    FONT_SIZE_SM,
    FONT_SIZE_XS,
    PageType,
    SPACING_MD,
    SPACING_SM,
)
from i18n import t
from models.entities import AppState
from services.claude_service import ClaudeService, save_api_key, load_api_key
from ui.helpers import SnackService, accent_btn

logger = logging.getLogger(__name__)


class ChatView:
    """Chat page for conversing with Claude to manage tasks."""

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        claude_service: ClaudeService,
        snack: SnackService,
        navigate: Callable[[PageType], None],
    ) -> None:
        self.page = page
        self.state = state
        self.claude_service = claude_service
        self.snack = snack
        self.navigate = navigate

        # Conversation state (ephemeral — reset on each build)
        self._messages: List[Dict[str, Any]] = []
        self._chat_column: Optional[ft.Column] = None
        self._input_field: Optional[ft.TextField] = None
        self._send_btn: Optional[ft.IconButton] = None
        self._loading_row: Optional[ft.Row] = None
        self._scroll_column: Optional[ft.Column] = None
        self._has_api_key: bool = False
        self._setup_mode: bool = False
        self._api_key_field: Optional[ft.TextField] = None

    def _reset_conversation(self) -> None:
        """Reset conversation state for a fresh chat session."""
        self._messages.clear()

    # ── Chat bubbles ───────────────────────────────────────────────────

    def _user_bubble(self, text: str) -> ft.Container:
        return ft.Container(
            content=ft.Text(text, size=FONT_SIZE_MD, color=COLORS["white"], selectable=True),
            bgcolor=COLORS["accent"],
            border_radius=BORDER_RADIUS_MD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            margin=ft.Margin.only(left=60, bottom=4),
            alignment=ft.Alignment(1, 0),
        )

    def _assistant_bubble(self, text: str) -> ft.Container:
        return ft.Container(
            content=ft.Markdown(
                text,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED,
            ),
            bgcolor=COLORS["card"],
            border_radius=BORDER_RADIUS_MD,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            margin=ft.Margin.only(right=60, bottom=4),
            alignment=ft.Alignment(-1, 0),
        )

    def _tool_action_chip(self, action: str, detail: str) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=14, color=COLORS["green"]),
                    ft.Text(f"{action}: {detail}", size=FONT_SIZE_XS, color=COLORS["green"]),
                ],
                spacing=4,
            ),
            bgcolor=COLORS["card"],
            border_radius=BORDER_RADIUS_MD,
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            margin=ft.Margin.only(right=60, bottom=2),
        )

    def _loading_indicator(self) -> ft.Row:
        return ft.Row(
            [ft.ProgressRing(width=16, height=16, stroke_width=2)],
            alignment=ft.MainAxisAlignment.START,
        )

    # ── Send flow ─────────────────────────────────────────────────────

    async def _on_send(self, e: Optional[ft.ControlEvent] = None) -> None:
        """Handle send button click or Enter key."""
        if not self._input_field:
            return
        text = (self._input_field.value or "").strip()
        if not text:
            return

        # Clear input and add user bubble
        self._input_field.value = ""
        self._add_bubble(self._user_bubble(text))

        # Add to conversation history
        self._messages.append({"role": "user", "content": text})

        # Show loading
        self._set_loading(True)

        try:
            response_text, tool_actions = await self.claude_service.chat(
                self._messages, self.state,
            )

            # Show tool action chips
            for action in tool_actions:
                self._add_bubble(self._tool_action_chip(action["action"], action["detail"]))

            # Show assistant response
            self._add_bubble(self._assistant_bubble(response_text))

            # Add to conversation history
            self._messages.append({"role": "assistant", "content": response_text})

        except ValueError as exc:
            # API key not configured
            self.snack.show(str(exc), COLORS["danger"])
        except Exception as exc:
            logger.exception("Chat error")
            error_msg = str(exc)
            if "401" in error_msg or "authentication" in error_msg.lower():
                error_msg = t("invalid_api_key")
            self.snack.show(f"{t('chat_error')}: {error_msg}", COLORS["danger"])
        finally:
            self._set_loading(False)

    def _add_bubble(self, bubble: ft.Control) -> None:
        """Add a chat bubble to the display column."""
        if self._chat_column:
            self._chat_column.controls.append(bubble)
            self._chat_column.update()
            # Scroll to bottom
            if self._scroll_column:
                self._scroll_column.scroll_to(offset=-1, duration=200)

    def _set_loading(self, loading: bool) -> None:
        """Show or hide the loading indicator."""
        if self._loading_row:
            self._loading_row.visible = loading
            self._loading_row.update()
        if self._send_btn:
            self._send_btn.disabled = loading
            self._send_btn.update()
        if self._input_field:
            self._input_field.disabled = loading
            self._input_field.update()

    # ── API key setup ─────────────────────────────────────────────────

    def _on_save_api_key(self, e: ft.ControlEvent) -> None:
        """Save the API key and switch to chat mode."""
        async def _save() -> None:
            if not self._api_key_field:
                return
            key = (self._api_key_field.value or "").strip()
            if not key:
                self.snack.show(t("api_key_required"), COLORS["danger"])
                return
            await save_api_key(key)
            self.snack.show(t("api_key_saved"), COLORS["green"])
            self._has_api_key = True
            self._setup_mode = False
            # Rebuild the view
            self.navigate(PageType.CHAT)

        self.page.run_task(_save)

    def _on_change_key_click(self, e: ft.ControlEvent) -> None:
        """Switch to API key setup mode."""
        self._setup_mode = True
        self.navigate(PageType.CHAT)

    def _build_setup_card(self) -> ft.Container:
        """Build the API key setup card."""
        self._api_key_field = ft.TextField(
            label=t("claude_api_key"),
            password=True,
            can_reveal_password=True,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
            label_style=ft.TextStyle(size=FONT_SIZE_SM),
        )

        # Pre-fill existing key if changing
        async def _load_key() -> None:
            existing = await load_api_key()
            if existing and self._api_key_field:
                self._api_key_field.value = existing
                self._api_key_field.update()

        self.page.run_task(_load_key)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.KEY, color=COLORS["accent"]),
                            ft.Text(t("claude_api_key"), weight="bold", size=16),
                        ],
                        spacing=10,
                    ),
                    ft.Text(
                        t("api_key_setup_desc"),
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                    ),
                    ft.Container(height=5),
                    self._api_key_field,
                    ft.Container(
                        content=accent_btn(t("save"), self._on_save_api_key),
                        alignment=ft.Alignment(1, 0),
                    ),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        )

    # ── Build ─────────────────────────────────────────────────────────

    def build(self) -> ft.Column:
        """Build the chat page layout.

        Both setup card and chat interface are built; an async check toggles
        visibility so the first render doesn't flash the wrong state.
        """
        self._reset_conversation()

        # Header
        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"],
        )

        change_key_btn = ft.IconButton(
            ft.Icons.KEY,
            on_click=self._on_change_key_click,
            icon_color=COLORS["done_text"],
            tooltip=t("change_api_key"),
            icon_size=18,
        )

        header = ft.Row(
            [
                back_btn,
                ft.Text(t("claude_chat"), size=24, weight="bold"),
                ft.Container(expand=True),
                change_key_btn,
            ],
        )

        # Setup card (hidden by default, shown if no key)
        setup_card = self._build_setup_card()
        setup_container = ft.Container(content=setup_card, visible=self._setup_mode)

        # Chat interface
        self._chat_column = ft.Column(
            spacing=SPACING_SM,
            controls=[],
        )

        self._loading_row = ft.Row(
            [ft.ProgressRing(width=16, height=16, stroke_width=2)],
            alignment=ft.MainAxisAlignment.START,
            visible=False,
        )

        self._scroll_column = ft.Column(
            controls=[self._chat_column, self._loading_row],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=SPACING_SM,
        )

        self._input_field = ft.TextField(
            hint_text=t("ask_claude"),
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
            expand=True,
            on_submit=lambda e: self.page.run_task(self._on_send),
            text_size=FONT_SIZE_MD,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        )

        self._send_btn = ft.IconButton(
            ft.Icons.SEND,
            icon_color=COLORS["accent"],
            on_click=lambda e: self.page.run_task(self._on_send),
            tooltip=t("send"),
        )

        input_row = ft.Row(
            [self._input_field, self._send_btn],
            spacing=SPACING_MD,
        )

        chat_container = ft.Column(
            [
                self._scroll_column,
                input_row,
            ],
            spacing=0,
            expand=True,
            visible=not self._setup_mode,
        )

        # Async key check — toggle visibility after DB round-trip
        async def _check_key() -> None:
            key = await load_api_key()
            self._has_api_key = bool(key)
            show_setup = self._setup_mode or not self._has_api_key
            setup_container.visible = show_setup
            chat_container.visible = not show_setup
            self.page.update()

        self.page.run_task(_check_key)

        return ft.Column(
            [
                header,
                ft.Divider(height=10, color="transparent"),
                setup_container,
                chat_container,
            ],
            spacing=0,
            expand=True,
        )
