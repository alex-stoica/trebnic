import flet as ft
from datetime import date, datetime, timedelta
from typing import Callable, Optional, List

from config import (
    COLORS,
    DIALOG_WIDTH_SM,
    DIALOG_WIDTH_MD,
    DIALOG_WIDTH_LG,
    DIALOG_WIDTH_XL,
    NOTES_FIELD_HEIGHT,
    DATE_PICKER_YEARS,
    BORDER_RADIUS,
    PageType,
    RecurrenceFrequency,
)
from models.entities import Task, AppState, TimeEntry
from services.logic import TaskService
from ui.formatters import TimeFormatter
from ui.helpers import accent_btn, SnackService
from ui.dialogs.base import open_dialog, create_option_item
from ui.dialogs.dialog_state import RecurrenceState
from ui.components.duration_knob import DurationKnob
from events import event_bus, AppEvent


class RecurrenceDialogController:
    """Controller for the recurrence dialog."""

    WEEKDAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"]

    # Class-level DatePicker to reuse across instances and prevent memory leak
    _shared_date_picker: Optional[ft.DatePicker] = None
    _shared_picker_page: Optional[ft.Page] = None

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
        self.weekday_cbs = [
            ft.Checkbox(
                label=d,
                value=self.state.weekdays[i],
                scale=0.85,
                on_change=lambda e, idx=i: self._on_weekday_change(e, idx),
            )
            for i, d in enumerate(self.WEEKDAY_LABELS)
        ]

        self.weekdays_section = ft.Column(
            [
                ft.Text("On these days", weight="bold", size=13),
                ft.Row(self.weekday_cbs[:4], spacing=0),
                ft.Row(self.weekday_cbs[4:], spacing=0),
            ],
            visible=self.state.frequency == RecurrenceFrequency.WEEKS,
            spacing=8,
        )

        self.freq_dd = ft.Dropdown(
            value=self.state.frequency.value,
            options=[
                ft.dropdown.Option(RecurrenceFrequency.DAYS.value, "Days"),
                ft.dropdown.Option(RecurrenceFrequency.WEEKS.value, "Weeks"),
                ft.dropdown.Option(RecurrenceFrequency.MONTHS.value, "Months"),
            ],
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            width=120,
            on_change=self._on_freq_change,
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
            label="Enable recurrence",
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
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=4,
        )

        self.end_type_group = ft.RadioGroup(
            value=self.state.end_type,
            on_change=self._on_end_type_change,
            content=ft.Column(
                [
                    ft.Radio(value="never", label="Never"),
                    ft.Row(
                        [
                            ft.Radio(value="on_date", label="On date"),
                            self.end_date_btn,
                        ],
                        spacing=8,
                    ),
                ],
                spacing=8,
            ),
        )

        self.from_completion_switch = ft.Switch(
            value=self.state.from_completion,
            label="Recur from completion date",
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

        Uses a class-level shared DatePicker to prevent overlay memory leaks.
        The picker is reused across dialog instances and only added to overlay once.
        """
        cls = RecurrenceDialogController

        # Check if we need to create a new picker (first time or page changed)
        if cls._shared_date_picker is None or cls._shared_picker_page != self.page:
            # Remove old picker from previous page's overlay if exists
            if cls._shared_date_picker is not None and cls._shared_picker_page is not None:
                try:
                    cls._shared_picker_page.overlay.remove(cls._shared_date_picker)
                except ValueError:
                    pass  # Already removed

            # Create new picker for current page
            cls._shared_date_picker = ft.DatePicker(
                first_date=date.today(),
                last_date=date.today() + timedelta(days=365 * 5),
            )
            self.page.overlay.append(cls._shared_date_picker)
            cls._shared_picker_page = self.page

        # Update handler for this specific dialog instance
        cls._shared_date_picker.on_change = self._on_end_date_change
        cls._shared_date_picker.value = self.state.end_date or date.today()
        cls._shared_date_picker.open = True
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
        self.state.interval = int(self.interval_field.value or 1)
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
                    ft.Divider(height=15, color=COLORS["border"]),
                    ft.Text("Frequency", weight="bold", size=13),
                    ft.Row(
                        [
                            ft.Text("Repeat every", size=13),
                            self.interval_field,
                            self.freq_dd,
                        ],
                        spacing=8,
                    ),
                    ft.Divider(height=10, color="transparent"),
                    self.weekdays_section,
                    ft.Divider(height=15, color=COLORS["border"]),
                    ft.Text("Behavior", weight="bold", size=13),
                    self.from_completion_switch,
                    ft.Text(
                        "When enabled, the next occurrence is calculated from the completion date "
                        "instead of the original due date. Useful for habits like 'Every 30 days'.",
                        size=11,
                        color=COLORS["done_text"],
                    ),
                    ft.Divider(height=15, color=COLORS["border"]),
                    ft.Text("Ends", weight="bold", size=13),
                    self.end_type_group,
                ],
                spacing=10,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )


class TaskDialogs:
    # Class-level DatePicker to reuse across instances and prevent memory leak
    _shared_date_picker: Optional[ft.DatePicker] = None
    _shared_picker_page: Optional[ft.Page] = None

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        service: TaskService,
        snack: SnackService,
        navigate: Callable[[PageType], None] = None,
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self.snack = snack
        self.navigate = navigate

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
            if self.service.task_name_exists(name, task):
                error.value = "A task with this name already exists"
                error.visible = True
                self.page.update()
                return

            async def _save() -> None:
                await self.service.rename_task(task, name)
                self.snack.show(f"Renamed to '{name}'")
                close(e)
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_save)

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column([field, error], tight=True, spacing=5),
        )

        _, close = open_dialog(
            self.page,
            "Rename Task",
            content,
            lambda c: [ft.TextButton("Cancel", on_click=c), accent_btn("Save", save)],
        )

    def assign_project(self, task: Task) -> None:
        def select(pid: Optional[str]) -> None:
            async def _select() -> None:
                await self.service.assign_project(task, pid)
                p = self.state.get_project_by_id(pid)
                self.snack.show(f"Task assigned to {p.name if p else 'Unassigned'}")
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
                spacing=12,
            )
            container = ft.Container(
                content=row,
                padding=ft.padding.symmetric(vertical=10, horizontal=15),
                border_radius=8,
                ink=True,
                on_click=lambda e, pid=p.id: select(pid),
            )
            opts.append(container)

        opts.append(ft.Divider(height=1, color=COLORS["border"]))

        unassign_row = ft.Row(
            [
                ft.Icon(ft.Icons.CLOSE, color=COLORS["done_text"], size=18),
                ft.Text("Unassign", size=14, color=COLORS["done_text"]),
            ],
            spacing=12,
        )
        unassign_container = ft.Container(
            content=unassign_row,
            padding=ft.padding.symmetric(vertical=10, horizontal=15),
            border_radius=8,
            ink=True,
            on_click=lambda e: select(None),
        )
        opts.append(unassign_container)

        content = ft.Container(
            width=DIALOG_WIDTH_SM,
            content=ft.Column(opts, tight=True, spacing=4),
        )

        _, close = open_dialog(
            self.page,
            "Assign to Project",
            content,
            lambda c: [ft.TextButton("Cancel", on_click=c)],
        )

    def _ensure_date_picker(self) -> ft.DatePicker:
        """Get or create the shared DatePicker, managing overlay lifecycle.

        Uses a class-level shared DatePicker to prevent overlay memory leaks.
        The picker is reused across dialog instances and only added to overlay once.
        """
        cls = TaskDialogs

        # Check if we need to create a new picker (first time or page changed)
        if cls._shared_date_picker is None or cls._shared_picker_page != self.page:
            # Remove old picker from previous page's overlay if exists
            if cls._shared_date_picker is not None and cls._shared_picker_page is not None:
                try:
                    cls._shared_picker_page.overlay.remove(cls._shared_date_picker)
                except ValueError:
                    pass  # Already removed

            # Create new picker for current page
            cls._shared_date_picker = ft.DatePicker(
                first_date=date.today(),
                last_date=date.today() + timedelta(days=365 * DATE_PICKER_YEARS),
            )
            self.page.overlay.append(cls._shared_date_picker)
            cls._shared_picker_page = self.page

        return cls._shared_date_picker

    def date_picker(self, task: Task) -> None:
        if task.recurrent:
            content = ft.Container(
                width=DIALOG_WIDTH_SM,
                height=100,
                content=ft.Column(
                    [
                        ft.Text(
                            "Recurrent tasks use their recurrence pattern.",
                            color=COLORS["done_text"],
                        ),
                        ft.Text(
                            "Edit recurrence settings to change schedule.",
                            color=COLORS["done_text"],
                            size=12,
                        ),
                    ],
                    tight=True,
                ),
            )
            open_dialog(
                self.page,
                "Select date",
                content,
                lambda c: [ft.TextButton("Close", on_click=c)],
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
                    await self.service.set_task_due_date(task, new_date)
                    self.snack.show(f"Date set to {task.due_date.strftime('%b %d')}")
                    event_bus.emit(AppEvent.REFRESH_UI)
                self.page.run_task(_handle)

        picker.on_change = handle_change

        def preset(days: int) -> None:
            new_date = date.today() + timedelta(days=days)

            async def _preset() -> None:
                await self.service.set_task_due_date(task, new_date)
                self.snack.show(f"Date set to {task.due_date.strftime('%b %d')}")
                close()
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_preset)

        def clear(e: ft.ControlEvent) -> None:
            async def _clear() -> None:
                await self.service.set_task_due_date(task, None)
                self.snack.show("Date cleared")
                close()
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
                        "🚫 No due date",
                        clear,
                        color=COLORS["danger"],
                        text_color=COLORS["done_text"],
                    ),
                    ft.Divider(height=1, color=COLORS["border"]),
                    create_option_item(ft.Icons.TODAY, "Today", lambda e: preset(0)),
                    create_option_item(
                        ft.Icons.CALENDAR_TODAY, "Tomorrow", lambda e: preset(1)
                    ),
                    create_option_item(
                        ft.Icons.DATE_RANGE, "Next week", lambda e: preset(7)
                    ),
                    ft.Divider(height=1, color=COLORS["border"]),
                    create_option_item(
                        ft.Icons.CALENDAR_MONTH, "Pick a date...", pick
                    ),
                ],
                tight=True,
                spacing=4,
            ),
        )

        _, close = open_dialog(
            self.page,
            "Select date",
            content,
            lambda c: [ft.TextButton("Cancel", on_click=c)],
        )

    def recurrence(self, task: Task) -> None:
        """Open the recurrence dialog."""
        recurrence_state = RecurrenceState.from_task(task)

        def on_save() -> None:
            async def _save() -> None:
                await self.service.persist_task(task)
                msg = "Recurrence updated" if task.recurrent else "Recurrence disabled"
                self.snack.show(msg)
                event_bus.emit(AppEvent.REFRESH_UI)
            self.page.run_task(_save)  

        controller: Optional[RecurrenceDialogController] = None

        def make_actions(close_fn: Callable[[], None]) -> List[ft.Control]:
            nonlocal controller
            controller = RecurrenceDialogController(
                page=self.page,
                state=recurrence_state,
                on_save=on_save,
                on_close=close_fn,
            )
            return [
                ft.TextButton("Cancel", on_click=close_fn),
                accent_btn("Save", controller.save),
            ]
 
        temp_controller = RecurrenceDialogController(
            page=self.page,
            state=recurrence_state,
            on_save=on_save,
            on_close=lambda e: None,
        )
        content = temp_controller.build_content()

        _, close = open_dialog(
            self.page,
            "Set recurrence",
            content,
            lambda c: [
                ft.TextButton("Cancel", on_click=c),
                accent_btn("Save", lambda e: temp_controller.save(e)),
            ],
        )
        temp_controller.on_close = close

    def stats(self, task: Task) -> None:
        """Show task statistics dialog.

        Loads time entries asynchronously then displays the dialog.
        """
        async def load_and_show() -> None:
            time_entries = (
                await self.service.load_time_entries_for_task(task.id)
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
                            spacing=10,
                        ),
                        ft.Text(value, size=24, weight="bold", color=color),
                    ],
                    spacing=5,
                ),
                bgcolor=COLORS["card"],
                padding=15,
                border_radius=BORDER_RADIUS,
            )

        estimated_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SCHEDULE, color=COLORS["blue"]),
                            ft.Text("Estimated", weight="bold"),
                        ],
                        spacing=10,
                    ),
                    ft.Text(
                        TimeFormatter.seconds_to_display(task.estimated_seconds),
                        size=18,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=5,
            ),
            bgcolor=COLORS["card"],
            padding=15,
            border_radius=BORDER_RADIUS,
        )

        progress_card = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Progress", weight="bold"),
                    ft.ProgressBar(
                        value=min(pct / 100, 1.0),
                        color=COLORS["accent"],
                        bgcolor=COLORS["input_bg"],
                    ),
                    ft.Text(
                        f"{pct:.0f}% complete",
                        size=12,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=8,
            ),
            bgcolor=COLORS["card"],
            padding=15,
            border_radius=BORDER_RADIUS,
        )

        project_row = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.FOLDER, size=16, color=COLORS["done_text"]),
                    ft.Text(
                        f"Project: {project.name if project else 'Unassigned'}",
                        size=12,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=8,
            ),
            padding=ft.padding.only(top=10),
        )

        entries_count = len(time_entries)
        entries_text = f"{entries_count} time {'entry' if entries_count == 1 else 'entries'}"

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
                            ft.Text("Time Entries", weight="bold", size=13),
                            ft.Text(entries_text, color=COLORS["done_text"], size=12),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ARROW_FORWARD,
                        icon_color=COLORS["accent"],
                        tooltip="View all time entries",
                        on_click=view_entries,
                    ),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=12,
            border_radius=BORDER_RADIUS,
            on_click=view_entries,
            ink=True,
        )

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column(
                [
                    stat_card(
                        ft.Icons.TIMER,
                        "Time spent",
                        TimeFormatter.seconds_to_display(task.spent_seconds),
                        COLORS["accent"],
                    ),
                    stat_card(
                        ft.Icons.HOURGLASS_EMPTY,
                        "Remaining",
                        TimeFormatter.seconds_to_display(remaining),
                        COLORS["orange"],
                    ),
                    estimated_card,
                    progress_card,
                    entries_card,
                    project_row,
                ],
                spacing=10,
                tight=True,
            ),
        )

        _, close = open_dialog(
            self.page,
            f"Stats: {task.title}",
            content,
            lambda c: [ft.TextButton("Close", on_click=c)],
        )

    def notes(self, task: Task) -> None:
        field = ft.TextField(
            value=task.notes,
            multiline=True,
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=8,
            hint_text="Write notes here... Markdown supported",
            height=NOTES_FIELD_HEIGHT,
        )

        md = ft.Markdown(
            value=task.notes or "*No notes yet*",
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
        )

        preview = ft.Container(
            content=ft.Column([md], scroll=ft.ScrollMode.AUTO, expand=True),
            bgcolor=COLORS["input_bg"],
            border=ft.border.all(1, COLORS["border"]),
            border_radius=8,
            padding=10,
            height=NOTES_FIELD_HEIGHT,
            visible=False,
        )

        toggle_btn = ft.TextButton("Preview", icon=ft.Icons.VISIBILITY)

        def toggle(e: ft.ControlEvent) -> None:
            is_preview = not preview.visible
            if is_preview:
                md.value = field.value or "*No notes yet*"
            field.visible = not is_preview
            preview.visible = is_preview
            toggle_btn.text = "Edit" if is_preview else "Preview"
            toggle_btn.icon = ft.Icons.EDIT if is_preview else ft.Icons.VISIBILITY
            self.page.update()

        toggle_btn.on_click = toggle

        def save(e: ft.ControlEvent) -> None:
            async def _save() -> None:
                await self.service.set_task_notes(task, field.value)
                close(e)
                self.snack.show("Notes saved")
            self.page.run_task(_save)

        content = ft.Container(
            width=DIALOG_WIDTH_XL,
            content=ft.Column(
                [
                    ft.Row([toggle_btn], alignment=ft.MainAxisAlignment.END),
                    field,
                    preview,
                ],
                tight=True,
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        )

        _, close = open_dialog(
            self.page,
            f"Notes: {task.title}",
            content,
            lambda c: [ft.TextButton("Cancel", on_click=c), accent_btn("Save", save)],
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
                        f"'{task.title}' is a recurring task.",
                        size=14,
                    ),
                    ft.Divider(height=15, color="transparent"),
                    create_option_item(
                        ft.Icons.DELETE_OUTLINE,
                        "Delete this occurrence only",
                        delete_this,
                        color=COLORS["orange"],
                    ),
                    ft.Text(
                        "Removes only this instance. Future occurrences will still be created when you complete tasks.",
                        size=11,
                        color=COLORS["done_text"],
                    ),
                    ft.Divider(height=10, color="transparent"),
                    create_option_item(
                        ft.Icons.DELETE_FOREVER,
                        "Delete all occurrences",
                        delete_all,
                        color=COLORS["danger"],
                    ),
                    ft.Text(
                        "Removes this task and all other pending/completed instances with the same recurrence.",
                        size=11,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=5,
                tight=True,
            ),
        )

        _, close = open_dialog(
            self.page,
            "Delete recurring task",
            content,
            lambda c: [ft.TextButton("Cancel", on_click=c)],
        )

    def duration_completion(
        self,
        task: Task,
        on_complete: Callable[[Task], None],
    ) -> None:
        """Show duration knob dialog for completing a task without time entries.

        Args:
            task: The task being completed
            on_complete: Callback to call after setting duration to complete the task
        """
        # Default to estimated time or 15 minutes
        initial_minutes = task.estimated_seconds // 60 if task.estimated_seconds else 15

        knob = DurationKnob(initial_minutes=initial_minutes, size=220)

        def save(e: ft.ControlEvent) -> None:
            async def _save() -> None:
                duration_seconds = knob.value * 60
                # Create time entry: end_time = now, start_time = now - duration
                end_time = datetime.now()
                start_time = end_time - timedelta(seconds=duration_seconds)
                entry = TimeEntry(task_id=task.id, start_time=start_time, end_time=end_time)
                await self.service.save_time_entry(entry)
                # Update task spent time
                task.spent_seconds += duration_seconds
                await self.service.persist_task(task)
                close(None)
                # Now complete the task
                on_complete(task)
            self.page.run_task(_save)

        def skip(e: ft.ControlEvent) -> None:
            # Complete without setting time
            close(e)
            on_complete(task)

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column(
                [
                    ft.Text(
                        "How long did you spend on this task?",
                        size=14,
                        color=COLORS["done_text"],
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(
                        content=knob,
                        alignment=ft.alignment.center,
                        padding=ft.padding.only(top=10, bottom=10),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
                tight=True,
            ),
        )

        _, close = open_dialog(
            self.page,
            f"Complete: {task.title}",
            content,
            lambda c: [
                ft.TextButton("Skip", on_click=skip),
                accent_btn("Save & Complete", save),
            ],
        )