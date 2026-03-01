import flet as ft
from datetime import date
from typing import Optional, List

from config import COLORS
from database import DatabaseError
from i18n import t
from models.entities import AppState, DailyNote
from services.daily_notes_service import DailyNoteService
from ui.helpers import SnackService


class NotesView:
    """Notes page showing today's editable note and a list of recent notes.

    Today's note has 3 states:
    - Placeholder (no note, not editing): tappable card
    - Editing: auto-growing text field, no preview/save buttons
    - Display (note exists, not editing): rendered markdown with edit icon
    """

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        daily_notes_service: DailyNoteService,
        snack: SnackService,
    ) -> None:
        self.page = page
        self.state = state
        self._svc = daily_notes_service
        self.snack = snack
        self._editing = False
        self._last_saved_content: Optional[str] = None
        self._recent_notes: List[DailyNote] = []
        self._expanded_date: Optional[date] = None
        self._build_controls()

    def _build_controls(self) -> None:
        # Placeholder card — shown when no note exists and not editing
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
            on_click=self._start_editing,
            ink=True,
            visible=True,
        )

        # Edit field — auto-growing, no fixed height
        self._note_field = ft.TextField(
            multiline=True,
            min_lines=3,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            hint_text=t("daily_note_hint"),
            visible=False,
        )

        # Markdown display — shown when note exists and not editing
        self._note_markdown = ft.Markdown(
            value="",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        )

        self._note_edit_btn = ft.IconButton(
            icon=ft.Icons.EDIT_OUTLINED,
            icon_color=COLORS["accent"],
            tooltip=t("edit"),
            visible=False,
            on_click=self._start_editing,
        )

        self._note_display = ft.Container(
            content=ft.Column(
                [self._note_markdown],
                scroll=ft.ScrollMode.AUTO,
            ),
            bgcolor=COLORS["input_bg"],
            border=ft.Border.all(1, COLORS["border"]),
            border_radius=8,
            padding=10,
            visible=False,
        )

        self._recent_list = ft.Column(controls=[], spacing=8)

        self._empty_recent = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.NOTES, size=48, color=COLORS["done_text"]),
                    ft.Text(t("no_notes_yet"), size=16, color=COLORS["done_text"], weight="bold"),
                    ft.Text(t("no_notes_yet_desc"), size=13, color=COLORS["done_text"]),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            alignment=ft.Alignment(0, 0),
            padding=ft.Padding.only(top=20),
            visible=True,
        )

    def _start_editing(self, e: Optional[ft.ControlEvent]) -> None:
        """Switch to editing state. Saves previous content first if needed."""
        self.save_if_editing()
        self._editing = True
        self._note_field.value = (
            self._note_markdown.value if self._note_display.visible else ""
        )
        self._placeholder.visible = False
        self._note_field.visible = True
        self._note_display.visible = False
        self._note_edit_btn.visible = False
        self.page.update()

    def _show_display(self, content: str) -> None:
        """Switch to display state — rendered markdown with edit button."""
        self._editing = False
        self._note_markdown.value = content
        self._note_display.visible = True
        self._note_edit_btn.visible = True
        self._note_field.visible = False
        self._placeholder.visible = False

    def _show_placeholder(self) -> None:
        """Switch to placeholder state — compact tappable card."""
        self._editing = False
        self._placeholder.visible = True
        self._note_field.visible = False
        self._note_display.visible = False
        self._note_edit_btn.visible = False

    def save_if_editing(self) -> None:
        """Save current note content if in editing state and content changed.

        Called from app.py before navigating away from notes page.
        """
        if not self._editing or self._svc is None:
            return

        content = (self._note_field.value or "").strip()
        if content == (self._last_saved_content or ""):
            # Content unchanged — just switch state without saving
            if content:
                self._show_display(content)
            else:
                self._show_placeholder()
            return

        async def _save() -> None:
            try:
                await self._svc.save_note(date.today(), content)
            except DatabaseError as err:
                self.snack.show(t("failed_to_save_note").format(error=err))
                return
            self._last_saved_content = content
            self.snack.show(t("daily_note_saved"))
            if content:
                self._show_display(content)
            else:
                self._show_placeholder()
            await self._load_recent_notes()
            self.page.update()

        self.page.run_task(_save)

    async def _load_today_note(self) -> None:
        if self._svc is None:
            return
        try:
            note = await self._svc.get_note(date.today())
        except DatabaseError:
            return

        if note and note.content.strip():
            self._last_saved_content = note.content.strip()
            self._show_display(note.content)
        else:
            self._last_saved_content = ""
            self._show_placeholder()

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
                continue  # Skip today's note — shown above
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

        if is_expanded:
            content_widget = ft.Markdown(
                value=note.content,
                selectable=True,
                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            )
        else:
            content_widget = ft.Text(
                preview_text,
                size=13,
                color=COLORS["done_text"],
                max_lines=2,
                overflow=ft.TextOverflow.ELLIPSIS,
            )

        return ft.Container(
            content=ft.Column(
                [
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
                    content_widget,
                ],
                spacing=6,
            ),
            padding=ft.Padding.all(12),
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
        if not self._editing:
            await self._load_today_note()
        await self._load_recent_notes()
        self.page.update()

    def build(self) -> ft.Column:
        today_section = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.EDIT_NOTE, color=COLORS["accent"], size=20),
                            ft.Text(t("todays_note"), size=16, weight="bold"),
                            ft.Container(expand=True),
                            self._note_edit_btn,
                        ],
                    ),
                    self._placeholder,
                    self._note_field,
                    self._note_display,
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=ft.Padding.symmetric(horizontal=4, vertical=10),
        )

        recent_section = ft.Column(
            [
                ft.Text(t("recent_notes"), size=14, weight="bold", color=COLORS["done_text"]),
                ft.Divider(height=8, color="transparent"),
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
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )
