import flet as ft
from datetime import date
from typing import Callable, List, Optional

from config import (
    COLORS, PageType, SPACING_SM, SPACING_MD, SPACING_XL,
    PADDING_LG, PADDING_XL, PADDING_3XL,
)
from database import DatabaseError
from i18n import t
from models.entities import AppState, DailyNote
from services.daily_notes_service import DailyNoteService
from ui.helpers import SnackService


class NotesView:
    """Notes list page — read-only view of today's note and recent notes.

    Tapping any note opens the full-screen NoteEditorView via navigate callback.
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
        self._recent_notes: List[DailyNote] = []
        self._expanded_date: Optional[date] = None
        self._build_controls()

    def _build_controls(self) -> None:
        self._placeholder = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.EDIT_NOTE, color=COLORS["accent"], size=20),
                    ft.Text(t("tap_to_write"), size=14, color=COLORS["done_text"]),
                    ft.Container(expand=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=COLORS["done_text"]),
                ],
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=14),
            border_radius=8,
            bgcolor=COLORS["card"],
            on_click=lambda e: self._open_editor(date.today()),
            ink=True,
            visible=True,
        )

        self._note_markdown = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        )

        self._note_display = ft.Container(
            content=ft.Column(
                [self._note_markdown],
                scroll=ft.ScrollMode.AUTO,
            ),
            bgcolor=COLORS["input_bg"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=8,
            padding=PADDING_LG,
            visible=False,
            on_click=lambda e: self._open_editor(date.today()),
            ink=True,
        )

        self._recent_list = ft.Column(controls=[], spacing=SPACING_MD)

        self._empty_recent = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.NOTES, size=48, color=COLORS["done_text"]),
                    ft.Text(t("no_notes_yet"), size=16, color=COLORS["done_text"], weight="bold"),
                    ft.Text(t("no_notes_yet_desc"), size=13, color=COLORS["done_text"]),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_MD,
            ),
            alignment=ft.Alignment(0, 0),
            padding=ft.Padding.only(top=PADDING_3XL),
            visible=True,
        )

    def _open_editor(self, note_date: date) -> None:
        self.state.editing_note_date = note_date
        self.navigate(PageType.NOTE_EDITOR)

    async def _load_today_note(self) -> None:
        if self._svc is None:
            return
        try:
            note = await self._svc.get_note(date.today())
        except DatabaseError:
            return

        if note and note.content.strip():
            self._note_markdown.value = note.content
            self._note_display.visible = True
            self._placeholder.visible = False
        else:
            self._note_display.visible = False
            self._placeholder.visible = True

    async def _load_recent_notes(self) -> None:
        if self._svc is None:
            return
        try:
            self._recent_notes = await self._svc.get_recent_notes(limit=50)
        except DatabaseError:
            self._recent_notes = []

        today = date.today()
        self._recent_list.controls.clear()
        for note in self._recent_notes:
            if note.date == today:
                continue
            if not note.content.strip():
                continue
            self._recent_list.controls.append(self._build_note_card(note))
        self._empty_recent.visible = len(self._recent_list.controls) == 0

    def _build_note_card(self, note: DailyNote) -> ft.Container:
        is_expanded = self._expanded_date == note.date
        preview_text = note.content[:120].replace("\n", " ")
        if len(note.content) > 120:
            preview_text += "..."

        date_label = note.date.strftime("%A, %b %d, %Y")

        children: List[ft.Control] = [
            ft.Row(
                [
                    ft.Icon(ft.Icons.CALENDAR_TODAY, size=14, color=COLORS["accent"]),
                    ft.Text(date_label, size=13, weight="bold"),
                    ft.Container(expand=True),
                    ft.Icon(
                        ft.Icons.EXPAND_LESS if is_expanded else ft.Icons.EXPAND_MORE,
                        size=18,
                        color=COLORS["done_text"],
                    ),
                ],
            ),
        ]

        if is_expanded:
            children.append(ft.Markdown(
                value=note.content,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            ))
            children.append(ft.Row(
                [
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.EDIT_OUTLINED,
                        icon_color=COLORS["accent"],
                        tooltip=t("edit"),
                        icon_size=18,
                        on_click=lambda e, n=note: self._open_editor(n.date),
                    ),
                ],
                spacing=0,
            ))
        else:
            children.append(ft.Text(
                preview_text,
                size=13,
                color=COLORS["done_text"],
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
            ))

        return ft.Container(
            content=ft.Column(children, spacing=SPACING_SM),
            padding=ft.Padding.all(PADDING_XL),
            border_radius=8,
            bgcolor=COLORS["card"],
            on_click=lambda e, d=note.date: self._toggle_expand(d),
            ink=True,
        )

    def _toggle_expand(self, note_date: date) -> None:
        if self._expanded_date == note_date:
            self._expanded_date = None
        else:
            self._expanded_date = note_date
        self.page.run_task(self._rebuild_recent)

    async def _rebuild_recent(self) -> None:
        today = date.today()
        self._recent_list.controls.clear()
        for note in self._recent_notes:
            if note.date == today:
                continue
            if not note.content.strip():
                continue
            self._recent_list.controls.append(self._build_note_card(note))
        self._empty_recent.visible = len(self._recent_list.controls) == 0
        self.page.update()

    def refresh(self) -> None:
        self.page.run_task(self._refresh_async)

    async def _refresh_async(self) -> None:
        await self._load_today_note()
        await self._load_recent_notes()
        self.page.update()

    def build(self) -> ft.Column:
        today_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(t("todays_note"), size=16, weight="bold"),
                    self._placeholder,
                    self._note_display,
                ],
                spacing=SPACING_MD,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=10),
        )

        recent_section = ft.Column(
            [
                ft.Text(t("recent_notes"), size=14, weight="bold", color=COLORS["done_text"]),
                ft.Divider(height=SPACING_MD, color="transparent"),
                self._empty_recent,
                self._recent_list,
            ],
        )

        return ft.Column(
            controls=[
                today_section,
                ft.Divider(color=COLORS["border"]),
                recent_section,
            ],
            spacing=SPACING_XL,
            scroll=ft.ScrollMode.AUTO,
        )
