import flet as ft
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional, List
from weakref import WeakKeyDictionary

from config import (
    COLORS,
    DIALOG_WIDTH_SM,
    DIALOG_WIDTH_MD,
    DIALOG_WIDTH_LG,
    DATE_PICKER_YEARS,
    BORDER_RADIUS,
    SPACING_XS,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    SPACING_XL,
    SPACING_2XL,
    PADDING_SM,
    PADDING_MD,
    PADDING_LG,
    PADDING_XL,
    PADDING_2XL,
    PageType,
    RecurrenceFrequency,
    NavItem,
)
from models.entities import Task, AppState, TimeEntry
from services.logic import TaskService
from services.time_entry_service import TimeEntryService
from ui.formatters import TimeFormatter
from ui.helpers import accent_btn, danger_btn, SnackService
from ui.dialogs.base import open_dialog, create_option_item
from ui.dialogs.dialog_state import RecurrenceState
from ui.components.duration_knob import DurationKnob
from events import event_bus, AppEvent
from i18n import t


class DatePickerManager:
    """Manages DatePicker instances to prevent overlay memory leaks.

    Instead of creating new DatePickers for each dialog, this manager reuses
    a single picker per page and properly cleans up when pages are disposed.
    Uses WeakKeyDictionary with page objects as keys - this automatically
    removes entries when pages are garbage collected, avoiding the fragile
    id(page) approach where IDs can be reused after GC.
    """

    _instance: Optional["DatePickerManager"] = None
    _pickers: WeakKeyDictionary  # page -> picker (auto-cleanup on page GC)

    def __new__(cls) -> "DatePickerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pickers = WeakKeyDictionary()
        return cls._instance

    def get_picker(
        self,
        page: ft.Page,
        first_date: Optional[date] = None,
        last_date: Optional[date] = None,
    ) -> ft.DatePicker:
        """Get or create a DatePicker for the given page.

        Args:
            page: The Flet page
            first_date: Minimum selectable date (default: today)
            last_date: Maximum selectable date (default: 5 years from today)

        Returns:
            A DatePicker instance attached to the page's overlay
        """
        # Check if we have a valid picker for this page
        picker = self._pickers.get(page)
        if picker is not None:
            # Verify the picker is still in the overlay
            if picker in page.overlay:
                return picker
            # Picker was removed from overlay, create a new one

        # Create new picker
        picker = ft.DatePicker(
            first_date=first_date or date.today(),
            last_date=last_date or date.today() + timedelta(days=365 * 5),
        )
        page.overlay.append(picker)

        # Store reference (auto-cleanup when page is GC'd via WeakKeyDictionary)
        self._pickers[page] = picker

        return picker

    def remove_picker(self, page: ft.Page) -> None:
        """Explicitly remove the picker for a page."""
        picker = self._pickers.pop(page, None)
        if picker and picker in page.overlay:
            page.overlay.remove(picker)


# Module-level singleton
_picker_manager = DatePickerManager()


def get_date_picker(page: ft.Page) -> ft.DatePicker:
    """Get a reusable DatePicker for the given page.

    Public wrapper around _picker_manager to avoid importing the private singleton.
    """
    return _picker_manager.get_picker(
        page,
        first_date=date.today(),
        last_date=date.today() + timedelta(days=365 * DATE_PICKER_YEARS),
    )


class RecurrenceDialogController:
    """Controller for the recurrence dialog."""

    def __init__(
        self,
        page: ft.Page,
        state: RecurrenceState,
        on_save: Callable[[], None],
        on_close: Callable[[], None],
    ) -> None:
        self.page = page
        self.state = state
        self.on_save = on_save
        self.on_close = on_close
        self._build_controls()

    def _build_controls(self) -> None:
        """Build all dialog controls."""
        weekday_labels = [
            t("recurrence_day_mon"), t("recurrence_day_tue"),
            t("recurrence_day_wed"), t("recurrence_day_thu"),
            t("recurrence_day_fri"), t("recurrence_day_sat"),
            t("recurrence_day_sun"),
        ]
        self.weekday_cbs = [
            ft.Checkbox(
                label=d,
                value=self.state.weekdays[i],
                scale=0.85,
                on_change=lambda e, idx=i: self._on_weekday_change(e, idx),
            )
            for i, d in enumerate(weekday_labels)
        ]

        self.weekdays_section = ft.Column(
            [
                ft.Text(t("on_these_days"), weight="bold", size=13),
                ft.Row(self.weekday_cbs[:4], spacing=0),
                ft.Row(self.weekday_cbs[4:], spacing=0),
            ],
            visible=self.state.frequency == RecurrenceFrequency.WEEKS,
            spacing=SPACING_MD,
        )

        self.freq_dd = ft.Dropdown(
            value=self.state.frequency.value,
            options=[
                ft.dropdown.Option(RecurrenceFrequency.DAYS.value, t("freq_days")),
                ft.dropdown.Option(RecurrenceFrequency.WEEKS.value, t("freq_weeks")),
                ft.dropdown.Option(RecurrenceFrequency.MONTHS.value, t("freq_months")),
            ],
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            width=120,
            on_select=self._on_freq_change,
        )

        self.interval_field = ft.TextField(
            value=str(self.state.interval),
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            width=50,
            text_align=ft.TextAlign.CENTER,
            on_change=self._on_interval_change,
        )

        self.enable_switch = ft.Switch(
            value=self.state.enabled,
            label=t("enable_recurrence"),
            on_change=self._on_enable_change,
        )

        default_end = self.state.end_date or (date.today() + timedelta(days=90))
        self.end_date_text = ft.Text(
            default_end.strftime("%b %d, %Y"),
            color=COLORS["accent"],
        )

        self.end_date_btn = ft.Container(
            content=self.end_date_text,
            on_click=self._open_end_date_picker,
            ink=True,
            padding=ft.Padding.symmetric(horizontal=PADDING_MD, vertical=PADDING_SM),
            border_radius=4,
        )

        self.end_type_group = ft.RadioGroup(
            value=self.state.end_type,
            on_change=self._on_end_type_change,
            content=ft.Column(
                [
                    ft.Radio(value="never", label=t("never")),
                    ft.Row(
                        [
                            ft.Radio(value="on_date", label=t("on_date")),
                            self.end_date_btn,
                        ],
                        spacing=SPACING_MD,
                    ),
                ],
                spacing=SPACING_MD,
            ),
        )

        self.from_completion_switch = ft.Switch(
            value=self.state.from_completion,
            label=t("recur_from_completion"),
            on_change=self._on_from_completion_change,
        )

    def _on_weekday_change(self, e: ft.ControlEvent, idx: int) -> None:
        """Handle weekday checkbox change."""
        self.state.weekdays[idx] = e.control.value

    def _on_freq_change(self, e: ft.ControlEvent) -> None:
        """Handle frequency dropdown change."""
        try:
            self.state.frequency = RecurrenceFrequency(e.control.value)
        except ValueError:
            self.state.frequency = RecurrenceFrequency.WEEKS
        self.weekdays_section.visible = (
            self.state.frequency == RecurrenceFrequency.WEEKS
        )
        self.page.update()

    def _on_interval_change(self, e: ft.ControlEvent) -> None:
        """Handle interval field change."""
        try:
            self.state.interval = int(e.control.value or 1)
        except ValueError:
            self.state.interval = 1

    def _on_enable_change(self, e: ft.ControlEvent) -> None:
        """Handle enable switch change."""
        self.state.enabled = e.control.value

    def _on_end_type_change(self, e: ft.ControlEvent) -> None:
        """Handle end type radio change."""
        self.state.end_type = e.control.value
        if self.state.end_type == "on_date" and self.state.end_date is None:
            self.state.end_date = date.today() + timedelta(days=90)

    def _on_from_completion_change(self, e: ft.ControlEvent) -> None:
        """Handle from completion switch change."""
        self.state.from_completion = e.control.value

    def _open_end_date_picker(self, e: ft.ControlEvent) -> None:
        """Open the end date picker.

        Uses DatePickerManager to reuse pickers and prevent overlay memory leaks.
        """
        picker = _picker_manager.get_picker(
            self.page,
            first_date=date.today(),
            last_date=date.today() + timedelta(days=365 * 5),
        )

        # Update handler for this specific dialog instance
        picker.on_change = self._on_end_date_change
        picker.value = self.state.end_date or date.today()
        picker.open = True
        self.page.update()

    def _on_end_date_change(self, e: ft.ControlEvent) -> None:
        """Handle end date picker change."""
        if e.control.value:
            self.state.end_date = e.control.value.date()
            self.end_date_text.value = self.state.end_date.strftime("%b %d, %Y")
            self.end_type_group.value = "on_date"
            self.state.end_type = "on_date"
            self.page.update()

    def save(self, e: ft.ControlEvent) -> None:
        """Save the recurrence settings."""
        try:
            self.state.interval = int(self.interval_field.value or 1)
        except ValueError:
            self.state.interval = 1
        self.state.apply_to_task()
        self.on_save()
        self.on_close(e)

    def build_content(self) -> ft.Container:
        """Build the dialog content."""
        return ft.Container(
            width=DIALOG_WIDTH_LG,
            height=350,
            content=ft.Column(
                [
                    self.enable_switch,
                    ft.Divider(height=SPACING_2XL, color=COLORS["border"]),
                    ft.Text(t("frequency_label"), weight="bold", size=13),
                    ft.Row(
                        [
                            ft.Text(t("repeat_every"), size=13),
                            self.interval_field,
                            self.freq_dd,
                        ],
                        spacing=SPACING_MD,
                    ),
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    self.weekdays_section,
                    ft.Divider(height=SPACING_2XL, color=COLORS["border"]),
                    ft.Text(t("behavior"), weight="bold", size=13),
                    self.from_completion_switch,
                    ft.Text(
                        t("from_completion_explanation"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                    ft.Divider(height=SPACING_2XL, color=COLORS["border"]),
                    ft.Text(t("ends"), weight="bold", size=13),
                    self.end_type_group,
                ],
                spacing=SPACING_LG,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )


class TaskDialogs:
    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        task_service: TaskService,
        time_entry_service: TimeEntryService,
        snack: SnackService,
        navigate: Callable[[PageType], None] = None,
    ) -> None:
        self.page = page
        self.state = state
        self.task_service = task_service
        self.time_entry_service = time_entry_service
        self.snack = snack
        self.navigate = navigate

    def _get_date_change_message(self, new_date: Optional[date]) -> str:
        """Get an appropriate message when a task's date changes.

        Tells the user where to find the task based on the new date
        and current navigation selection.
        """
        today = date.today()
        current_nav = self.state.selected_nav

        if new_date is None:
            if current_nav == NavItem.INBOX:
                return t("due_date_cleared")
            return t("task_moved_to_draft")
        elif new_date <= today:
            date_str = new_date.strftime('%b %d')
            if current_nav == NavItem.TODAY:
                return t("date_set_to").replace("{date}", date_str)
            return t("date_set_to_see_today").replace("{date}", date_str)
        else:
            date_str = new_date.strftime('%b %d')
            if current_nav == NavItem.TODAY and self.state.task_filter.value == "next":
                return t("date_set_to").replace("{date}", date_str)
            return t("date_set_to_see_upcoming").replace("{date}", date_str)

    def rename(self, task: Task) -> None:
        error = ft.Text("", color=COLORS["danger"], size=12, visible=False)
        field = ft.TextField(
            value=task.title,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            autofocus=True,
        )

        def save(e: ft.ControlEvent) -> None:
            name = field.value.strip()
            if not name:
                return
            if self.task_service.task_name_exists(name, task):
                error.value = t("task_name_exists")
                error.visible = True
                self.page.update()
                return

            async def _save() -> None:
                await self.task_service.rename_task(task, name)
                self.snack.show(t("renamed_to").replace("{name}", name))
                close(e)
                event_bus.emit(AppEvent.TASK_RENAMED, task)
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_save)

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column([field, error], tight=True, spacing=SPACING_SM),
        )

        _, close = open_dialog(
            self.page,
            t("rename_task"),
            content,
            lambda c: [ft.TextButton(t("cancel"), on_click=c), accent_btn(t("save"), save)],
        )

    def assign_project(self, task: Task) -> None:
        def select(pid: Optional[str]) -> None:
            async def _select() -> None:
                await self.task_service.assign_project(task, pid)
                p = self.state.get_project_by_id(pid)
                name = p.name if p else t("unassigned")
                self.snack.show(t("task_assigned_to").replace("{name}", name))
                close()
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_select)

        opts: List[ft.Control] = []
        for p in self.state.projects:
            is_sel = task.project_id == p.id
            check_icon = (
                ft.Icon(ft.Icons.CHECK, color=COLORS["accent"], size=18)
                if is_sel else ft.Container(width=18)
            )
            row = ft.Row(
                [
                    ft.Text(p.icon, size=18),
                    ft.Text(p.name, size=14, expand=True),
                    check_icon,
                ],
                spacing=SPACING_XL,
            )
            container = ft.Container(
                content=row,
                padding=ft.Padding.symmetric(vertical=PADDING_LG, horizontal=PADDING_2XL),
                border_radius=8,
                ink=True,
                on_click=lambda e, pid=p.id: select(pid),
            )
            opts.append(container)

        opts.append(ft.Divider(height=1, color=COLORS["border"]))

        unassign_row = ft.Row(
            [
                ft.Icon(ft.Icons.CLOSE, color=COLORS["done_text"], size=18),
                ft.Text(t("unassign"), size=14, color=COLORS["done_text"]),
            ],
            spacing=SPACING_XL,
        )
        unassign_container = ft.Container(
            content=unassign_row,
            padding=ft.Padding.symmetric(vertical=PADDING_LG, horizontal=PADDING_2XL),
            border_radius=8,
            ink=True,
            on_click=lambda e: select(None),
        )
        opts.append(unassign_container)

        content = ft.Container(
            width=DIALOG_WIDTH_SM,
            content=ft.Column(opts, tight=True, spacing=SPACING_SM),
        )

        _, close = open_dialog(
            self.page,
            t("assign_to_project"),
            content,
            lambda c: [ft.TextButton(t("cancel"), on_click=c)],
        )

    def _ensure_date_picker(self) -> ft.DatePicker:
        """Get or create a DatePicker using the DatePickerManager.

        Uses DatePickerManager to reuse pickers and prevent overlay memory leaks.
        """
        return _picker_manager.get_picker(
            self.page,
            first_date=date.today(),
            last_date=date.today() + timedelta(days=365 * DATE_PICKER_YEARS),
        )

    def date_picker(self, task: Task) -> None:
        if task.recurrent:
            content = ft.Container(
                width=DIALOG_WIDTH_SM,
                height=100,
                content=ft.Column(
                    [
                        ft.Text(
                            t("recurrent_tasks_use_pattern"),
                            color=COLORS["done_text"],
                        ),
                        ft.Text(
                            t("edit_recurrence_to_change"),
                            color=COLORS["done_text"],
                            size=12,
                        ),
                    ],
                    tight=True,
                ),
            )
            def _edit_recurrence(close: Callable) -> None:
                close(None)
                self.recurrence(task)

            open_dialog(
                self.page,
                t("select_date"),
                content,
                lambda c: [
                    ft.TextButton(t("close"), on_click=c),
                    ft.TextButton(t("edit_recurrence"), on_click=lambda e: _edit_recurrence(c)),
                ],
            )
            return

        picker = self._ensure_date_picker()

        picker_value = (
            task.due_date
            if task.due_date and task.due_date >= date.today()
            else date.today()
        )
        picker.value = picker_value

        def handle_change(e: ft.ControlEvent) -> None:
            if e.control.value:
                new_date = e.control.value.date()

                async def _handle() -> None:
                    await self.task_service.set_task_due_date(task, new_date)
                    self.snack.show(self._get_date_change_message(new_date))
                    event_bus.emit(AppEvent.TASK_UPDATED, task)
                    event_bus.emit(AppEvent.REFRESH_UI)
                self.page.run_task(_handle)

        picker.on_change = handle_change

        def preset(days: int) -> None:
            new_date = date.today() + timedelta(days=days)

            async def _preset() -> None:
                await self.task_service.set_task_due_date(task, new_date)
                self.snack.show(self._get_date_change_message(new_date))
                close()
                event_bus.emit(AppEvent.TASK_UPDATED, task)
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_preset)

        def clear(e: ft.ControlEvent) -> None:
            async def _clear() -> None:
                await self.task_service.set_task_due_date(task, None)
                self.snack.show(self._get_date_change_message(None))
                close()
                event_bus.emit(AppEvent.TASK_UPDATED, task)
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_clear)

        def pick(e: ft.ControlEvent) -> None:
            picker.open = True
            self.page.update()

        content = ft.Container(
            width=DIALOG_WIDTH_SM,
            content=ft.Column(
                [
                    create_option_item(
                        ft.Icons.BLOCK,
                        t("no_due_date"),
                        clear,
                        color=COLORS["danger"],
                        text_color=COLORS["done_text"],
                    ),
                    ft.Divider(height=1, color=COLORS["border"]),
                    create_option_item(ft.Icons.TODAY, t("today"), lambda e: preset(0)),
                    create_option_item(
                        ft.Icons.CALENDAR_TODAY, t("tomorrow"), lambda e: preset(1)
                    ),
                    create_option_item(
                        ft.Icons.DATE_RANGE, t("next_week"), lambda e: preset(7)
                    ),
                    ft.Divider(height=1, color=COLORS["border"]),
                    create_option_item(
                        ft.Icons.CALENDAR_MONTH, t("pick_a_date"), pick
                    ),
                ],
                tight=True,
                spacing=SPACING_SM,
            ),
        )

        _, close = open_dialog(
            self.page,
            t("select_date"),
            content,
            lambda c: [ft.TextButton(t("cancel"), on_click=c)],
        )

    def recurrence(self, task: Task) -> None:
        """Open the recurrence dialog."""
        recurrence_state = RecurrenceState.from_task(task)

        def on_save() -> None:
            async def _save() -> None:
                await self.task_service.persist_task(task)
                msg = t("recurrence_updated") if task.recurrent else t("recurrence_disabled")
                self.snack.show(msg)
                event_bus.emit(AppEvent.TASK_UPDATED, task)
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_save)

        temp_controller = RecurrenceDialogController(
            page=self.page,
            state=recurrence_state,
            on_save=on_save,
            on_close=lambda e: None,
        )
        content = temp_controller.build_content()

        _, close = open_dialog(
            self.page,
            t("set_recurrence"),
            content,
            lambda c: [
                ft.TextButton(t("cancel"), on_click=c),
                accent_btn(t("save"), lambda e: temp_controller.save(e)),
            ],
        )
        temp_controller.on_close = close

    def stats(self, task: Task) -> None:
        """Show task statistics dialog.

        Loads time entries asynchronously then displays the dialog.
        """
        async def load_and_show() -> None:
            time_entries = (
                await self.time_entry_service.load_time_entries_for_task(task.id)
                if task.id else []
            )
            self._show_stats_dialog(task, time_entries)

        self.page.run_task(load_and_show)

    def _show_stats_dialog(self, task: Task, time_entries: List[TimeEntry]) -> None:
        """Internal: Build and show the stats dialog with loaded data."""
        project = self.state.get_project_by_id(task.project_id)
        pct = (
            (task.spent_seconds / task.estimated_seconds * 100)
            if task.estimated_seconds > 0 else 0
        )
        remaining = max(0, task.estimated_seconds - task.spent_seconds)

        def stat_card(
            icon: str,
            label: str,
            value: str,
            color: str,
        ) -> ft.Container:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [ft.Icon(icon, color=color), ft.Text(label, weight="bold")],
                            spacing=SPACING_LG,
                        ),
                        ft.Text(value, size=24, weight="bold", color=color),
                    ],
                    spacing=SPACING_SM,
                ),
                bgcolor=COLORS["card"],
                padding=PADDING_2XL,
                border_radius=BORDER_RADIUS,
            )

        estimated_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SCHEDULE, color=COLORS["blue"]),
                            ft.Text(t("estimated"), weight="bold"),
                        ],
                        spacing=SPACING_LG,
                    ),
                    ft.Text(
                        TimeFormatter.seconds_to_display(task.estimated_seconds),
                        size=18,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=SPACING_SM,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
        )

        progress_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text(t("progress"), weight="bold"),
                    ft.ProgressBar(
                        value=min(pct / 100, 1.0),
                        color=COLORS["accent"],
                        bgcolor=COLORS["input_bg"],
                    ),
                    ft.Text(
                        t("pct_complete").replace("{pct}", f"{pct:.0f}"),
                        size=12,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=SPACING_MD,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
        )

        project_row = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.FOLDER, size=16, color=COLORS["done_text"]),
                    ft.Text(
                        t("project_colon").replace(
                            "{name}", project.name if project else t("unassigned")
                        ),
                        size=12,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=SPACING_MD,
            ),
            padding=ft.Padding.only(top=PADDING_LG),
        )

        entries_count = len(time_entries)
        entries_text = (
            t("one_time_entry") if entries_count == 1
            else t("n_time_entries").replace("{count}", str(entries_count))
        )

        def view_entries(e: ft.ControlEvent) -> None:
            close(e)
            self.state.viewing_task_id = task.id
            if self.navigate:
                self.navigate(PageType.TIME_ENTRIES)   

        entries_card = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.HISTORY, color=COLORS["accent"], size=18),
                    ft.Column(
                        [
                            ft.Text(t("time_entries_label"), weight="bold", size=13),
                            ft.Text(entries_text, color=COLORS["done_text"], size=12),
                        ],
                        spacing=SPACING_XS,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ARROW_FORWARD,
                        icon_color=COLORS["accent"],
                        tooltip=t("view_all_time_entries"),
                        on_click=view_entries,
                    ),
                ],
                spacing=SPACING_LG,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_XL,
            border_radius=BORDER_RADIUS,
            on_click=view_entries,
            ink=True,
        )

        # Completion-date editor — only meaningful for done tasks. Persistent (not
        # just the one-shot completion modal) so legacy/edited completions can be set.
        is_done = any(td.id == task.id for td in self.state.done_tasks)
        column_items = [
            stat_card(
                ft.Icons.TIMER,
                t("time_spent"),
                TimeFormatter.seconds_to_display(task.spent_seconds),
                COLORS["accent"],
            ),
            stat_card(
                ft.Icons.HOURGLASS_EMPTY,
                t("remaining"),
                TimeFormatter.seconds_to_display(remaining),
                COLORS["orange"],
            ),
            estimated_card,
            progress_card,
            entries_card,
            project_row,
        ]
        if is_done:
            column_items.append(self._build_completion_row(task))

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column(
                column_items,
                spacing=SPACING_LG,
                tight=True,
            ),
        )

        _, close = open_dialog(
            self.page,
            t("stats_title").replace("{title}", task.title),
            content,
            lambda c: [ft.TextButton(t("close"), on_click=c)],
        )

    def confirm_delete(self, task: Task, on_confirm: Callable[[], None]) -> None:
        """Confirm before an irreversible task delete (no undo; cascades to entries)."""
        def do(e: ft.ControlEvent) -> None:
            close(e)
            on_confirm()

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Text(
                t("delete_task_confirm").replace("{title}", task.title),
                text_align=ft.TextAlign.CENTER,
            ),
        )
        _, close = open_dialog(
            self.page,
            t("delete_task_title"),
            content,
            lambda c: [ft.TextButton(t("cancel"), on_click=c), danger_btn(t("delete"), do)],
        )

    def log_time(self, on_pick: Callable[[Task], None]) -> None:
        """Pick a task to log past time against (pending + done, drafts excluded).

        Includes a search box so the list stays usable with many tasks; done tasks
        are visually distinct and sorted after pending ones.
        """
        pending = [tk for tk in self.state.tasks if not tk.is_draft]
        done = [tk for tk in self.state.done_tasks if not tk.is_draft]
        done_ids = {d.id for d in done}
        candidates = pending + done

        def choose(tk: Task) -> None:
            close()
            on_pick(tk)

        list_col = ft.Column(tight=True, spacing=SPACING_SM, scroll=ft.ScrollMode.AUTO, expand=True)

        def _row(tk: Task) -> ft.Container:
            project = self.state.get_project_by_id(tk.project_id)
            is_done = tk.id in done_ids
            row = ft.Row(
                [
                    ft.Text(project.icon if project else "📋", size=16),
                    ft.Text(
                        tk.title,
                        size=14,
                        expand=True,
                        color=COLORS["done_text"] if is_done else None,
                        style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH) if is_done else None,
                    ),
                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=14, color=COLORS["done_text"]) if is_done else ft.Container(),
                ],
                spacing=SPACING_XL,
            )
            return ft.Container(
                content=row,
                padding=ft.Padding.symmetric(vertical=PADDING_LG, horizontal=PADDING_2XL),
                border_radius=8,
                ink=True,
                on_click=lambda e, picked=tk: choose(picked),
            )

        def _rebuild(query: str = "") -> None:
            q = query.strip().lower()
            matches = [tk for tk in candidates if q in tk.title.lower()] if q else candidates
            list_col.controls = (
                [_row(tk) for tk in matches]
                if matches else [ft.Text(t("no_tasks"), size=13, color=COLORS["done_text"])]
            )

        search = ft.TextField(
            hint_text=t("search"),
            prefix_icon=ft.Icons.SEARCH,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            dense=True,
            on_change=lambda e: (_rebuild(e.control.value), self.page.update()),
        )
        _rebuild()

        content = ft.Container(
            width=DIALOG_WIDTH_SM,
            height=400,
            content=ft.Column([search, list_col], tight=True, spacing=SPACING_MD, expand=True),
        )
        _, close = open_dialog(
            self.page,
            t("log_time_for"),
            content,
            lambda c: [ft.TextButton(t("cancel"), on_click=c)],
        )

    def _build_completion_row(self, task: Task) -> ft.Container:
        """Editable completion-date row for a done task (date + time)."""
        def _label() -> str:
            if task.completed_at:
                return task.completed_at.strftime("%b %d, %Y %H:%M")
            return t("no_completion_date")

        value_text = ft.Text(_label(), size=12, color=COLORS["accent"])

        def _persist(new_dt: datetime) -> None:
            # A task cannot have been completed in the future; clamp to now.
            new_dt = min(new_dt, datetime.now())

            async def _save() -> None:
                await self.task_service.set_task_completed_at(task, new_dt)
                value_text.value = _label()
                self.snack.show(t("completion_date"))
                self.page.update()
                event_bus.emit(AppEvent.TASK_UPDATED, task)
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_save)

        def edit(e: ft.ControlEvent) -> None:
            base = task.completed_at or datetime.now()
            # Dedicated past-capable pickers (not the shared due-date picker).
            date_picker = ft.DatePicker(
                first_date=date.today() - timedelta(days=365 * 10),
                last_date=date.today(),  # a task can't have been completed in the future
                value=base,
            )

            def on_date(ev: ft.ControlEvent) -> None:
                picked = ev.control.value
                if date_picker in self.page.overlay:
                    self.page.overlay.remove(date_picker)
                if picked is None:
                    return
                d = picked.date() if hasattr(picked, "date") else picked
                time_picker = ft.TimePicker(value=base.time())

                def on_time(tev: ft.ControlEvent) -> None:
                    tm = tev.control.value
                    if time_picker in self.page.overlay:
                        self.page.overlay.remove(time_picker)
                    chosen_time = tm if isinstance(tm, time) else base.time()
                    _persist(datetime(d.year, d.month, d.day, chosen_time.hour, chosen_time.minute))

                time_picker.on_change = on_time
                time_picker.on_dismiss = lambda x: (
                    self.page.overlay.remove(time_picker) if time_picker in self.page.overlay else None
                )
                self.page.overlay.append(time_picker)
                time_picker.open = True
                self.page.update()

            date_picker.on_change = on_date
            date_picker.on_dismiss = lambda x: (
                self.page.overlay.remove(date_picker) if date_picker in self.page.overlay else None
            )
            self.page.overlay.append(date_picker)
            date_picker.open = True
            self.page.update()

        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.EVENT_AVAILABLE, size=16, color=COLORS["done_text"]),
                    ft.Column(
                        [
                            ft.Text(t("completion_date"), weight="bold", size=13),
                            value_text,
                        ],
                        spacing=SPACING_XS,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.EDIT_CALENDAR,
                        icon_color=COLORS["accent"],
                        tooltip=t("set_completion_date"),
                        on_click=edit,
                    ),
                ],
                spacing=SPACING_MD,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_XL,
            border_radius=BORDER_RADIUS,
        )

    def delete_recurrence(
        self,
        task: Task,
        on_delete_this: Callable[[Task], None],
        on_delete_all: Callable[[Task], None],
    ) -> None:
        """Show dialog for deleting a recurring task.

        Args:
            task: The recurring task to delete
            on_delete_this: Callback for deleting just this occurrence
            on_delete_all: Callback for deleting all recurring instances
        """
        def delete_this(e: ft.ControlEvent) -> None:
            close(e)
            on_delete_this(task)

        def delete_all(e: ft.ControlEvent) -> None:
            close(e)
            on_delete_all(task)

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column(
                [
                    ft.Text(
                        t("task_is_recurring").replace("{title}", task.title),
                        size=14,
                    ),
                    ft.Divider(height=SPACING_2XL, color="transparent"),
                    create_option_item(
                        ft.Icons.DELETE_OUTLINE,
                        t("delete_this_occurrence"),
                        delete_this,
                        color=COLORS["orange"],
                    ),
                    ft.Text(
                        t("delete_occurrence_explanation"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    create_option_item(
                        ft.Icons.DELETE_FOREVER,
                        t("delete_all_occurrences"),
                        delete_all,
                        color=COLORS["danger"],
                    ),
                    ft.Text(
                        t("delete_all_explanation"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=SPACING_SM,
                tight=True,
            ),
        )

        _, close = open_dialog(
            self.page,
            t("delete_recurring_task"),
            content,
            lambda c: [ft.TextButton(t("cancel"), on_click=c)],
        )

    def _open_past_date_picker(self, current: date, on_pick: Callable[[date], None]) -> None:
        """Open a no-future date picker (created on demand, removed on dismiss).

        Shared by the completion-knob and completion-date editors so the
        'cannot be in the future' policy lives in one place.
        """
        picker = ft.DatePicker(
            first_date=date.today() - timedelta(days=365 * 10),
            last_date=date.today(),
            value=datetime.combine(current, time()),
        )

        def _handle(e: ft.ControlEvent) -> None:
            value = e.control.value
            if value is not None:
                on_pick(value.date() if hasattr(value, "date") else value)
            if picker in self.page.overlay:
                self.page.overlay.remove(picker)

        picker.on_change = _handle
        picker.on_dismiss = lambda e: (
            self.page.overlay.remove(picker) if picker in self.page.overlay else None
        )
        self.page.overlay.append(picker)
        picker.open = True
        self.page.update()

    def duration_completion(
        self,
        task: Task,
        on_complete: Callable,
    ) -> None:
        """Show duration knob dialog for completing a task without time entries.

        Supports backdating: pick the day the work was done so both the time entry
        and the completion timestamp land on the right day (not always 'now').

        Args:
            task: The task being completed
            on_complete: Async callback ``on_complete(task, completed_at)`` finalizing completion
        """
        # Default to estimated time or 15 minutes
        initial_minutes = task.estimated_seconds // 60 if task.estimated_seconds else 15

        knob = DurationKnob(initial_minutes=initial_minutes, size=220)
        when = {"date": date.today()}

        def _completed_dt() -> datetime:
            now = datetime.now()
            if when["date"] >= date.today():
                return now
            # Past day: anchor at the same clock time on that day (always < now).
            return datetime.combine(when["date"], now.time())

        date_btn = ft.TextButton(t("today"), icon=ft.Icons.CALENDAR_TODAY)

        def _refresh_date_label() -> None:
            date_btn.text = t("today") if when["date"] == date.today() else when["date"].strftime("%b %d, %Y")
            date_btn.update()

        def pick_when(e: ft.ControlEvent) -> None:
            def applied(d: date) -> None:
                when["date"] = d
                _refresh_date_label()
            self._open_past_date_picker(when["date"], applied)

        date_btn.on_click = pick_when

        def save(e: ft.ControlEvent) -> None:
            async def _save() -> None:
                duration_seconds = knob.value * 60
                end_time = _completed_dt()
                start_time = end_time - timedelta(seconds=duration_seconds)
                # Canonical: create the entry and recompute (do NOT += and persist —
                # metadata saves no longer write spent_seconds).
                _, affected = await self.time_entry_service.add_manual_entry(
                    task.id, start_time, end_time
                )
                if task.id in affected:
                    task.spent_seconds = affected[task.id]
                close(None)
                await on_complete(task, end_time)
            self.page.run_task(_save)

        def skip(e: ft.ControlEvent) -> None:
            async def _skip() -> None:
                completed_at = _completed_dt()
                close(None)
                await on_complete(task, completed_at)
            self.page.run_task(_skip)

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column(
                [
                    ft.Text(
                        t("how_long_spent"),
                        size=14,
                        color=COLORS["done_text"],
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(
                        content=knob,
                        alignment=ft.Alignment(0, 0),
                        padding=ft.Padding.only(top=PADDING_LG, bottom=PADDING_LG),
                    ),
                    ft.Row(
                        [
                            ft.Text(t("when_done"), size=13, color=COLORS["done_text"]),
                            date_btn,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=SPACING_SM,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_LG,
                tight=True,
            ),
        )

        _, close = open_dialog(
            self.page,
            t("complete_title").replace("{title}", task.title),
            content,
            lambda c: [
                ft.TextButton(t("cancel"), on_click=c),
                ft.TextButton(t("skip"), on_click=skip),
                accent_btn(t("complete_action"), save),
            ],
        )
