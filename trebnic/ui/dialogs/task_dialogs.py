import flet as ft 
from datetime import date, timedelta 

from config import (COLORS, DIALOG_WIDTH_SM, DIALOG_WIDTH_MD, DIALOG_WIDTH_LG, DIALOG_WIDTH_XL, 
                    NOTES_FIELD_HEIGHT, DATE_PICKER_YEARS, BORDER_RADIUS) 
from models.entities import Task, AppState 
from services.logic import TaskService 
from ui.helpers import accent_btn, seconds_to_time, SnackService 
from ui.dialogs.base import open_dialog, create_option_item 


class TaskDialogs: 
    def __init__(self, page: ft.Page, state: AppState, service: TaskService, snack: SnackService, refresh: callable): 
        self.page = page 
        self.state = state 
        self.service = service 
        self.snack = snack 
        self.refresh = refresh 
        self._date_picker = None 

    def rename(self, task: Task): 
        error = ft.Text("", color=COLORS["danger"], size=12, visible=False) 
        field = ft.TextField(value=task.title, border_color=COLORS["border"], bgcolor=COLORS["input_bg"], 
                             border_radius=8, autofocus=True) 
        def save(e): 
            name = field.value.strip() 
            if not name: 
                return 
            if self.service.task_name_exists(name, task): 
                error.value, error.visible = "A task with this name already exists", True 
                self.page.update() 
                return 
            task.title = name 
            self.service.persist_task(task) 
            self.snack.show(f"Renamed to '{name}'") 
            close(e) 
            self.refresh() 
        content = ft.Container(width=DIALOG_WIDTH_MD, content=ft.Column([field, error], tight=True, spacing=5)) 
        _, close = open_dialog(self.page, "Rename Task", content, lambda c: [ft.TextButton("Cancel", on_click=c), accent_btn("Save", save)]) 

    def assign_project(self, task: Task): 
        def select(pid): 
            self.service.assign_project(task, pid) 
            p = self.state.get_project_by_id(pid) 
            self.snack.show(f"Task assigned to {p['name'] if p else 'Unassigned'}") 
            close() 
            self.refresh() 
        opts = [] 
        for p in self.state.projects: 
            is_sel = task.project_id == p["id"] 
            opts.append(ft.Container( 
                content=ft.Row([ft.Text(p["icon"], size=18), ft.Text(p["name"], size=14, expand=True), 
                                ft.Icon(ft.Icons.CHECK, color=COLORS["accent"], size=18) if is_sel else ft.Container(width=18)], spacing=12), 
                padding=ft.padding.symmetric(vertical=10, horizontal=15), border_radius=8, ink=True, on_click=lambda e, pid=p["id"]: select(pid))) 
        opts.append(ft.Divider(height=1, color=COLORS["border"])) 
        opts.append(ft.Container( 
            content=ft.Row([ft.Icon(ft.Icons.CLOSE, color=COLORS["done_text"], size=18), ft.Text("Unassign", size=14, color=COLORS["done_text"])], spacing=12), 
            padding=ft.padding.symmetric(vertical=10, horizontal=15), border_radius=8, ink=True, on_click=lambda e: select(None))) 
        content = ft.Container(width=DIALOG_WIDTH_SM, content=ft.Column(opts, tight=True, spacing=4)) 
        _, close = open_dialog(self.page, "Assign to Project", content, lambda c: [ft.TextButton("Cancel", on_click=c)]) 

    def date_picker(self, task: Task): 
        if task.recurrent: 
            content = ft.Container(width=DIALOG_WIDTH_SM, height=100, 
                                   content=ft.Column([ft.Text("Recurrent tasks use their recurrence pattern.", color=COLORS["done_text"]), 
                                                      ft.Text("Edit recurrence settings to change schedule.", color=COLORS["done_text"], size=12)], tight=True)) 
            open_dialog(self.page, "Select date", content, lambda c: [ft.TextButton("Close", on_click=c)]) 
            return 
        if self._date_picker is None: 
            self._date_picker = ft.DatePicker(first_date=date.today(), last_date=date.today() + timedelta(days=365 * DATE_PICKER_YEARS)) 
            self.page.overlay.append(self._date_picker) 
        self._date_picker.value = task.due_date if task.due_date and task.due_date >= date.today() else date.today() 
        def handle_change(e): 
            if e.control.value: 
                task.due_date = e.control.value.date() 
                self.service.persist_task(task) 
                self.snack.show(f"Date set to {task.due_date.strftime('%b %d')}") 
                self.refresh() 
        self._date_picker.on_change = handle_change 
        def preset(days): 
            task.due_date = date.today() + timedelta(days=days) 
            self.service.persist_task(task) 
            self.snack.show(f"Date set to {task.due_date.strftime('%b %d')}") 
            close() 
            self.refresh() 
        def clear(e): 
            task.due_date = None 
            self.service.persist_task(task) 
            self.snack.show("Date cleared") 
            close() 
            self.refresh() 
        def pick(e): 
            self._date_picker.open = True 
            self.page.update() 
        content = ft.Container(width=DIALOG_WIDTH_SM, content=ft.Column([ 
            create_option_item(ft.Icons.BLOCK, "🚫 No due date", clear, color=COLORS["danger"], text_color=COLORS["done_text"]), 
            ft.Divider(height=1, color=COLORS["border"]), 
            create_option_item(ft.Icons.TODAY, "Today", lambda e: preset(0)), 
            create_option_item(ft.Icons.CALENDAR_TODAY, "Tomorrow", lambda e: preset(1)), 
            create_option_item(ft.Icons.DATE_RANGE, "Next week", lambda e: preset(7)), 
            ft.Divider(height=1, color=COLORS["border"]), 
            create_option_item(ft.Icons.CALENDAR_MONTH, "Pick a date...", pick), 
        ], tight=True, spacing=4)) 
        _, close = open_dialog(self.page, "Select date", content, lambda c: [ft.TextButton("Cancel", on_click=c)]) 

    def recurrence(self, task: Task): 
        weekday_cbs = [ft.Checkbox(label=d, value=i in task.recurrence_weekdays, scale=0.85) for i, d in enumerate(["M", "T", "W", "T", "F", "S", "S"])] 
        weekdays_section = ft.Column([ft.Text("On these days", weight="bold", size=13), 
                                      ft.Row(weekday_cbs[:4], spacing=0), ft.Row(weekday_cbs[4:], spacing=0)], visible=True, spacing=8) 
        freq_dd = ft.Dropdown(value=task.recurrence_frequency, options=[ft.dropdown.Option("days", "Days"), 
                              ft.dropdown.Option("weeks", "Weeks"), ft.dropdown.Option("months", "Months")], 
                              border_color=COLORS["border"], bgcolor=COLORS["input_bg"], border_radius=8, width=120, 
                              on_change=lambda e: setattr(weekdays_section, "visible", freq_dd.value == "weeks") or self.page.update()) 
        interval = ft.TextField(value=str(task.recurrence_interval), border_color=COLORS["border"], bgcolor=COLORS["input_bg"], 
                                border_radius=8, width=50, text_align=ft.TextAlign.CENTER) 
        enable = ft.Switch(value=task.recurrent, label="Enable recurrence") 
        end_type = ft.RadioGroup(value="never", content=ft.Column([ft.Radio(value="never", label="Never"), 
                                  ft.Row([ft.Radio(value="on_date", label="On date"), ft.Text((date.today() + timedelta(days=90)).strftime("%b %d, %Y"), color=COLORS["accent"])], spacing=8)], spacing=8)) 
        def save(e): 
            task.recurrent = enable.value 
            task.recurrence_frequency = freq_dd.value 
            task.recurrence_interval = int(interval.value or 1) 
            task.recurrence_weekdays = [i for i, cb in enumerate(weekday_cbs) if cb.value] 
            self.service.persist_task(task) 
            close(e) 
            self.snack.show("Recurrence updated" if task.recurrent else "Recurrence disabled") 
            self.refresh() 
        content = ft.Container(width=DIALOG_WIDTH_LG, content=ft.Column([enable, ft.Divider(height=15, color=COLORS["border"]), 
                               ft.Text("Frequency", weight="bold", size=13), ft.Row([ft.Text("Repeat every", size=13), interval, freq_dd], spacing=8), 
                               ft.Divider(height=10, color="transparent"), weekdays_section, ft.Divider(height=15, color=COLORS["border"]), 
                               ft.Text("Ends", weight="bold", size=13), end_type], spacing=10, tight=True)) 
        _, close = open_dialog(self.page, "Set Recurrence", content, lambda c: [ft.TextButton("Cancel", on_click=c), accent_btn("Save", save)]) 

    def stats(self, task: Task): 
        project = self.state.get_project_by_id(task.project_id) 
        pct = (task.spent_seconds / task.estimated_seconds * 100) if task.estimated_seconds > 0 else 0 
        remaining = max(0, task.estimated_seconds - task.spent_seconds) 
        def stat_card(icon, label, value, color): 
            return ft.Container(content=ft.Column([ft.Row([ft.Icon(icon, color=color), ft.Text(label, weight="bold")], spacing=10), 
                                                   ft.Text(value, size=24, weight="bold", color=color)], spacing=5), 
                                bgcolor=COLORS["card"], padding=15, border_radius=BORDER_RADIUS) 
        content = ft.Container(width=DIALOG_WIDTH_MD, content=ft.Column([ 
            stat_card(ft.Icons.TIMER, "Time spent", seconds_to_time(task.spent_seconds), COLORS["accent"]), 
            stat_card(ft.Icons.HOURGLASS_EMPTY, "Remaining", seconds_to_time(remaining), COLORS["orange"]), 
            ft.Container(content=ft.Column([ft.Row([ft.Icon(ft.Icons.SCHEDULE, color=COLORS["blue"]), ft.Text("Estimated", weight="bold")], spacing=10), 
                                            ft.Text(seconds_to_time(task.estimated_seconds), size=18, color=COLORS["done_text"])], spacing=5), 
                         bgcolor=COLORS["card"], padding=15, border_radius=BORDER_RADIUS), 
            ft.Container(content=ft.Column([ft.Text("Progress", weight="bold"), ft.ProgressBar(value=min(pct / 100, 1.0), color=COLORS["accent"], bgcolor=COLORS["input_bg"]), 
                                            ft.Text(f"{pct:.0f}% complete", size=12, color=COLORS["done_text"])], spacing=8), 
                         bgcolor=COLORS["card"], padding=15, border_radius=BORDER_RADIUS), 
            ft.Container(content=ft.Row([ft.Icon(ft.Icons.FOLDER, size=16, color=COLORS["done_text"]), 
                                         ft.Text(f"Project: {project['name'] if project else 'Unassigned'}", size=12, color=COLORS["done_text"])], spacing=8), padding=ft.padding.only(top=10)), 
        ], spacing=10, tight=True)) 
        open_dialog(self.page, f"Stats: {task.title}", content, lambda c: [ft.TextButton("Close", on_click=c)]) 

    def notes(self, task: Task): 
        field = ft.TextField(value=task.notes, multiline=True, border_color=COLORS["border"], bgcolor=COLORS["input_bg"], 
                             border_radius=8, hint_text="Write notes here... Markdown supported", height=NOTES_FIELD_HEIGHT) 
        md = ft.Markdown(value=task.notes or "*No notes yet*", selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB) 
        preview = ft.Container(content=ft.Column([md], scroll=ft.ScrollMode.AUTO, expand=True), bgcolor=COLORS["input_bg"], 
                               border=ft.border.all(1, COLORS["border"]), border_radius=8, padding=10, height=NOTES_FIELD_HEIGHT, visible=False) 
        toggle_btn = ft.TextButton("Preview", icon=ft.Icons.VISIBILITY) 
        def toggle(e): 
            is_preview = not preview.visible 
            if is_preview: 
                md.value = field.value or "*No notes yet*" 
            field.visible, preview.visible = not is_preview, is_preview 
            toggle_btn.text, toggle_btn.icon = ("Edit", ft.Icons.EDIT) if is_preview else ("Preview", ft.Icons.VISIBILITY) 
            self.page.update() 
        toggle_btn.on_click = toggle 
        def save(e): 
            task.notes = field.value 
            self.service.persist_task(task) 
            close(e) 
            self.snack.show("Notes saved") 
        content = ft.Container(width=DIALOG_WIDTH_XL, content=ft.Column([ft.Row([toggle_btn], alignment=ft.MainAxisAlignment.END), 
                               field, preview], tight=True, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)) 
        _, close = open_dialog(self.page, f"Notes: {task.title}", content, lambda c: [ft.TextButton("Cancel", on_click=c), accent_btn("Save", save)]) 