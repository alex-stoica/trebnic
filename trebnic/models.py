import flet as ft
from dataclasses import dataclass, field
from typing import Optional, List, Set
from datetime import date, timedelta
import re

from constants import (
    NAV_INBOX, NAV_TODAY, NAV_UPCOMING, NAV_PROJECTS,
    PAGE_TASKS, COLORS
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
    notes: str = ""


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
        return cls(
            projects=[
                {"id": "sport", "name": "Sport", "icon": "🏃", "color": COLORS["green"]},
                {"id": "work", "name": "Work", "icon": "💼", "color": COLORS["blue"]},
                {"id": "chores", "name": "Chores", "icon": "🧹", "color": COLORS["orange"]},
            ],
            tasks=[
                Task(title="Design Dashboard", spent_seconds=45, estimated_seconds=120, project_id="work", due_date=date.today()),
                Task(title="Refactor Auth", spent_seconds=10, estimated_seconds=90, project_id=None, due_date=date.today() + timedelta(days=1)),
                Task(title="Gym", spent_seconds=0, estimated_seconds=60, project_id="sport", due_date=date.today(), recurrent=True),
            ],
        )

    def reset(self):
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
        new_task = Task(
            title=title,
            spent_seconds=0,
            estimated_seconds=estimated_seconds,
            project_id=project_id,
            due_date=due_date,
        )
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