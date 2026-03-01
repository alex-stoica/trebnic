import flet as ft
from datetime import date, timedelta
from typing import Callable, List, Optional, Set, Tuple

from config import COLORS, CALENDAR_HEADER_HEIGHT, DIALOG_WIDTH_XL
from database import DatabaseError
from i18n import t
from models.entities import AppState, Task
from services.daily_notes_service import DailyNoteService
from ui.helpers import SnackService
from ui.dialogs.base import open_dialog


class CalendarView:
    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        daily_notes_service: DailyNoteService,
        snack: SnackService,
        on_update: Optional[Callable[[], None]] = None,
        on_open_notes: Optional[Callable] = None,
    ) -> None:
        self.page = page
        self.state = state
        self._daily_notes_svc = daily_notes_service
        self._snack = snack
        self.on_update = on_update
        self._on_open_notes = on_open_notes
        self._note_dates: Set[date] = set()

    def get_visible_range(self) -> Tuple[date, date]:
        """Return (start, end) dates for the currently visible calendar window."""
        today = date.today()
        if self.state.is_mobile:
            start = today - timedelta(days=1) + timedelta(days=self.state.calendar_offset * 4)
            end = start + timedelta(days=3)
        else:
            week_start = today - timedelta(days=today.weekday())
            start = week_start + timedelta(weeks=self.state.calendar_offset)
            end = start + timedelta(days=6)
        return start, end

    def _open_daily_note(self, note_date: date) -> None:
        """Open a read-only dialog for a daily note. For today, offer 'Edit in notes' button."""
        md = ft.Markdown(
            value=f"*{t('no_note_yet')}*",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        )

        content = ft.Container(
            width=DIALOG_WIDTH_XL,
            content=ft.Column(
                [md],
                tight=True,
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        )

        is_today = note_date == date.today()
        date_str = note_date.strftime("%b %d, %Y")

        def go_to_notes(e: ft.ControlEvent) -> None:
            close(e)
            if self._on_open_notes:
                self._on_open_notes()

        def make_actions(close_fn: Callable) -> list:
            actions = [ft.TextButton(t("close"), on_click=close_fn)]
            if is_today and self._on_open_notes:
                actions.append(ft.TextButton(t("edit_in_notes"), icon=ft.Icons.EDIT, on_click=go_to_notes))
            return actions

        _, close = open_dialog(
            self.page,
            f"{t('daily_note')} - {date_str}",
            content,
            make_actions,
        )

        # Load existing note content
        async def _load() -> None:
            try:
                note = await self._daily_notes_svc.get_note(note_date)
            except DatabaseError:
                return
            if note and note.content.strip():
                md.value = note.content
            self.page.update()

        self.page.run_task(_load)

    def _get_tasks_for_date(self, d: date) -> Tuple[List[Task], List[Task]]:
        pending = [task for task in self.state.tasks if task.due_date == d]
        done = [task for task in self.state.done_tasks if task.due_date == d]
        return pending, done

    def _create_chip(self, task: Task, is_done: bool = False, is_mobile: bool = False) -> ft.Container:
        project = self.state.get_project_by_id(task.project_id)
        color = project.color if project else COLORS["unassigned"]
        chip_text_size = 12 if is_mobile else 9

        if is_done:
            return ft.Container(
                content=ft.Text(
                    task.title,
                    size=chip_text_size,
                    max_lines=3,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH),
                    color=COLORS["done_text"],
                ),
                bgcolor=COLORS["done_bg"],
                padding=ft.Padding.symmetric(horizontal=4, vertical=2),
                border_radius=4,
                margin=ft.Margin.only(bottom=2),
            )

        return ft.Container(
            content=ft.Text(
                task.title,
                size=chip_text_size,
                max_lines=3,
                overflow=ft.TextOverflow.ELLIPSIS,
                color=COLORS["white"],
            ),
            bgcolor=color,
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            border_radius=4,
            margin=ft.Margin.only(bottom=2),
        )

    def _create_day_column(
        self, d: date, today: date, is_mobile: bool = False,
    ) -> ft.Container:
        day_names = [
            t("day_mon"), t("day_tue"), t("day_wed"), t("day_thu"),
            t("day_fri"), t("day_sat"), t("day_sun"),
        ]
        pending, done = self._get_tasks_for_date(d)
        has_note = d in self._note_dates

        is_today = d == today
        is_past = d < today
        is_weekend = d.weekday() >= 5

        items = [self._create_chip(t, is_mobile=is_mobile) for t in pending]
        items.extend([self._create_chip(t, True, is_mobile=is_mobile) for t in done])

        # Weekend headers get a faint warm tint when not today/past
        if is_today:
            header_bg = COLORS["accent"]
        elif is_past:
            header_bg = COLORS["done_bg"]
        elif is_weekend:
            header_bg = "#332d2d"
        else:
            header_bg = COLORS["card"]
        header_color = COLORS["white"] if is_today else COLORS["done_text"]

        day_name_size = 11 if is_mobile else 9
        day_num_size = 16 if is_mobile else 14
        note_icon_size = 12 if is_mobile else 10

        weekday_idx = d.weekday()
        header_controls = [
            ft.Text(day_names[weekday_idx], size=day_name_size, color=header_color),
            ft.Text(str(d.day), size=day_num_size, weight="bold", color=header_color),
        ]

        if has_note:
            header_controls.append(
                ft.Icon(ft.Icons.STICKY_NOTE_2_OUTLINED, size=note_icon_size, color=header_color),
            )

        header = ft.Container(
            content=ft.Column(
                header_controls,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            bgcolor=header_bg,
            padding=ft.Padding.symmetric(horizontal=4, vertical=6),
            border_radius=6,
            height=CALENDAR_HEADER_HEIGHT,
            alignment=ft.Alignment(0, 0),
            on_click=lambda e, day=d: self._open_daily_note(day),
            ink=True,
        )

        content_control = (
            ft.Column(items, scroll=ft.ScrollMode.AUTO, spacing=2)
            if items
            else ft.Text(
                "\u2014",
                size=10,
                color=COLORS["done_text"],
                text_align=ft.TextAlign.CENTER,
            )
        )

        content = ft.Container(
            content=content_control,
            padding=4,
            expand=True,
            alignment=ft.Alignment(0, -1),
        )

        # Weekend columns get a slightly lighter border
        if is_today:
            border_color = COLORS["accent"]
        elif is_weekend:
            border_color = "#3a3a3a"
        else:
            border_color = COLORS["border"]

        return ft.Container(
            content=ft.Column(
                [header, content],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            expand=True,
            border=ft.Border.all(1, border_color),
            border_radius=6,
        )

    def _navigate(self, delta: int) -> None:
        """Navigate forward or backward by one window (7 days on desktop, 4 on mobile)."""
        self.state.calendar_offset += delta
        if self.on_update:
            self.on_update()

    async def _load_note_dates(self, start: date, end: date) -> None:
        """Load which dates have daily notes for the visible range."""
        try:
            self._note_dates = await self._daily_notes_svc.get_dates_with_notes(start, end)
        except DatabaseError:
            self._note_dates = set()

    def build(self) -> ft.Column:
        today = date.today()
        is_mobile = self.state.is_mobile
        start, end = self.get_visible_range()
        num_days = 4 if is_mobile else 7
        days = [start + timedelta(days=i) for i in range(num_days)]

        date_range = f"{days[0].strftime('%b %d')} - {days[-1].strftime('%b %d, %Y')}"

        nav_controls = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_LEFT,
                    icon_color=COLORS["accent"],
                    tooltip=t("previous_week"),
                    on_click=lambda e: self._navigate(-1),
                ),
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_RIGHT,
                    icon_color=COLORS["accent"],
                    tooltip=t("next_week"),
                    on_click=lambda e: self._navigate(1),
                ),
            ],
            spacing=0,
            tight=True,
        )

        header_row = ft.Row(
            [
                ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK, color=COLORS["accent"], size=20),
                ft.Text(t("calendar"), size=16, weight="bold"),
                ft.Container(expand=True),
                ft.Text(date_range, color=COLORS["done_text"], size=11),
                nav_controls,
            ],
            spacing=4,
        )

        day_columns = [self._create_day_column(d, today, is_mobile) for d in days]

        calendar_row = ft.Row(
            day_columns,
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        calendar_container = ft.Container(
            content=calendar_row,
            expand=True,
            padding=ft.Padding.only(top=10),
        )

        return ft.Column([header_row, calendar_container], expand=True)
