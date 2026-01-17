import flet as ft
from dataclasses import dataclass, field
from typing import Optional, List, Set, Tuple 
from datetime import date, timedelta
import calendar 
import re

from constants import (
    NAV_INBOX, NAV_TODAY, NAV_UPCOMING, NAV_PROJECTS, 
    PAGE_TASKS, COLORS, DEFAULT_ESTIMATED_SECONDS 
)
from database import db


@dataclass
class Task:
    title: str
    spent_seconds: int
    estimated_seconds: int
    project_id: Optional[str]
    due_date: Optional[date]
    id: Optional[int] = None
    recurrent: bool = False
    recurrence_interval: int = 1
    recurrence_frequency: str = "weeks"
    recurrence_weekdays: List[int] = field(default_factory=list)
    notes: str = ""
    sort_order: int = 0 

    def to_dict(self, is_done: bool = False) -> dict:
        return { 
            "id": self.id, "title": self.title, "spent_seconds": self.spent_seconds, 
            "estimated_seconds": self.estimated_seconds, "project_id": self.project_id, 
            "due_date": self.due_date, "is_done": 1 if is_done else 0, 
            "recurrent": 1 if self.recurrent else 0, 
            "recurrence_interval": self.recurrence_interval, 
            "recurrence_frequency": self.recurrence_frequency, 
            "recurrence_weekdays": self.recurrence_weekdays, "notes": self.notes, 
            "sort_order": self.sort_order 
        } 

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls( 
            id=d.get("id"), title=d["title"], spent_seconds=d.get("spent_seconds", 0), 
            estimated_seconds=d.get("estimated_seconds", DEFAULT_ESTIMATED_SECONDS), 
            project_id=d.get("project_id"), due_date=d.get("due_date"), 
            recurrent=bool(d.get("recurrent", 0)), 
            recurrence_interval=d.get("recurrence_interval", 1), 
            recurrence_frequency=d.get("recurrence_frequency", "weeks"), 
            recurrence_weekdays=d.get("recurrence_weekdays", []), 
            notes=d.get("notes", ""), sort_order=d.get("sort_order", 0) 
        ) 


@dataclass
class AppState:
    tasks: List[Task] = field(default_factory=list)
    done_tasks: List[Task] = field(default_factory=list)
    projects: List[dict] = field(default_factory=list)
    selected_nav: str = NAV_TODAY
    selected_projects: Set[str] = field(default_factory=set)
    projects_expanded: bool = False
    is_mobile: bool = False
    editing_project_id: Optional[str] = None
    default_estimated_minutes: int = 15
    email_weekly_stats: bool = False
    active_timer_task: Optional[Task] = None
    timer_seconds: int = 0
    timer_running: bool = False
    current_page: str = PAGE_TASKS

    @classmethod
    def get_defaults(cls) -> "AppState":
        state = cls(
            default_estimated_minutes=db.get_setting("default_estimated_minutes", 15),
            email_weekly_stats=db.get_setting("email_weekly_stats", False),
        )
        if db.is_empty():
            state._init_default_data()
        else:
            state._load_from_db()
        return state

    def _init_default_data(self):
        defaults = [ 
            {"id": "sport", "name": "Sport", "icon": "🏃", "color": COLORS["green"]}, 
            {"id": "work", "name": "Work", "icon": "💼", "color": COLORS["blue"]}, 
            {"id": "chores", "name": "Chores", "icon": "🧹", "color": COLORS["orange"]} 
        ] 
        for p in defaults: 
            db.save_project(p)
            self.projects.append(p)
        default_tasks = [
            Task( 
                title="Design dashboard", spent_seconds=45, estimated_seconds=120, 
                project_id="work", due_date=date.today() 
            ), 
            Task( 
                title="Refactor auth", spent_seconds=10, estimated_seconds=90, 
                project_id=None, due_date=date.today() + timedelta(days=1) 
            ), 
            Task( 
                title="Gym", spent_seconds=0, estimated_seconds=60, 
                project_id="sport", due_date=date.today(), recurrent=True 
            ), 
        ]
        for i, t in enumerate(default_tasks): 
            t.sort_order = i 
            t.id = db.save_task(t.to_dict())
            self.tasks.append(t)

    def _load_from_db(self):
        self.projects = db.load_projects()
        for row in db.load_tasks():
            task = Task.from_dict(row)
            (self.done_tasks if row["is_done"] else self.tasks).append(task)

    def persist_task(self, task: Task):
        is_done = task in self.done_tasks
        task.id = db.save_task(task.to_dict(is_done))

    def persist_task_order(self): 
        for i, task in enumerate(self.tasks): 
            task.sort_order = i 
            self.persist_task(task) 

    def save_settings(self):
        db.set_setting("default_estimated_minutes", self.default_estimated_minutes)
        db.set_setting("email_weekly_stats", self.email_weekly_stats)

    def reset(self):
        db.clear_all()
        defaults = AppState.get_defaults()
        for key, value in vars(defaults).items():
            setattr(self, key, value)

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
            self.persist_task(task)
        self.active_timer_task = None
        self.timer_seconds = 0
        return task, elapsed

    def tick(self):
        if self.timer_running:
            self.timer_seconds += 1

    def _add_months(self, base: date, months: int) -> date: 
        """Add months to date, handling edge cases like Feb 29."""
        total_months = base.year * 12 + base.month - 1 + months 
        new_year = total_months // 12 
        new_month = total_months % 12 + 1 
        last_day_of_month = calendar.monthrange(new_year, new_month)[1] 
        new_day = min(base.day, last_day_of_month) 
        return date(new_year, new_month, new_day) 

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
            return self._add_months(base, task.recurrence_interval) 
        return base + timedelta(weeks=1)

    def complete_task(self, task: Task) -> Optional[Task]:
        if task not in self.tasks:
            return None
        self.tasks.remove(task)
        self.done_tasks.append(task)
        db.save_task(task.to_dict(is_done=True))
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
                new_task.id = db.save_task(new_task.to_dict())
                self.tasks.append(new_task)
                return new_task
        return None

    def uncomplete_task(self, task: Task) -> bool:
        if task in self.done_tasks:
            self.done_tasks.remove(task)
            self.tasks.append(task)
            db.save_task(task.to_dict(is_done=False))
            return True
        return False

    def delete_task(self, task: Task) -> bool:
        if task in self.tasks:
            self.tasks.remove(task)
            if task.id:
                db.delete_task(task.id)
            return True
        if task in self.done_tasks:
            self.done_tasks.remove(task)
            if task.id:
                db.delete_task(task.id)
            return True
        return False

    def postpone_task(self, task: Task) -> date:
        if task.due_date:
            task.due_date = task.due_date + timedelta(days=1)
        else:
            task.due_date = date.today() + timedelta(days=1)
        self.persist_task(task)
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
        new_task.id = db.save_task(new_task.to_dict())
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
        db.delete_project(project_id)
        return len(tasks_to_remove) + len(done_to_remove)

    def assign_project(self, task: Task, project_id: Optional[str]) -> None:
        task.project_id = project_id
        self.persist_task(task)

    def add_task(
            self,
            title: str,
            project_id: Optional[str] = None,
            due_date: Optional[date] = None,
            estimated_seconds: int = None
        ) -> Task:
        if estimated_seconds is None:
            estimated_seconds = self.default_estimated_minutes * 60
        if due_date is None:
            if self.selected_nav == NAV_INBOX:
                due_date = None
            elif self.selected_nav == NAV_UPCOMING:
                due_date = date.today() + timedelta(days=1)
            else:
                due_date = date.today()
        max_order = max((t.sort_order for t in self.tasks), default=-1)  
        new_task = Task(
            title=title,
            spent_seconds=0,
            estimated_seconds=estimated_seconds,
            project_id=project_id,
            due_date=due_date,
            sort_order=max_order + 1, 
        )
        new_task.id = db.save_task(new_task.to_dict())
        self.tasks.append(new_task)
        return new_task

    def get_project_by_id(self, project_id: Optional[str]) -> Optional[dict]:
        for p in self.projects:
            if p["id"] == project_id:
                return p
        return None


class AppController:
    """Central controller for app operations - eliminates prop drilling."""

    def __init__(self, page: ft.Page, state: AppState):
        self.page = page
        self.state = state
        self._initialized = False
        self.refresh_ui = None
        self.update_nav = None
        self.complete = None
        self.uncomplete = None
        self.delete = None
        self.duplicate = None
        self.rename = None
        self.assign_project = None
        self.date_picker = None
        self.start_timer = None
        self.postpone = None
        self.recurrence = None
        self.stats = None
        self.notes = None

    def wire(self, **callbacks):
        """Wire all callbacks at once. Must be called before using controller."""
        for name, callback in callbacks.items():
            if hasattr(self, name):
                setattr(self, name, callback)
        self._initialized = True

    def _check_initialized(self):
        if not self._initialized:
            raise RuntimeError("Controller not initialized. Call wire() first.")

    def get_project(self, project_id: Optional[str]) -> Optional[dict]:
        return self.state.get_project_by_id(project_id)

    def format_due_date(self, due_date: Optional[date]) -> Optional[str]:
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
        return f"📋 {date_str}"

    def toggle_project(self, project_id: str):
        if project_id in self.state.selected_projects:
            self.state.selected_projects.remove(project_id)
        else:
            self.state.selected_projects.add(project_id)
            self.state.selected_nav = NAV_PROJECTS
        if self.state.is_mobile:
            self.page.drawer.open = False
        self._check_initialized()
        self.update_nav()

    def get_filtered_tasks(self) -> Tuple[List[Task], List[Task]]: 
        """Returns (pending, done) tasks filtered by current nav selection.""" 
        s = self.state 
        if s.selected_nav == NAV_INBOX: 
            pending = [t for t in s.tasks if t.project_id is None and t.due_date is None] 
            done = [t for t in s.done_tasks if t.project_id is None and t.due_date is None] 
            return pending, done 
        if s.selected_nav == NAV_TODAY: 
            today = date.today() 
            pending = [t for t in s.tasks if t.due_date and t.due_date <= today] 
            done = [t for t in s.done_tasks if t.due_date and t.due_date <= today] 
            return pending, done 
        if s.selected_nav == NAV_UPCOMING: 
            today = date.today() 
            pending = [t for t in s.tasks if t.due_date and t.due_date > today] 
            done = [t for t in s.done_tasks if t.due_date and t.due_date > today] 
            return pending, done 
        if not s.selected_projects: 
            return s.tasks[:], s.done_tasks[:] 
        pending = [t for t in s.tasks if t.project_id in s.selected_projects] 
        done = [t for t in s.done_tasks if t.project_id in s.selected_projects] 
        return pending, done 