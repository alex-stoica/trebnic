"""One draft-based editor for task metadata, usable at phone widths."""
from datetime import date, datetime
import flet as ft

from config import COLORS
from database import DatabaseError
from events import AppEvent, event_bus
from i18n import t
from services.crypto import LOCKED_PLACEHOLDER
from ui.formatters import TimeFormatter


class TaskDetailsPanel:
    def __init__(self, page, state, service, task, snack):
        self.page, self.state, self.service, self.task, self.snack = page, state, service, task, snack
        self.title = ft.TextField(label=t("details_title"), value=task.title, multiline=True, max_lines=3)
        self.estimate = ft.TextField(label=t("details_estimate"),
            value=str(task.estimated_seconds / 60).removesuffix(".0") if task.estimated_seconds else "",
            hint_text=t("not_estimated"), keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        self.due = task.due_date
        self.due_button = ft.TextButton(self._due_label(), icon=ft.Icons.CALENDAR_TODAY, on_click=self.pick_date)
        self.project = ft.Dropdown(label=t("assign_to_project"), value=task.project_id or "",
            options=[ft.DropdownOption(key="", text=t("no_project"))] +
                    [ft.DropdownOption(key=p.id, text=p.name) for p in state.projects])
        self.notes = ft.TextField(label=t("details_notes"), value=task.notes, multiline=True,
            min_lines=3, max_lines=6, hint_text=t("details_notes_hint"))
        self.repeat = ft.Switch(label=t("details_repeat"), value=task.recurrent, on_change=self.change_repeat)
        self.frequency = ft.Dropdown(label=t("frequency_label"), value=task.recurrence_frequency.value,
            options=[ft.DropdownOption(key=k, text=t("details_" + k)) for k in ("days", "weeks", "months")],
            on_select=self.change_repeat, expand=True)
        self.interval = ft.TextField(label=t("repeat_every"), value=str(task.recurrence_interval),
            keyboard_type=ft.KeyboardType.NUMBER, width=100)
        self.days = [ft.Checkbox(label=t("recurrence_day_" + key), value=i in task.recurrence_weekdays, width=72)
                     for i, key in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))]
        self.weekdays = ft.Row(self.days, wrap=True, spacing=0, run_spacing=0,
            visible=task.recurrence_frequency.value == "weeks")
        self.from_completion = ft.Switch(label=t("details_from_completion"), value=task.recurrence_from_completion)
        self.until = ft.TextField(label=t("details_until"),
            value=task.recurrence_end_date.isoformat() if task.recurrence_end_date else "",
            hint_text=t("details_until_hint"))
        self.recurrence_fields = ft.Column([
            ft.Row([self.interval, self.frequency]), self.weekdays, self.from_completion, self.until,
            ft.Text(t("details_recurrence_hint"), size=12, color=COLORS["done_text"]),
        ], visible=task.recurrent, spacing=10, tight=True)
        self.reminder = ft.TextField(label=t("details_reminder_time"), value=task.reminder_time or "",
            hint_text="19:00", keyboard_type=ft.KeyboardType.DATETIME)
        self.reminder_days = [ft.Checkbox(label=t("recurrence_day_" + key),
            value=i in task.reminder_weekdays, width=72)
            for i, key in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))]
        self.error = ft.Text("", color=COLORS["danger"], visible=False)
        self.save_button = ft.FilledButton(t("save"), on_click=self.save)
        self.cancel_button = ft.TextButton(t("cancel"), on_click=lambda e: self.page.pop_dialog())

    def _due_label(self):
        return self.due.strftime("%d.%m.%Y") if self.due else t("details_no_date")

    def set_date(self, value):
        self.due = value
        self.due_button.content = self._due_label()
        self.page.update()

    def pick_date(self, e):
        picker = ft.DatePicker(value=self.due or date.today(), first_date=date(2000, 1, 1),
            last_date=date(2100, 12, 31))
        def changed(ev):
            value = ev.control.value
            # Flet transports a local calendar midnight as a UTC instant.
            self.set_date(value.astimezone().date() if isinstance(value, datetime) else value)
        picker.on_change = changed
        self.page.show_dialog(picker)

    def change_repeat(self, e):
        self.recurrence_fields.visible = self.repeat.value
        self.weekdays.visible = self.frequency.value == "weeks"
        self.page.update()

    def open(self):
        from services.scoring import completion_points
        if self.task.title == LOCKED_PLACEHOLDER:
            return
        spent = TimeFormatter.seconds_to_display(self.task.spent_seconds)
        content = ft.Column([
            self.title,
            ft.Text(t("score_task_reward").format(points=f"{completion_points(self.task):g}",
                count=self.task.postponements), size=12, color=COLORS["done_text"]),
            ft.Container(content=ft.Row([
                ft.Icon(ft.Icons.TIMER_OUTLINED, color=COLORS["accent"]),
                ft.Text(t("details_worked").format(time=spent), weight=ft.FontWeight.W_600, expand=True),
            ]), bgcolor=COLORS["input_bg"], padding=12, border_radius=10),
            ft.Row([self.estimate, ft.IconButton(ft.Icons.CLEAR, tooltip=t("not_estimated"),
                on_click=self.clear_estimate)]),
            ft.Text(t("details_estimate_hint"), size=12, color=COLORS["done_text"]),
            ft.Row([self.due_button, ft.TextButton(t("details_no_date"), on_click=lambda e: self.set_date(None))], wrap=True),
            self.project, self.notes, self.repeat, self.recurrence_fields,
            self.reminder, ft.Text(t("details_reminder_hint"), size=12, color=COLORS["done_text"]),
            ft.Row(self.reminder_days, wrap=True, spacing=0, run_spacing=0), self.error,
        ], tight=True, spacing=12, scroll=ft.ScrollMode.AUTO)
        height = max(220, min(620, (self.page.height or 800) - 220))
        self.dialog = ft.AlertDialog(modal=True, title=ft.Text(t("task_details")),
            content=ft.Container(content=content, width=460, height=height),
            actions=[self.cancel_button, self.save_button],
            inset_padding=ft.Padding.all(16), content_padding=ft.Padding.all(16))
        self.page.show_dialog(self.dialog)

    def clear_estimate(self, e):
        self.estimate.value = ""
        self.page.update()

    async def save(self, e):
        if self.save_button.disabled:
            return
        try:
            raw = (self.estimate.value or "").strip().replace(",", ".")
            try:
                seconds = round(float(raw) * 60) if raw else 0
                if raw and seconds <= 0:
                    raise ValueError()
            except (ValueError, OverflowError):
                raise ValueError("details_invalid_estimate")
            try:
                interval = int(self.interval.value) if self.repeat.value else 1
            except ValueError:
                raise ValueError("details_invalid_interval")
            try:
                until = date.fromisoformat(self.until.value.strip()) if self.repeat.value and self.until.value.strip() else None
            except ValueError:
                raise ValueError("details_invalid_until")
            self.save_button.disabled = self.cancel_button.disabled = True
            self.page.update()
            await self.service.update_task_details(self.task, title=self.title.value or "",
                estimated_seconds=seconds, due_date=self.due, project_id=self.project.value or None,
                notes=self.notes.value or "", recurrent=bool(self.repeat.value),
                frequency=self.frequency.value, interval=interval,
                weekdays=[i for i, control in enumerate(self.days) if control.value],
                from_completion=bool(self.from_completion.value), until=until,
                reminder_time=(self.reminder.value or "").strip() or None,
                reminder_weekdays=[i for i, control in enumerate(self.reminder_days) if control.value])
        except (ValueError, DatabaseError) as exc:
            self.error.value = t(str(exc)) if isinstance(exc, ValueError) else t("details_save_failed")
            self.error.visible = True
            self.save_button.disabled = self.cancel_button.disabled = False
            self.page.update()
            return
        self.page.pop_dialog()
        event_bus.emit(AppEvent.TASK_UPDATED, self.task)
        event_bus.emit(AppEvent.REFRESH_UI)
        self.snack.show(t("details_saved"))
