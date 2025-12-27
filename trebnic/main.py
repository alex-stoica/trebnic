import flet as ft
from dataclasses import dataclass, field
from typing import Optional, List, Set
from datetime import date, timedelta
import threading
import time
import re 

from constants import PROJECT_COLORS, PROJECT_ICONS, BORDER_RADIUS

COLORS = { 
    "bg": "#1e1e1e", 
    "sidebar": "#121212", 
    "card": "#2d2d2d", 
    "card_hover": "#383838", 
    "accent": "#4a9eff", 
    "input_bg": "#252525", 
    "border": "#333", 
    "danger": "#ff6b6b", 
    "done_bg": "#1a1a1a", 
    "done_text": "#666666", 
    "unassigned": "#888888", 
    "done_tag": "#3d3d3d",
    "white": "white",  
    "green": "#4caf50",  
    "blue": "#2196f3",  
    "orange": "#ff9800",  
}  

def format_duration(minutes: int) -> str: 
    if minutes < 60: 
        return f"{minutes} min" 
    hours = minutes // 60 
    mins = minutes % 60 
    if mins == 0: 
        return f"{hours} hr" if hours == 1 else f"{hours} hrs" 
    return f"{hours} hr {mins} min" if hours == 1 else f"{hours} hrs {mins} min" 


def seconds_to_time(seconds: int) -> str:  
    mins = seconds // 60  
    secs = seconds % 60  
    return f"{mins}:{secs:02d}"  


def open_custom_dialog(page: ft.Page, title: str, content: ft.Control, actions: List[ft.Control]) -> ft.AlertDialog: 
    dialog = ft.AlertDialog( 
        modal=True, 
        title=ft.Text(title), 
        content=content, 
        actions=actions, 
        actions_alignment=ft.MainAxisAlignment.END, 
    ) 
    page.open(dialog) 
    return dialog 


def create_menu_item(icon, text, on_click, color=COLORS["accent"], text_color=None):  
    return ft.PopupMenuItem(  
        content=ft.Container(  
            content=ft.Row([ft.Icon(icon, size=18, color=color), ft.Text(text, size=14, color=text_color)], spacing=12),  
            padding=ft.padding.symmetric(vertical=5, horizontal=10)  
        ),  
        on_click=on_click,  
    )  


def create_option_row(icon, text, on_click, color=COLORS["accent"], text_color=None):  
    return ft.Container(  
        content=ft.Row([ft.Icon(icon, size=18, color=color), ft.Text(text, size=14, expand=True, color=text_color)], spacing=12),  
        padding=ft.padding.symmetric(vertical=10, horizontal=15),  
        border_radius=8,  
        ink=True,  
        on_click=on_click,  
    )  


@dataclass 
class Task: 
    title: str 
    spent_seconds: int 
    estimated_seconds: int 
    project_id: Optional[str] 
    due_date: Optional[date] 
    recurrent: bool = False 
    recurrence_interval: int = 1  
    recurrence_frequency: str = "weeks"  
    recurrence_weekdays: List[int] = field(default_factory=list)  


@dataclass  
class AppState:   
    tasks: List[Task] = field(default_factory=list)   
    done_tasks: List[Task] = field(default_factory=list)   
    projects: List[dict] = field(default_factory=list)   
    selected_nav: str = "today"   
    selected_projects: Set[str] = field(default_factory=set)   
    projects_expanded: bool = False   
    is_mobile: bool = False   
    editing_project_id: Optional[str] = None   
    default_estimated_minutes: int = 15   
    email_weekly_stats: bool = False   
    active_timer_task: Optional[Task] = None    
    timer_seconds: int = 0    
    timer_running: bool = False    

    def start_timer(self, task: Task):    
        self.active_timer_task = task    
        self.timer_seconds = 0    
        self.timer_running = True    

    def stop_timer(self) -> tuple:    
        self.timer_running = False    
        task = self.active_timer_task    
        elapsed = self.timer_seconds    
        if task and elapsed > 0:    
            task.spent_seconds += elapsed    
        self.active_timer_task = None    
        self.timer_seconds = 0    
        return task, elapsed    

    def tick(self):    
        if self.timer_running:    
            self.timer_seconds += 1    

    def _calculate_next_recurrence_date(self, task: Task) -> Optional[date]:  
        if not task.recurrent or not task.due_date:  
            return None  
        base = task.due_date  
        if task.recurrence_frequency == "days":  
            return base + timedelta(days=task.recurrence_interval)  
        elif task.recurrence_frequency == "weeks":  
            if task.recurrence_weekdays:  
                for offset in range(1, 8):  
                    next_day = base + timedelta(days=offset)  
                    if next_day.weekday() in task.recurrence_weekdays:  
                        return next_day  
            return base + timedelta(weeks=task.recurrence_interval)  
        elif task.recurrence_frequency == "months":  
            new_month = base.month + task.recurrence_interval  
            new_year = base.year + (new_month - 1) // 12  
            new_month = ((new_month - 1) % 12) + 1  
            try:  
                return base.replace(year=new_year, month=new_month)  
            except ValueError:  
                last_day = (date(new_year, new_month % 12 + 1, 1) - timedelta(days=1)).day  
                return base.replace(year=new_year, month=new_month, day=min(base.day, last_day))  
        return base + timedelta(weeks=1)  

    def complete_task(self, task: Task) -> Optional[Task]:  
        if task not in self.tasks:  
            return None  
        self.tasks.remove(task)  
        self.done_tasks.append(task)  
        if task.recurrent:  
            next_date = self._calculate_next_recurrence_date(task)  
            if next_date:  
                new_task = Task(  
                    title=task.title,  
                    spent_seconds=0,  
                    estimated_seconds=task.estimated_seconds,  
                    project_id=task.project_id,  
                    due_date=next_date,  
                    recurrent=True,  
                    recurrence_interval=task.recurrence_interval,  
                    recurrence_frequency=task.recurrence_frequency,  
                    recurrence_weekdays=task.recurrence_weekdays.copy(),  
                )  
                self.tasks.append(new_task)  
                return new_task  
        return None  

    def uncomplete_task(self, task: Task) -> bool:  
        if task in self.done_tasks:  
            self.done_tasks.remove(task)  
            self.tasks.append(task)  
            return True  
        return False  

    def delete_task(self, task: Task) -> bool:  
        if task in self.tasks:  
            self.tasks.remove(task)  
            return True  
        if task in self.done_tasks:  
            self.done_tasks.remove(task)  
            return True  
        return False  

    def postpone_task(self, task: Task) -> date:  
        if task.due_date:  
            task.due_date = task.due_date + timedelta(days=1)  
        else:  
            task.due_date = date.today() + timedelta(days=1)  
        return task.due_date  

    def _get_base_task_name(self, title: str) -> str:  
        match = re.match(r'^(.*?)\s*\((\d+)\)$', title)  
        if match:  
            return match.group(1).strip()  
        return title  

    def _get_next_copy_number(self, base_name: str) -> int:  
        max_num = 1  
        for t in self.tasks + self.done_tasks:  
            if t.title == base_name:  
                max_num = max(max_num, 1)  
            match = re.match(r'^(.*?)\s*\((\d+)\)$', t.title)  
            if match and match.group(1).strip() == base_name:  
                max_num = max(max_num, int(match.group(2)))  
        return max_num + 1  

    def duplicate_task(self, task: Task) -> Task:  
        base_name = self._get_base_task_name(task.title)  
        next_num = self._get_next_copy_number(base_name)  
        new_task = Task(  
            title=f"{base_name} ({next_num})",  
            spent_seconds=0,  
            estimated_seconds=task.estimated_seconds,  
            project_id=task.project_id,  
            due_date=task.due_date,  
            recurrent=task.recurrent,  
            recurrence_interval=task.recurrence_interval,  
            recurrence_frequency=task.recurrence_frequency,  
            recurrence_weekdays=task.recurrence_weekdays.copy() if task.recurrence_weekdays else [],  
        )  
        self.tasks.append(new_task)  
        return new_task  

    def task_name_exists(self, name: str, exclude_task: Task = None) -> bool:  
        for t in self.tasks + self.done_tasks:  
            if t != exclude_task and t.title.lower() == name.lower():  
                return True  
        return False  

    def delete_project(self, project_id: str) -> int:  
        self.projects = [p for p in self.projects if p["id"] != project_id]  
        tasks_to_remove = [t for t in self.tasks if t.project_id == project_id]  
        done_to_remove = [t for t in self.done_tasks if t.project_id == project_id]  
        for t in tasks_to_remove:  
            self.tasks.remove(t)  
        for t in done_to_remove:  
            self.done_tasks.remove(t)  
        if project_id in self.selected_projects:  
            self.selected_projects.remove(project_id)  
        return len(tasks_to_remove) + len(done_to_remove)  

    def assign_project(self, task: Task, project_id: Optional[str]) -> None:  
        task.project_id = project_id  

    def add_task(self, title: str, project_id: Optional[str] = None, due_date: Optional[date] = None, estimated_seconds: int = None) -> Task:  
        if estimated_seconds is None:  
            estimated_seconds = self.default_estimated_minutes * 60  
        new_task = Task(  
            title=title,  
            spent_seconds=0,  
            estimated_seconds=estimated_seconds,  
            project_id=project_id,  
            due_date=due_date if due_date else date.today(),  
        )  
        self.tasks.append(new_task)  
        return new_task  

    def get_project_by_id(self, project_id: Optional[str]) -> Optional[dict]:  
        for p in self.projects:  
            if p["id"] == project_id:  
                return p  
        return None  


class RecurrenceDialog(ft.AlertDialog):    
    def __init__(self, task: Task, on_save, on_close):    
        self.task = task    
        self.on_save_callback = on_save    
        self.on_close_callback = on_close    
        
        self.weekday_checkboxes = [    
            ft.Checkbox(label=day, value=i in task.recurrence_weekdays, scale=0.85)  
            for i, day in enumerate(["M", "T", "W", "T", "F", "S", "S"])  
        ]    
        
        self.weekdays_section = ft.Column([    
            ft.Text("On these days", weight="bold", size=13),    
            ft.Row(self.weekday_checkboxes[:4], spacing=0),  
            ft.Row(self.weekday_checkboxes[4:], spacing=0),  
        ], visible=True, spacing=8)    
        
        self.freq_dropdown = ft.Dropdown(    
            value=task.recurrence_frequency,  
            options=[    
                ft.dropdown.Option("days", "Days"),    
                ft.dropdown.Option("weeks", "Weeks"),    
                ft.dropdown.Option("months", "Months"),    
            ],    
            border_color=COLORS["border"],    
            bgcolor=COLORS["input_bg"],    
            border_radius=8,    
            width=120,    
            on_change=self._on_freq_change,    
        )    
        
        self.interval_field = ft.TextField(    
            value=str(task.recurrence_interval),  
            border_color=COLORS["border"],    
            bgcolor=COLORS["input_bg"],    
            border_radius=8,    
            width=50,    
            text_align=ft.TextAlign.CENTER,    
        )    
        
        self.end_type = ft.RadioGroup(    
            value="never",    
            content=ft.Column([    
                ft.Radio(value="never", label="Never"),    
                ft.Row([    
                    ft.Radio(value="on_date", label="On date"),    
                    ft.Text(    
                        (date.today() + timedelta(days=90)).strftime("%b %d, %Y"),    
                        color=COLORS["accent"],    
                    ),    
                ], spacing=8),    
            ], spacing=8),    
        )    
        
        self.enable_switch = ft.Switch(value=task.recurrent, label="Enable recurrence")    
        
        super().__init__(    
            modal=True,    
            title=ft.Text("Set Recurrence"),    
            content=ft.Container(    
                width=320,    
                content=ft.Column([    
                    self.enable_switch,    
                    ft.Divider(height=15, color=COLORS["border"]),    
                    ft.Text("Frequency", weight="bold", size=13),    
                    ft.Row([    
                        ft.Text("Repeat every", size=13),    
                        self.interval_field,    
                        self.freq_dropdown,    
                    ], spacing=8),    
                    ft.Divider(height=10, color="transparent"),    
                    self.weekdays_section,    
                    ft.Divider(height=15, color=COLORS["border"]),    
                    ft.Text("Ends", weight="bold", size=13),    
                    self.end_type,    
                ], spacing=10, tight=True),    
            ),    
            actions=[    
                ft.TextButton("Cancel", on_click=self._on_cancel),    
                ft.ElevatedButton("Save", on_click=self._on_save, bgcolor=COLORS["accent"], color=COLORS["white"]),  
            ],    
            actions_alignment=ft.MainAxisAlignment.END,    
        )    
    
    def _on_freq_change(self, e):    
        self.weekdays_section.visible = self.freq_dropdown.value == "weeks"    
        self.update()    
    
    def _on_cancel(self, e):    
        self.on_close_callback()    
    
    def _on_save(self, e):    
        self.task.recurrent = self.enable_switch.value    
        self.task.recurrence_frequency = self.freq_dropdown.value  
        self.task.recurrence_interval = int(self.interval_field.value or 1)  
        self.task.recurrence_weekdays = [i for i, cb in enumerate(self.weekday_checkboxes) if cb.value]  
        self.on_save_callback(self.task.recurrent)    


class ProjectButton(ft.Container):  
    def __init__(self, project: dict, on_toggle):  
        self.project = project  
        self.on_toggle = on_toggle  
        super().__init__(  
            content=ft.Row(
                [ft.Text(project["icon"], size=16), ft.Text(project["name"], size=14)],    
                spacing=10
            ),    
            padding=ft.padding.only(left=50, top=10, bottom=10, right=10),  
            border_radius=5,  
            data=project["id"],  
            on_click=self._handle_click,  
        )  

    def _handle_click(self, e):  
        self.on_toggle(self.project["id"])  

    def update_content(self, project: dict):  
        self.project = project  
        self.content = ft.Row(
            [ft.Text(project["icon"], size=16), ft.Text(project["name"], size=14)],    
            spacing=10
        )    


class TaskComponent: 
    def __init__(self, task: Task, is_completed: bool, callbacks: dict, state: AppState): 
        self.task = task 
        self._is_completed = is_completed 
        self.callbacks = callbacks 
        self.state = state 
    
    @property 
    def is_completed(self): 
        return self._is_completed 
    
    @is_completed.setter 
    def is_completed(self, value: bool): 
        self._is_completed = value 
    
    @property 
    def _title_style(self): 
        return ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH) if self.is_completed else None 
    
    @property 
    def _title_color(self): 
        return COLORS["done_text"] if self.is_completed else None 
    
    @property 
    def _bg_color(self): 
        return COLORS["done_bg"] if self.is_completed else COLORS["card"] 
    
    @property 
    def _opacity(self): 
        return 0.6 if self.is_completed else 1.0 
    
    def _format_title(self): 
        return f"↻ {self.task.title}" if self.task.recurrent else self.task.title 
    
    def _on_check_change(self, e): 
        if self.is_completed and not e.control.value: 
            self.callbacks["uncomplete"](self.task) 
        elif not self.is_completed and e.control.value: 
            self.callbacks["complete"](self.task) 
    
    def _create_tags_row(self): 
        project = self.callbacks["get_project"](self.task.project_id) 
        due_str = self.callbacks["format_due_date"](self.task.due_date) 
        
        if self.is_completed: 
            info_parts = [project["name"] if project else "Unassigned"] 
            if due_str: 
                info_parts.append(due_str) 
            return ft.Container( 
                content=ft.Text(" • ".join(info_parts), size=10, color=COLORS["done_text"]), 
                bgcolor=COLORS["done_tag"],    
                padding=ft.padding.symmetric(horizontal=8, vertical=2), 
                border_radius=5, 
            ) 
        
        tag_items = [] 
        if project: 
            project_tag = ft.Container( 
                content=ft.Row(
                    [    
                        ft.Text(project["icon"], size=10),    
                        ft.Text(project["name"], size=10, color=COLORS["white"])  
                    ],    
                    spacing=4,    
                    tight=True    
                ),    
                bgcolor=project["color"], 
                padding=ft.padding.symmetric(horizontal=8, vertical=2), 
                border_radius=5, 
                on_click=lambda e: self.callbacks["assign_project"](self.task), 
                ink=True, 
            ) 
        else: 
            project_tag = ft.Container( 
                content=ft.Text("Unassigned", size=10, color=COLORS["unassigned"]), 
                bgcolor=COLORS["input_bg"], 
                border=ft.border.all(1, COLORS["border"]), 
                padding=ft.padding.symmetric(horizontal=8, vertical=2), 
                border_radius=5, 
                on_click=lambda e: self.callbacks["assign_project"](self.task), 
                ink=True, 
            ) 
        tag_items.append(project_tag) 
        
        if due_str: 
            tag_items.append(ft.Container( 
                content=ft.Text(due_str, size=10, color=COLORS["done_text"]), 
                bgcolor=COLORS["input_bg"], 
                padding=ft.padding.symmetric(horizontal=8, vertical=2), 
                border_radius=5, 
                on_click=lambda e: self.callbacks["date_picker"](self.task), 
                ink=True, 
            )) 
        return ft.Row(tag_items, spacing=8, tight=True, wrap=True) 
    
    def _create_menu(self): 
        items = []    
        
        if self.state.is_mobile:    
            items.append(create_menu_item(ft.Icons.TIMER_OUTLINED, "Start Timer", lambda e: self.callbacks["start_timer"](self.task)))  
        
        items.extend([    
            create_menu_item(ft.Icons.EDIT_OUTLINED, "Rename", lambda e: self.callbacks["rename"](self.task)),  
            create_menu_item(ft.Icons.DRIVE_FILE_MOVE_OUTLINE, "Assign to project", lambda e: self.callbacks["assign_project"](self.task)),  
            create_menu_item(ft.Icons.SCHEDULE_OUTLINED, "Reschedule", lambda e: self.callbacks["date_picker"](self.task)),  
            create_menu_item(ft.Icons.NEXT_PLAN_OUTLINED, "Postpone by 1 day", lambda e: self.callbacks["postpone"](self.task)),  
            create_menu_item(ft.Icons.REPEAT, "Set Recurrence", lambda e: self.callbacks["recurrence"](self.task)),  
            create_menu_item(ft.Icons.CONTENT_COPY_OUTLINED, "Duplicate Task", lambda e: self.callbacks["duplicate"](self.task)),  
            ft.PopupMenuItem(),    
            create_menu_item(ft.Icons.INSIGHTS, "Stats", None),  
            create_menu_item(ft.Icons.STICKY_NOTE_2_OUTLINED, "Notes", None),  
            ft.PopupMenuItem(),    
            create_menu_item(ft.Icons.DELETE_OUTLINE, "Delete", lambda e: self.callbacks["delete"](self.task), color=COLORS["danger"], text_color=COLORS["danger"]),  
        ])    
        
        return ft.PopupMenuButton(
            icon=ft.Icons.MORE_HORIZ,    
            icon_color="grey",    
            tooltip="Task options",    
            menu_position=ft.PopupMenuPosition.UNDER,    
            items=items    
        )    
    
    def build(self) -> ft.Container: 
        checkbox = ft.Checkbox(value=self.is_completed, on_change=self._on_check_change) 
        title_text = ft.Text(
            self._format_title(),    
            weight="bold",    
            color=self._title_color,    
            style=self._title_style    
        )    
        tags_row = self._create_tags_row() 
        time_display = ft.Text(
            f"{seconds_to_time(self.task.spent_seconds)} / {seconds_to_time(self.task.estimated_seconds)}",    
            font_family="monospace",    
            color=COLORS["done_text"],    
            visible=not self.state.is_mobile    
        )    
        
        if self.is_completed: 
            return ft.Container(    
                padding=15,    
                bgcolor=self._bg_color,    
                border_radius=BORDER_RADIUS,    
                opacity=self._opacity,    
                content=ft.Row([checkbox, ft.Column([title_text, tags_row], expand=True, spacing=2), time_display])    
            )    
        
        if self.state.is_mobile: 
            return ft.Container(    
                padding=12,    
                bgcolor=self._bg_color,    
                border_radius=BORDER_RADIUS,    
                data=self.task,    
                content=ft.Column(    
                    [    
                        ft.Row([    
                            checkbox,    
                            ft.Text(self._format_title(), weight="bold", expand=True, size=14),    
                            self._create_menu()    
                        ]),    
                        ft.Row([tags_row], wrap=True)    
                    ],    
                    spacing=8,    
                    tight=True    
                )    
            )    
        
        return ft.Container(    
            padding=15,    
            bgcolor=self._bg_color,    
            border_radius=BORDER_RADIUS,    
            data=self.task,    
            content=ft.Row([    
                ft.Icon(ft.Icons.DRAG_INDICATOR, color=ft.Colors.GREY),    
                checkbox,    
                ft.Column([title_text, ft.Row([tags_row], tight=True)], expand=True, spacing=2),    
                ft.IconButton(    
                    ft.Icons.PLAY_ARROW,    
                    icon_color=COLORS["accent"],    
                    tooltip="Start timer",    
                    on_click=lambda e: self.callbacks["start_timer"](self.task)    
                ),    
                time_display,    
                self._create_menu()    
            ])    
        )    


def main(page: ft.Page):
    print("=== APP STARTING ===")
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    state = AppState(   
        projects=[   
            {"id": "sport", "name": "Sport", "icon": "🏃", "color": COLORS["green"]},  
            {"id": "work", "name": "Work", "icon": "💼", "color": COLORS["blue"]},  
            {"id": "chores", "name": "Chores", "icon": "🧹", "color": COLORS["orange"]},  
        ],   
        tasks=[   
            Task(
                title="Design Dashboard",    
                spent_seconds=45,    
                estimated_seconds=120,    
                project_id="work",    
                due_date=date.today()    
            ),    
            Task(
                title="Refactor Auth",    
                spent_seconds=10,    
                estimated_seconds=90,    
                project_id=None,    
                due_date=date.today() + timedelta(days=1)    
            ),    
            Task(
                title="Gym",    
                spent_seconds=0,    
                estimated_seconds=60,    
                project_id="sport",    
                due_date=date.today(),    
                recurrent=True    
            ),    
        ],   
    )   
    
    snack_bar = ft.SnackBar(content=ft.Text(""), bgcolor=COLORS["card"], duration=2000)

    def get_project_by_id(project_id):
        return state.get_project_by_id(project_id)  

    def show_snack(message, color=None, update=True):  
        snack_bar.content = ft.Text(message, color=COLORS["white"])  
        snack_bar.bgcolor = color or COLORS["card"] 
        snack_bar.open = True  
        if update: 
            page.update()  

    def format_due_date(due_date):
        if due_date is None:
            return None
        today = date.today()
        delta = (due_date - today).days
        date_str = due_date.strftime("%b %d")
        if delta < 0:
            return f"🔴 {date_str}"
        elif delta == 0:
            return f"📅 Today"
        elif delta == 1:
            return f"📆 Tomorrow"
        elif delta <= 7:
            return f"🗓️ {date_str}"
        else:
            return f"📋 {date_str}" 

    def toggle_project(project_id):  
        if project_id in state.selected_projects:  
            state.selected_projects.remove(project_id)  
        else:  
            state.selected_projects.add(project_id)  
            state.selected_nav = "projects"  
        if state.is_mobile:  
            drawer.open = False  
        update_nav_visuals()  

    project_buttons = {p["id"]: ProjectButton(p, toggle_project) for p in state.projects}  

    def get_filtered(task_list: List[Task]) -> List[Task]:   
        if state.selected_nav == "inbox": 
            return [t for t in task_list if t.project_id is None and t.due_date is None] 
        if state.selected_nav == "today":    
            today = date.today()    
            return [t for t in task_list if t.due_date is not None and t.due_date <= today]    
        if state.selected_nav == "upcoming":  
            today = date.today()  
            return [t for t in task_list if t.due_date is not None and t.due_date > today]    
        if not state.selected_projects:   
            return task_list   
        return [t for t in task_list if t.project_id in state.selected_projects]
    
    def update_nav_visuals():
        nav_inbox.selected = state.selected_nav == "inbox"   
        nav_today.selected = state.selected_nav == "today"   
        nav_upcoming.selected = state.selected_nav == "upcoming"  
        nav_projects.selected = len(state.selected_projects) > 0   
        
        for pid, btn in project_buttons.items():
            btn.bgcolor = COLORS["accent"] if pid in state.selected_projects else None   
 
        projects_items.visible = state.projects_expanded   
        projects_arrow.name = (
            ft.Icons.KEYBOARD_ARROW_DOWN if state.projects_expanded else ft.Icons.KEYBOARD_ARROW_RIGHT   
        )
        settings_menu.items = get_settings_items() 
        refresh_lists()
        page.update()

    def select_main_nav(name):
        state.selected_nav = name   
        state.selected_projects.clear()   
        if state.is_mobile:   
            drawer.open = False 
        update_nav_visuals()

    def toggle_projects_menu(e):
        state.projects_expanded = not state.projects_expanded   
        update_nav_visuals()

    def assign_project_to_task(task: Task, project_id): 
        state.assign_project(task, project_id)  
        project = get_project_by_id(project_id)
        project_name = project["name"] if project else "Unassigned"
        show_snack(f"Task assigned to {project_name}")
        refresh_lists()

    def complete_task(task: Task):  
        new_task = state.complete_task(task)  
        if new_task:  
            show_snack(f"Next occurrence scheduled for {new_task.due_date.strftime('%b %d')}")  
        refresh_lists()  

    def uncomplete_task(task: Task):  
        if state.uncomplete_task(task):  
            refresh_lists()  

    def delete_task(task: Task):  
        task_title = task.title  
        index_to_remove = None  
        for i, ctrl in enumerate(task_list.controls):  
            if ctrl.content.data == task:  
                index_to_remove = i  
                break  
        state.delete_task(task)  
        def delayed_update():  
            time.sleep(0.35)  
            if index_to_remove is not None and index_to_remove < len(task_list.controls):  
                task_list.controls.pop(index_to_remove)  
                for i, ctrl in enumerate(task_list.controls):  
                    ctrl.index = i  
            show_snack(f"'{task_title}' deleted", COLORS["danger"], update=False)  
            page.update()  
        threading.Thread(target=delayed_update, daemon=True).start()  

    def duplicate_task(task: Task):  
        new_task = state.duplicate_task(task)  
        def delayed_update():  
            time.sleep(0.35)  
            show_snack(f"Task duplicated as '{new_task.title}'", update=False)  
            refresh_lists()  
        threading.Thread(target=delayed_update, daemon=True).start()  

    def postpone_task(task: Task):  
        new_date = state.postpone_task(task)  
        new_date_str = new_date.strftime('%b %d')  
        def delayed_update():  
            time.sleep(0.35)  
            show_snack(f"'{task.title}' postponed to {new_date_str}", update=False)  
            refresh_lists()  
        threading.Thread(target=delayed_update, daemon=True).start()  

    def open_rename_dialog(task: Task): 
        error_text = ft.Text("", color=COLORS["danger"], size=12, visible=False) 
        rename_field = ft.TextField( 
            value=task.title, 
            border_color=COLORS["border"], 
            bgcolor=COLORS["input_bg"], 
            border_radius=8, 
            autofocus=True, 
        ) 
        
        def save_rename(e): 
            new_name = rename_field.value.strip() 
            if new_name: 
                if state.task_name_exists(new_name, task):  
                    error_text.value = "A task with this name already exists" 
                    error_text.visible = True 
                    page.update() 
                    return 
                task.title = new_name 
                show_snack(f"Renamed to '{new_name}'") 
                page.close(rename_dialog) 
                refresh_lists() 
        
        def close_dialog(e): 
            page.close(rename_dialog) 
        
        rename_field.on_submit = save_rename 
        
        rename_dialog = open_custom_dialog( 
            page, "Rename Task", 
            ft.Container(
                width=300,    
                content=ft.Column([rename_field, error_text], tight=True, spacing=5)    
            ),    
            [
                ft.TextButton("Cancel", on_click=close_dialog),    
                ft.ElevatedButton("Save", on_click=save_rename, bgcolor=COLORS["accent"], color=COLORS["white"])  
            ],    
        ) 

    def open_recurrence_dialog(task: Task):    
        def on_save(is_recurrent):    
            page.close(recurrence_dialog)    
            show_snack("Recurrence updated" if is_recurrent else "Recurrence disabled")    
            refresh_lists()    
        
        def on_close():    
            page.close(recurrence_dialog)    
        
        recurrence_dialog = RecurrenceDialog(task, on_save, on_close)    
        page.open(recurrence_dialog)    

    def get_task_callbacks(): 
        return { 
            "complete": complete_task, 
            "uncomplete": uncomplete_task, 
            "delete": delete_task, 
            "duplicate": duplicate_task, 
            "rename": open_rename_dialog, 
            "assign_project": open_assign_project_dialog, 
            "date_picker": open_date_picker_dialog, 
            "start_timer": start_timer_for_task, 
            "get_project": get_project_by_id, 
            "format_due_date": format_due_date, 
            "postpone": postpone_task,    
            "recurrence": open_recurrence_dialog,    
        } 

    empty_state = ft.Container(  
        content=ft.Column([  
            ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=64, color=COLORS["done_text"]),  
            ft.Text("All caught up!", size=20, weight="bold", color=COLORS["done_text"]),  
            ft.Text("Enjoy your day!", size=14, color=COLORS["done_text"]),  
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),  
        alignment=ft.alignment.center,  
        padding=40,  
        visible=False,  
    )  

    def refresh_lists():
        filtered_tasks = get_filtered(state.tasks)   
        filtered_done = get_filtered(state.done_tasks)   
        callbacks = get_task_callbacks() 
        task_list.controls.clear()
        for i, task in enumerate(filtered_tasks):
            task_list.controls.append(
                ft.ReorderableDraggable(
                    index=i,
                    content=TaskComponent(task, False, callbacks, state).build(), 
                )
            )
        done_list.controls.clear()
        for task in filtered_done:
            done_list.controls.append(TaskComponent(task, True, callbacks, state).build()) 
        empty_state.visible = len(filtered_tasks) == 0 and state.selected_nav == "today"  
        page.update()

    timer_display_text = ft.Text("00:00", size=20, weight="bold")  
    timer_task_text = ft.Text("", size=10, color=COLORS["white"])  

    def format_timer_display(seconds):  
        minutes = seconds // 60  
        secs = seconds % 60  
        return f"{minutes:02d}:{secs:02d}"  

    def timer_tick():    
        while state.timer_running:    
            time.sleep(1)    
            if state.timer_running:    
                state.tick()    
                timer_display_text.value = format_timer_display(state.timer_seconds)    
                try:    
                    page.update()    
                except:    
                    break    

    def start_timer_for_task(task: Task):    
        if state.timer_running:    
            stop_timer()    
        state.start_timer(task)    
        timer_container.visible = True    
        timer_display_text.value = "00:00"    
        timer_task_text.value = task.title    
        threading.Thread(target=timer_tick, daemon=True).start()    
        show_snack(f"Timer started for '{task.title}'")    

    def stop_timer():    
        if not state.timer_running:    
            return    
        task, elapsed_seconds = state.stop_timer()    
        if task and elapsed_seconds > 0:    
            show_snack(f"Added {format_timer_display(elapsed_seconds)} to '{task.title}'")    
            refresh_lists()    
        timer_container.visible = False    
        page.update()    

    timer_container = ft.Container(  
        content=ft.Column(
            [    
                ft.Row([ft.Icon(ft.Icons.TIMER), timer_display_text], tight=True),    
                timer_task_text,    
            ],    
            tight=True,    
            spacing=2,    
            horizontal_alignment=ft.CrossAxisAlignment.CENTER    
        ),    
        bgcolor=COLORS["accent"],  
        padding=ft.padding.symmetric(horizontal=15, vertical=5),  
        border_radius=20,  
        visible=False,  
        on_click=lambda e: stop_timer(),  
        ink=True,  
        tooltip="Click to stop timer",  
    )  

    date_picker_ref = {"picker": None} 

    def open_date_picker_dialog(task: Task): 
        is_recurrent = task.recurrent 
        
        def handle_date_change(e):
            if e.control.value:
                task.due_date = e.control.value.date() 
                show_snack(f"Date set to {task.due_date.strftime('%b %d')}") 
                refresh_lists()
        
        def close_dialog(e):
            page.close(date_dialog)
        
        if is_recurrent:
            date_dialog = open_custom_dialog( 
                page, "Select date", 
                ft.Container(
                    width=280,    
                    height=100,    
                    content=ft.Column([    
                        ft.Text("Recurrent tasks use their recurrence pattern.", color=COLORS["done_text"]),    
                        ft.Text("Edit recurrence settings to change schedule.", color=COLORS["done_text"], size=12)    
                    ], tight=True)    
                ),    
                [ft.TextButton("Close", on_click=close_dialog)], 
            ) 
        else:
            if date_picker_ref["picker"] is None: 
                date_picker_ref["picker"] = ft.DatePicker(
                    first_date=date.today(),  
                    last_date=date.today() + timedelta(days=365 * 2),
                )
                page.overlay.append(date_picker_ref["picker"])
            
            date_picker_ref["picker"].value = (
                task.due_date if task.due_date and task.due_date >= date.today() else date.today()    
            )    
            date_picker_ref["picker"].on_change = handle_date_change
            
            def open_picker(e):
                date_picker_ref["picker"].open = True
                page.update()
            
            def select_preset(days):
                task.due_date = date.today() + timedelta(days=days) 
                show_snack(f"Date set to {task.due_date.strftime('%b %d')}") 
                page.close(date_dialog)
                refresh_lists()
            
            def clear_date(e): 
                task.due_date = None 
                show_snack("Date cleared")
                page.close(date_dialog)
                refresh_lists()
            
            date_dialog = open_custom_dialog( 
                page, "Select date", 
                ft.Container( 
                    width=280, 
                    content=ft.Column([    
                        create_option_row(ft.Icons.BLOCK, "🚫 No Due Date", clear_date, color=COLORS["danger"], text_color=COLORS["done_text"]),  
                        ft.Divider(height=1, color=COLORS["border"]),    
                        create_option_row(ft.Icons.TODAY, "Today", lambda e: select_preset(0)),  
                        create_option_row(ft.Icons.CALENDAR_TODAY, "Tomorrow", lambda e: select_preset(1)),  
                        create_option_row(ft.Icons.DATE_RANGE, "Next week", lambda e: select_preset(7)),  
                        ft.Divider(height=1, color=COLORS["border"]),    
                        create_option_row(ft.Icons.CALENDAR_MONTH, "Pick a date...", open_picker),  
                    ], tight=True, spacing=4),    
                ), 
                [ft.TextButton("Cancel", on_click=close_dialog)], 
            ) 

    def open_assign_project_dialog(task: Task): 
        def select_project(project_id):
            assign_project_to_task(task, project_id) 
            page.close(assign_dialog)
        
        project_options = []
        for p in state.projects:   
            is_selected = task.project_id == p["id"] 
            project_options.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text(p["icon"], size=18),
                        ft.Text(p["name"], size=14, expand=True),
                        ft.Icon(ft.Icons.CHECK, color=COLORS["accent"], size=18) if is_selected else ft.Container(width=18),
                    ], spacing=12),
                    padding=ft.padding.symmetric(vertical=10, horizontal=15),
                    border_radius=8,
                    ink=True,
                    on_click=lambda e, pid=p["id"]: select_project(pid),
                )
            )
        
        project_options.append(ft.Divider(height=1, color=COLORS["border"]))
        project_options.append(
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CLOSE, color=COLORS["done_text"], size=18),
                    ft.Text("Unassign", size=14, color=COLORS["done_text"]),
                ], spacing=12),
                padding=ft.padding.symmetric(vertical=10, horizontal=15),
                border_radius=8,
                ink=True,
                on_click=lambda e: select_project(None),
            )
        )
        
        assign_dialog = open_custom_dialog( 
            page, "Assign to Project", 
            ft.Container(width=280, content=ft.Column(project_options, tight=True, spacing=4)), 
            [ft.TextButton("Cancel", on_click=lambda e: page.close(assign_dialog))], 
        ) 

    pending_task_details = {"estimated_minutes": state.default_estimated_minutes}  

    def add_task(title):
        project_id = list(state.selected_projects)[0] if len(state.selected_projects) == 1 else None   
        state.add_task(  
            title=title,  
            project_id=project_id,  
            due_date=date.today(),  
            estimated_seconds=pending_task_details["estimated_minutes"] * 60,  
        )  
        pending_task_details["estimated_minutes"] = state.default_estimated_minutes  
        refresh_lists()

    def on_task_submit(e):
        if e.control.value.strip():
            add_task(e.control.value.strip())
            e.control.value = ""
            details_button.visible = False
            page.update()

    def on_input_change(e):
        details_button.visible = bool(e.control.value.strip())
        page.update()

    def on_reorder(e: ft.OnReorderEvent):
        filtered_tasks = get_filtered(state.tasks)   
        
        if len(task_list.controls) != len(filtered_tasks):
            refresh_lists()
            return

        if state.selected_projects:   
            task_to_move = filtered_tasks[e.old_index]
            old_real_index = state.tasks.index(task_to_move)   
            target_task = filtered_tasks[e.new_index] if e.new_index < len(filtered_tasks) else None
            state.tasks.pop(old_real_index)   
            if target_task:
                new_real_index = (
                    state.tasks.index(target_task) if target_task in state.tasks else len(state.tasks)    
                )    
                state.tasks.insert(new_real_index, task_to_move)   
            else:
                state.tasks.append(task_to_move)   
        else:
            state.tasks.insert(e.new_index, state.tasks.pop(e.old_index))   
        refresh_lists()

    new_project_name = ft.TextField(
        hint_text="Project name",
        border_color=COLORS["border"],
        bgcolor=COLORS["input_bg"],
        border_radius=8,
        autofocus=True,
    )

    selected_icon = {"value": PROJECT_ICONS[0]}
    selected_color = {"value": PROJECT_COLORS[0]["value"]}

    icon_display = ft.Text(selected_icon["value"], size=20)
    color_display = ft.Container(width=20, height=20, border_radius=10, bgcolor=selected_color["value"])

    def get_create_project_content():
        return ft.Column([
            ft.Row([
                ft.Text("Icon:", size=14, width=50),
                icon_dropdown_button,
            ], spacing=10),
            ft.Row([
                ft.Text("Color:", size=14, width=50),
                color_dropdown_button,
            ], spacing=10),
            new_project_name,
        ], spacing=15, tight=True)

    def get_create_project_actions():
        action_text = "Save" if state.editing_project_id else "Create"   
        actions = [  
            ft.TextButton("Cancel", on_click=close_create_dialog),  
        ]  
        if state.editing_project_id:  
            actions.append(ft.TextButton("Delete", on_click=delete_current_project, style=ft.ButtonStyle(color=COLORS["danger"])))  
        actions.append(ft.ElevatedButton(action_text, on_click=save_project, bgcolor=COLORS["accent"], color=COLORS["white"]))  
        return actions  

    def delete_current_project(e):  
        project_id = state.editing_project_id  
        project = get_project_by_id(project_id)  
        if not project:  
            return  
        
        def confirm_delete(e):  
            deleted_count = state.delete_project(project_id)  
            if project_id in project_buttons:  
                del project_buttons[project_id]  
            state.editing_project_id = None  
            page.close(confirm_dialog)  
            page.close(create_project_dialog)  
            show_snack(f"Project '{project['name']}' deleted ({deleted_count} tasks removed)", COLORS["danger"])  
            rebuild_projects_items()  
            update_nav_visuals()  
        
        def cancel_delete(e):  
            page.close(confirm_dialog)  
        
        confirm_dialog = open_custom_dialog(  
            page, "Delete Project",  
            ft.Text(f"Delete '{project['name']}' and all its tasks?"),  
            [  
                ft.TextButton("Cancel", on_click=cancel_delete),  
                ft.ElevatedButton("Delete", on_click=confirm_delete, bgcolor=COLORS["danger"], color=COLORS["white"]),  
            ],  
        )  

    def rebuild_projects_items():  
        projects_items.controls.clear()  
        for p in state.projects:  
            if p["id"] not in project_buttons:  
                project_buttons[p["id"]] = ProjectButton(p, toggle_project)  
            projects_items.controls.append(project_buttons[p["id"]])  

    def switch_to_icon_picker(e):
        temp_icon = {"value": selected_icon["value"]}
        temp_icon_display = ft.Text(temp_icon["value"], size=32)
        
        def on_icon_tap(icon):
            temp_icon["value"] = icon
            temp_icon_display.value = icon
            for ctrl in icon_grid.controls:
                ctrl.bgcolor = COLORS["accent"] if ctrl.data == icon else COLORS["card"]
            page.update()
        
        def confirm_icon(e):
            selected_icon["value"] = temp_icon["value"]
            icon_display.value = temp_icon["value"]
            restore_main_dialog()
        
        icon_grid = ft.GridView(
            runs_count=6,
            max_extent=45,
            spacing=5,
            run_spacing=5,
            controls=[
                ft.Container(
                    content=ft.Text(icon, size=20),
                    alignment=ft.alignment.center,
                    border_radius=8,
                    bgcolor=COLORS["accent"] if icon == selected_icon["value"] else COLORS["card"],
                    data=icon,
                    on_click=lambda e, i=icon: on_icon_tap(i),
                    ink=True,
                )
                for icon in PROJECT_ICONS
            ],
        )
        
        create_project_dialog.title = ft.Text("Select icon")
        create_project_dialog.content = ft.Container(
            width=300,
            height=375,
            content=ft.Column([
                ft.Container(
                    content=temp_icon_display,
                    alignment=ft.alignment.center,
                    bgcolor=COLORS["card"],
                    border_radius=10,
                    padding=15,
                    margin=ft.margin.only(bottom=10),
                ),
                icon_grid,
            ], tight=True),
        )
        create_project_dialog.actions = [
            ft.TextButton("Back", on_click=lambda e: restore_main_dialog()),
            ft.ElevatedButton("Select", on_click=confirm_icon, bgcolor=COLORS["accent"], color=COLORS["white"]),  
        ]
        page.update()

    def switch_to_color_picker(e):
        temp_color = {"value": selected_color["value"]}
        
        def on_color_tap(color_value):
            temp_color["value"] = color_value
            for ctrl in color_list.controls:
                is_sel = ctrl.data == color_value
                ctrl.content.controls[2].visible = is_sel
            page.update()
        
        def confirm_color(e):
            selected_color["value"] = temp_color["value"]
            color_display.bgcolor = temp_color["value"]
            restore_main_dialog()
        
        color_options = []
        for c in PROJECT_COLORS:
            is_selected = c["value"] == selected_color["value"]
            color_options.append(
                ft.Container(
                    content=ft.Row([
                        ft.Container(width=24, height=24, border_radius=12, bgcolor=c["value"]),
                        ft.Text(c["name"], size=14, expand=True),
                        ft.Icon(ft.Icons.CHECK, color=COLORS["accent"], size=18, visible=is_selected),
                    ], spacing=12),
                    padding=ft.padding.symmetric(vertical=8, horizontal=12),
                    border_radius=8,
                    ink=True,
                    data=c["value"],
                    on_click=lambda e, cv=c["value"]: on_color_tap(cv),
                )
            )
        
        color_list = ft.ListView(controls=color_options, spacing=4, height=250)
        
        create_project_dialog.title = ft.Text("Select Color")
        create_project_dialog.content = ft.Container(width=280, content=color_list)
        create_project_dialog.actions = [
            ft.TextButton("Back", on_click=lambda e: restore_main_dialog()),
            ft.ElevatedButton("Select", on_click=confirm_color, bgcolor=COLORS["accent"], color=COLORS["white"]),  
        ]
        page.update()

    def restore_main_dialog():
        title = "Edit Project" if state.editing_project_id else "Create New Project"   
        create_project_dialog.title = ft.Text(title) 
        create_project_dialog.content = ft.Container(width=300, content=get_create_project_content())
        create_project_dialog.actions = get_create_project_actions()
        page.update()

    icon_dropdown_button = ft.Container(
        content=ft.Row([icon_display, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=20)], tight=True),
        padding=ft.padding.symmetric(horizontal=10, vertical=5),
        border_radius=8,
        bgcolor=COLORS["input_bg"],
        border=ft.border.all(1, COLORS["border"]),
        on_click=switch_to_icon_picker, 
        ink=True,
    ) 
      

    color_dropdown_button = ft.Container(
        content=ft.Row(
            [color_display, ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=20)],    
            spacing=8,    
            tight=True    
        ),    
        padding=ft.padding.symmetric(horizontal=10, vertical=5),
        border_radius=8,
        bgcolor=COLORS["input_bg"],
        border=ft.border.all(1, COLORS["border"]),
        on_click=switch_to_color_picker, 
        ink=True,
    )

    def close_create_dialog(e):
        state.editing_project_id = None   
        page.close(create_project_dialog)

    def save_project(e): 
        name = new_project_name.value.strip()
        icon = selected_icon["value"] 
        color = selected_color["value"]
        if name:
            if state.editing_project_id:   
                for p in state.projects:   
                    if p["id"] == state.editing_project_id:   
                        p["name"] = name 
                        p["icon"] = icon 
                        p["color"] = color 
                        break 
                old_btn = project_buttons[state.editing_project_id]   
                project = get_project_by_id(state.editing_project_id)  
                old_btn.update_content(project)  
                msg = f"Project '{name}' updated" 
            else: 
                new_id = name.lower().replace(" ", "_")
                new_project = {
                    "id": new_id,
                    "name": name,
                    "icon": icon,
                    "color": color,
                }
                state.projects.append(new_project)   
                project_buttons[new_id] = ProjectButton(new_project, toggle_project)  
                projects_items.controls.append(project_buttons[new_id])
                msg = f"Project '{name}' created" 
            new_project_name.value = ""
            selected_icon["value"] = PROJECT_ICONS[0]
            selected_color["value"] = PROJECT_COLORS[0]["value"]
            icon_display.value = PROJECT_ICONS[0]
            color_display.bgcolor = PROJECT_COLORS[0]["value"]
            state.editing_project_id = None   
            page.close(create_project_dialog)
            show_snack(msg) 
            refresh_lists() 
            page.update()

    create_project_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Create new project"),
        content=ft.Container(
            width=300,
            content=get_create_project_content(), 
        ),
        actions=get_create_project_actions(), 
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def open_project_dialog(project=None): 
        if project: 
            state.editing_project_id = project["id"]   
            new_project_name.value = project["name"] 
            selected_icon["value"] = project["icon"] 
            selected_color["value"] = project["color"] 
            icon_display.value = project["icon"] 
            color_display.bgcolor = project["color"] 
        else: 
            state.editing_project_id = None   
            new_project_name.value = "" 
            selected_icon["value"] = PROJECT_ICONS[0] 
            selected_color["value"] = PROJECT_COLORS[0]["value"] 
            icon_display.value = PROJECT_ICONS[0] 
            color_display.bgcolor = PROJECT_COLORS[0]["value"] 
        restore_main_dialog() 
        page.open(create_project_dialog) 

    def open_create_project_dialog(e):
        open_project_dialog() 

    def open_preferences_dialog(e):   
        duration_label = ft.Text(
            format_duration(state.default_estimated_minutes),    
            size=16,    
            weight="bold"    
        )    
        
        def on_slider_change(e): 
            minutes = int(e.control.value) * 5 
            duration_label.value = format_duration(minutes) 
            page.update() 
        
        time_slider = ft.Slider( 
            min=1, 
            max=100, 
            divisions=99, 
            value=state.default_estimated_minutes // 5, 
            label="{value}", 
            on_change=on_slider_change, 
        ) 
         
        email_checkbox = ft.Checkbox(   
            value=state.email_weekly_stats,   
            label="Email weekly stats",   
        )   
         
        def save_preferences(e):   
            state.default_estimated_minutes = int(time_slider.value) * 5 
            state.email_weekly_stats = email_checkbox.value   
            show_snack("Preferences saved")   
            page.close(pref_dialog)   
         
        pref_dialog = open_custom_dialog( 
            page, "Preferences", 
            ft.Container( 
                width=300, 
                content=ft.Column([ 
                    ft.Text("Default estimated time", weight="bold", size=14), 
                    ft.Row([ft.Icon(ft.Icons.TIMER, size=18), duration_label], spacing=8), 
                    time_slider, 
                    ft.Text("5 min - 8 hrs 20 min", size=11, color=COLORS["done_text"]), 
                    ft.Divider(height=20, color=COLORS["border"]), 
                    ft.Text("Notifications", weight="bold", size=14), 
                    email_checkbox, 
                ], spacing=12, tight=True), 
            ), 
            [
                ft.TextButton("Cancel", on_click=lambda e: page.close(pref_dialog)),    
                ft.ElevatedButton(    
                    "Save",    
                    on_click=save_preferences,    
                    bgcolor=COLORS["accent"],    
                    color=COLORS["white"]  
                )    
            ],    
        ) 

    def open_add_details_dialog(e):  
        duration_label = ft.Text(  
            format_duration(pending_task_details["estimated_minutes"]),  
            size=16,  
            weight="bold"  
        )  
        def on_slider_change(ev):  
            minutes = int(ev.control.value) * 5  
            duration_label.value = format_duration(minutes)  
            page.update()  
        time_slider = ft.Slider(  
            min=1,  
            max=100,  
            divisions=99,  
            value=pending_task_details["estimated_minutes"] // 5,  
            label="{value}",  
            on_change=on_slider_change,  
        )  
        def save_details(ev):  
            pending_task_details["estimated_minutes"] = int(time_slider.value) * 5  
            details_button.content.controls[1].value = f"{format_duration(pending_task_details['estimated_minutes'])}"  
            page.close(details_dialog)  
            page.update()  
        details_dialog = open_custom_dialog(  
            page, "Task Details",  
            ft.Container(  
                width=300,  
                content=ft.Column([  
                    ft.Text("Estimated time", weight="bold", size=14),  
                    ft.Row([ft.Icon(ft.Icons.TIMER, size=18), duration_label], spacing=8),  
                    time_slider,  
                    ft.Text("5 min - 8 hrs 20 min", size=11, color=COLORS["done_text"]),  
                ], spacing=12, tight=True),  
            ),  
            [  
                ft.TextButton("Cancel", on_click=lambda ev: page.close(details_dialog)),  
                ft.ElevatedButton("Save", on_click=save_details, bgcolor=COLORS["accent"], color=COLORS["white"]),  
            ],  
        )  

    task_input = ft.TextField(
        hint_text="Add a new task...", 
        border_color=COLORS["border"],
        bgcolor=COLORS["input_bg"],
        expand=True,
        on_submit=on_task_submit,
        on_change=on_input_change,
        border_radius=BORDER_RADIUS, 
        prefix_icon=ft.Icons.ADD_TASK,
    )

    details_button = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.TUNE, size=16, color=COLORS["accent"]),
                ft.Text("Add Details", size=13, color=COLORS["accent"]),
                ft.Icon(ft.Icons.KEYBOARD_ARROW_RIGHT, size=16, color=COLORS["accent"]),
            ],
            spacing=4,
        ),
        padding=ft.padding.symmetric(horizontal=12, vertical=10),
        border_radius=BORDER_RADIUS, 
        bgcolor=COLORS["card"],
        visible=False,
        tooltip="Click to add tags, due date, and more",
        on_click=open_add_details_dialog,  
    )

    def submit_task_button_click(e):  
        if task_input.value.strip():  
            add_task(task_input.value.strip())  
            task_input.value = ""  
            details_button.visible = False  
            page.update()

    submit_button = ft.IconButton(
        icon=ft.Icons.SEND, 
        icon_color=COLORS["accent"], 
        on_click=submit_task_button_click, 
        visible=False,  
    )

    task_input_row = ft.Row(
        controls=[task_input, details_button, submit_button],
        spacing=10,
    )

    task_list = ft.ReorderableListView(
        show_default_drag_handles=False,
        on_reorder=on_reorder,
        controls=[],
    )

    done_list = ft.Column(
        controls=[],
        spacing=8,
    )
 
    nav_inbox = ft.ListTile(
        leading=ft.Icon(ft.Icons.INBOX),
        title=ft.Text("Inbox"),
        selected=False,
        selected_color=COLORS["accent"],
        on_click=lambda e: select_main_nav("inbox"),
    )
    
    nav_today = ft.ListTile(
        leading=ft.Icon(ft.Icons.TODAY),
        title=ft.Text("Today"),
        selected=True,
        selected_color=COLORS["accent"],
        on_click=lambda e: select_main_nav("today"),
    )
    
    nav_upcoming = ft.ListTile(  
        leading=ft.Icon(ft.Icons.UPCOMING),  
        title=ft.Text("Upcoming"),  
        selected=False,  
        selected_color=COLORS["accent"],  
        on_click=lambda e: select_main_nav("upcoming"),  
    )  
    
    projects_arrow = ft.Icon(ft.Icons.KEYBOARD_ARROW_RIGHT, size=20, color="grey")

    add_project_button = ft.Container(
        content=ft.Text("➕", size=14),
        padding=5,
        border_radius=5,
        on_click=open_create_project_dialog,
        tooltip="Create new project",
    )

    nav_projects = ft.ListTile(
        leading=ft.Icon(ft.Icons.FOLDER_OUTLINED),
        title=ft.Text("Projects"),
        selected=False,
        selected_color=COLORS["accent"],
        trailing=ft.Row([projects_arrow, add_project_button], spacing=5, tight=True),
        on_click=toggle_projects_menu,
    )

    projects_items = ft.Column(
        visible=False,
        spacing=0,
        controls=[project_buttons[p["id"]] for p in state.projects],   
    )
 
    nav_content = ft.Column( 
        controls=[ 
            ft.Text("Trebnic", size=20, weight="bold"), 
            ft.Divider(color="grey"), 
            nav_inbox, 
            nav_today, 
            nav_upcoming,  
            nav_projects, 
            projects_items, 
        ], 
    ) 
 
    drawer = ft.NavigationDrawer(  
        bgcolor=COLORS["sidebar"],  
        controls=[],  
    ) 
    page.drawer = drawer

    sidebar = ft.Container(
        width=250,
        bgcolor=COLORS["sidebar"],
        padding=20,
        content=nav_content,
        visible=False,  
    )
    
    menu_button = ft.IconButton( 
        icon=ft.Icons.MENU, 
        icon_color=COLORS["accent"], 
        on_click=lambda e: open_drawer(e), 
        visible=True,  
    )

    def get_settings_items(): 
        items = [ 
            ft.PopupMenuItem(text="Profile", icon=ft.Icons.PERSON), 
            ft.PopupMenuItem(text="Preferences", icon=ft.Icons.TUNE, on_click=open_preferences_dialog),   
        ] 
        if len(state.selected_projects) == 1:   
            project = get_project_by_id(list(state.selected_projects)[0])   
            if project: 
                items.append(ft.PopupMenuItem()) 
                items.append(ft.PopupMenuItem( 
                    text=f"Edit '{project['name']}'", 
                    icon=ft.Icons.EDIT, 
                    on_click=lambda e, p=project: open_project_dialog(p), 
                )) 
        items.append(ft.PopupMenuItem()) 
        items.append(ft.PopupMenuItem(text="Logout", icon=ft.Icons.LOGOUT)) 
        return items 

    settings_menu = ft.PopupMenuButton( 
        icon=ft.Icons.SETTINGS, 
        items=get_settings_items(), 
    ) 
 
    header_row = ft.Row( 
        controls=[ 
            menu_button, 
            timer_container,  
            ft.Container(expand=True), 
            settings_menu, 
        ], 
    ) 

    main_area = ft.Container(
        expand=True,
        bgcolor=COLORS["bg"],
        alignment=ft.alignment.top_left,  
        padding=ft.padding.only(left=20, right=20, top=20, bottom=20), 
        content=ft.Column(
            alignment=ft.MainAxisAlignment.START, 
            controls=[
                header_row,  
                ft.Divider(height=30, color="transparent"),
                task_input_row,
                ft.Divider(height=15, color="transparent"),
                ft.Text("TODAY", color="grey", weight="bold"),
                empty_state,  
                task_list,
                ft.Divider(height=25, color="transparent"),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=16, color=COLORS["done_text"]),
                        ft.Text("DONE", color=COLORS["done_text"], weight="bold"),
                    ],
                    spacing=8,
                ),
                ft.Divider(height=10, color="transparent"),
                done_list,
            ],
            scroll=ft.ScrollMode.AUTO, 
        ),
    )
 
    main_row = ft.Row( 
        expand=True, 
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,  
        spacing=0, 
        controls=[sidebar, main_area], 
    )

    def open_drawer(e): 
        drawer.open = True  
        page.update()
 
    def handle_resize(e=None): 
        width = page.width or 800 
        state.is_mobile = width < 768   
        
        if state.is_mobile:   
            sidebar.visible = False 
            sidebar.content = None 
            menu_button.visible = True  
            submit_button.visible = True  
            drawer.controls = [ft.Container(padding=20, content=nav_content)] 
        else: 
            drawer.controls = []  
            sidebar.content = nav_content  
            sidebar.visible = True 
            menu_button.visible = False 
            submit_button.visible = False 
        
        refresh_lists()  
        page.update()

    page.on_resized = handle_resize 
 
    page.drawer = drawer
    page.overlay.append(snack_bar)
    page.add(main_row) 
    
    handle_resize()  
    refresh_lists()

ft.app(target=main)