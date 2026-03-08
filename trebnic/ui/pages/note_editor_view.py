import asyncio
import json
import logging

import flet as ft
from datetime import date
from typing import Callable, Optional

import httpx

try:
    from flet_stt import FletStt, SttError
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False
    SttError = None

from config import COLORS, PageType, FONT_SIZE_LG, FONT_SIZE_2XL, SPACING_LG
from database import DatabaseError
from i18n import t
from models.entities import AppState
from services.claude_service import load_api_key, refine_note
from services.daily_notes_service import DailyNoteService
from ui.dialogs.base import open_dialog
from ui.helpers import SnackService, danger_btn, friendly_http_error

logger = logging.getLogger(__name__)


class NoteEditorView:
    """Full-screen note editor page.

    Follows the same pattern as TimeEntriesView: reads context from AppState
    (editing_note_date), builds header + content, navigates back on completion.
    Auto-saves on back if content changed.
    """

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        daily_notes_service: DailyNoteService,
        snack: SnackService,
        navigate: Callable[[PageType], None],
    ) -> None:
        self.page = page
        self.state = state
        self._svc = daily_notes_service
        self.snack = snack
        self.navigate = navigate
        self._note_field: Optional[ft.TextField] = None
        self._refine_field: Optional[ft.TextField] = None
        self._refine_btn: Optional[ft.IconButton] = None
        self._original_content: str = ""

        # Speech-to-text for refine field
        self._stt_initialized: bool = False
        self._stt_listening: bool = False
        self._mic_btn: Optional[ft.IconButton] = None

        if STT_AVAILABLE:
            self._stt = FletStt(
                on_result=self._on_stt_result,
                on_error=self._on_stt_error,
                on_status=self._on_stt_status,
            )
            self.page.services.append(self._stt)
        else:
            self._stt: Optional[FletStt] = None

    def build(self) -> ft.Column:
        note_date = self.state.editing_note_date or date.today()
        is_today = note_date == date.today()

        title = t("todays_note") if is_today else note_date.strftime("%A, %b %d, %Y")

        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self._go_back(),
            icon_color=COLORS["accent"],
        )

        header_controls = [
            back_btn,
            ft.Text(
                title,
                size=FONT_SIZE_2XL if not self.state.is_mobile else FONT_SIZE_LG,
                weight="bold",
                expand=True,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        ]

        if not is_today:
            header_controls.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=COLORS["danger"],
                    tooltip=t("delete"),
                    on_click=lambda e: self._confirm_delete(note_date),
                ),
            )

        header = ft.Row(
            header_controls,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self._note_field = ft.TextField(
            multiline=True,
            min_lines=14,
            expand=True,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            hint_text=t("daily_note_hint"),
            autofocus=True,
        )

        self._refine_field = ft.TextField(
            hint_text=t("refine_hint"),
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            expand=True,
            text_size=13,
            multiline=True,
            min_lines=1,
            max_lines=4,
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            on_submit=lambda e: self.page.run_task(self._refine_async),
        )
        self._refine_btn = ft.IconButton(
            icon=ft.Icons.SEND,
            icon_color=COLORS["accent"],
            tooltip=t("refine_hint"),
            on_click=self._on_refine_tap,
        )
        self._mic_btn = ft.IconButton(
            icon=ft.Icons.MIC,
            icon_color=COLORS["accent"],
            tooltip=t("voice_input"),
            on_click=self._on_mic_tap,
        )

        refine_controls = [self._refine_field, self._mic_btn, self._refine_btn]
        refine_row = ft.Row(
            refine_controls,
            spacing=8,
        )

        # Check API key availability — show red hint if missing
        async def _check_api_key() -> None:
            key = await load_api_key()
            if not key and self._refine_field:
                self._refine_field.hint_text = t("api_key_required")
                self._refine_field.border_color = COLORS["danger"]
                self._refine_field.hint_style = ft.TextStyle(color=COLORS["danger"])
                self._refine_btn.disabled = True
                self._mic_btn.disabled = True
                self.page.update()
        self.page.run_task(_check_api_key)

        return ft.Column(
            [
                header,
                ft.Divider(height=SPACING_LG, color="transparent"),
                self._note_field,
                refine_row,
            ],
            spacing=SPACING_LG,
            expand=True,
        )

    def refresh(self) -> None:
        self.page.run_task(self._refresh_async)

    async def _refresh_async(self) -> None:
        note_date = self.state.editing_note_date or date.today()
        try:
            note = await self._svc.get_note(note_date)
        except DatabaseError:
            note = None

        content = note.content.strip() if note and note.content else ""
        self._original_content = content
        if self._note_field:
            self._note_field.value = content
        self.page.update()

    async def save_if_changed(self) -> None:
        """Save note if content differs from the original. Called on back and on navigate-away."""
        if self._note_field is None:
            return
        current = (self._note_field.value or "").strip()
        if current == self._original_content:
            return
        note_date = self.state.editing_note_date or date.today()
        try:
            await self._svc.save_note(note_date, current)
        except DatabaseError as err:
            self.snack.show(t("failed_to_save_note").format(error=err))
            return
        self._original_content = current
        self.snack.show(t("daily_note_saved"))

    # ── Speech-to-text ────────────────────────────────────────────────

    def _on_stt_result(self, e: ft.ControlEvent) -> None:
        data = json.loads(e.data)
        if self._refine_field:
            self._refine_field.value = data.get("text", "")
            self._refine_field.update()
        if data.get("final", False):
            self._set_mic_state(False)

    def _on_stt_error(self, e: ft.ControlEvent) -> None:
        data = json.loads(e.data)
        logger.error("STT error (note editor): %s", data)
        self._set_mic_state(False)
        error_msg = data.get("error", "")
        if error_msg:
            self.snack.show(f"{t('stt_error')}: {error_msg}", COLORS["danger"])

    def _on_stt_status(self, e: ft.ControlEvent) -> None:
        data = json.loads(e.data)
        listening = data.get("status", "") == "listening"
        self._set_mic_state(listening)

    def _set_mic_state(self, listening: bool) -> None:
        self._stt_listening = listening
        if self._mic_btn:
            self._mic_btn.icon = ft.Icons.STOP_CIRCLE if listening else ft.Icons.MIC
            self._mic_btn.icon_color = COLORS["danger"] if listening else COLORS["accent"]
            self._mic_btn.update()

    async def _on_mic_tap(self, e: Optional[ft.ControlEvent] = None) -> None:
        if not STT_AVAILABLE:
            self.snack.show(t("stt_not_available"), COLORS["danger"])
            return
        try:
            if self._stt_listening:
                await self._stt.stop()
                return

            self._set_mic_state(True)

            if not self._stt_initialized:
                try:
                    available = await asyncio.wait_for(self._stt.initialize(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._set_mic_state(False)
                    self.snack.show(t("stt_not_available"), COLORS["danger"])
                    return
                if not available:
                    self._set_mic_state(False)
                    self.snack.show(t("stt_not_available"), COLORS["danger"])
                    return
                self._stt_initialized = True

            await self._stt.listen(partial_results=True, listen_mode="dictation", on_device=False)
        except SttError as exc:
            logger.error("STT SttError (note editor): %s", exc)
            self._set_mic_state(False)
            self.snack.show(f"{t('stt_error')}: {exc}", COLORS["danger"])
        except Exception as exc:
            logger.exception("STT mic tap error (note editor)")
            self._set_mic_state(False)
            self.snack.show(f"{t('stt_error')}: {exc}", COLORS["danger"])

    async def _on_refine_tap(self, e: Optional[ft.ControlEvent] = None) -> None:
        await self._refine_async()

    async def _refine_async(self) -> None:
        content = (self._note_field.value or "").strip()
        instruction = (self._refine_field.value or "").strip()
        if not instruction:
            self.snack.show(t("refine_hint"))
            return
        if not content:
            self.snack.show(t("note_empty_for_refine"), COLORS["danger"])
            return
        self._refine_btn.disabled = True
        self._refine_field.hint_text = t("refining_note")
        self.page.update()
        try:
            refined = await refine_note(content, instruction)
            self._note_field.value = refined
            self._refine_field.value = ""
        except ValueError as err:
            self.snack.show(str(err))
        except (httpx.HTTPStatusError, httpx.TimeoutException) as err:
            self.snack.show(friendly_http_error(err), COLORS["danger"])
        finally:
            self._refine_btn.disabled = False
            self._refine_field.hint_text = t("refine_hint")
            self.page.update()

    def _go_back(self) -> None:
        async def _back_async() -> None:
            await self.save_if_changed()
            self.state.editing_note_date = None
            self.navigate(PageType.NOTES)

        self.page.run_task(_back_async)

    def _confirm_delete(self, note_date: date) -> None:
        date_label = note_date.strftime("%A, %b %d, %Y")

        def do_delete(e: ft.ControlEvent) -> None:
            async def _delete_async() -> None:
                try:
                    await self._svc.delete_note(note_date)
                except DatabaseError as err:
                    self.snack.show(t("failed_to_delete_note").format(error=err))
                    return
                close()
                self.snack.show(t("daily_note_deleted"))
                self.state.editing_note_date = None
                self.navigate(PageType.NOTES)

            self.page.run_task(_delete_async)

        content = ft.Text(t("delete_note_confirm").format(date=date_label))
        _, close = open_dialog(
            self.page,
            t("delete"),
            content,
            lambda c: [
                ft.TextButton(t("cancel"), on_click=c),
                danger_btn(t("delete"), do_delete),
            ],
        )
