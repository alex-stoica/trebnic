import uuid
from datetime import date, timedelta
from typing import List, Tuple, Optional

from config import NAV_INBOX, NAV_TODAY, NAV_UPCOMING, NAV_PROJECTS, RecurrenceFrequency
from database import db
from models.entities import AppState, Task, Project, TimeEntry
from services.recurrence import calculate_next_recurrence


class TaskService:
    def __init__(self, state: AppState) -> None:
        self.state = state

    @staticmethod
    def load_state() -> AppState:
        state = AppState()
        
        # Load projects
        for p_dict in db.load_projects():
            state.projects.append(Project.from_dict(p_dict))
            
        # Load tasks
        all_tasks = db.load_tasks()
        for t_dict in all_tasks:
            task = Task.from_dict(t_dict)
            if t_dict.get("is_done"):
                state.done_tasks.append(task)
            else:
                state.tasks.append(task)
                
        # Load settings
        state.default_estimated_minutes = db.get_setting("default_estimated_minutes", 15)
        state.email_weekly_stats = db.get_setting("email_weekly_stats", False)
        
        return state

    def add_task(self, title: str, project_id: Optional[str] = None, estimated_seconds: int = 900) -> Task:
        task = Task(
            title=title,
            project_id=project_id,
            estimated_seconds=estimated_seconds,
            spent_seconds=0,
            due_date=date.today() if self.state.selected_nav == NAV_TODAY else None,
            sort_order=len(self.state.tasks)
        )
        task.id = db.save_task(task.to_dict())
        self.state.tasks.append(task)
        return task

    def persist_task(self, task: Task) -> None:
        is_done = task in self.state.done_tasks
        db.save_task(task.to_dict(is_done=is_done))

    def complete_task(self, task: Task) -> Optional[Task]:
        if task in self.state.tasks:
            self.state.tasks.remove(task)
            self.state.done_tasks.append(task)
            db.save_task(task.to_dict(is_done=True))

            if task.recurrent:
                next_date = calculate_next_recurrence(task)
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
                        recurrence_weekdays=task.recurrence_weekdays,
                        notes=task.notes,
                        sort_order=task.sort_order
                    )
                    new_task.id = db.save_task(new_task.to_dict())
                    self.state.tasks.append(new_task)
                    return new_task
        return None

    def uncomplete_task(self, task: Task) -> bool:
        if task in self.state.done_tasks:
            self.state.done_tasks.remove(task)
            self.state.tasks.append(task)
            db.save_task(task.to_dict(is_done=False))
            return True
        return False

    def delete_task(self, task: Task) -> None:
        if task in self.state.tasks:
            self.state.tasks.remove(task)
        elif task in self.state.done_tasks:
            self.state.done_tasks.remove(task)
        if task.id:
            db.delete_task(task.id)

    def duplicate_task(self, task: Task) -> Task:
        new_task = Task.from_dict(task.to_dict())
        new_task.id = None
        new_task.title = f"{task.title} (copy)"
        new_task.id = db.save_task(new_task.to_dict())
        self.state.tasks.append(new_task)
        return new_task

    def postpone_task(self, task: Task) -> date:
        current = task.due_date or date.today()
        task.due_date = current + timedelta(days=1)
        self.persist_task(task)
        return task.due_date

    def get_filtered_tasks(self) -> Tuple[List[Task], List[Task]]:
        nav = self.state.selected_nav
        today = date.today()
        
        pending = self.state.tasks
        done = self.state.done_tasks

        if nav == NAV_TODAY:
            pending = [t for t in pending if t.due_date and t.due_date <= today]
            done = [t for t in done if t.due_date == today]
        elif nav == NAV_UPCOMING:
            pending = [t for t in pending if t.due_date and t.due_date > today]
            done = []
        elif nav == NAV_INBOX:
            pending = [t for t in pending if not t.due_date]
            done = []
        elif nav == NAV_PROJECTS:
            pending = [t for t in pending if t.project_id in self.state.selected_projects]
            done = [t for t in done if t.project_id in self.state.selected_projects]

        return pending, sorted(done, key=lambda x: x.id or 0, reverse=True)

    def save_time_entry(self, entry: TimeEntry) -> int:
        return db.save_time_entry(entry.to_dict())

    def delete_time_entry(self, entry_id: int) -> None:
        db.delete_time_entry(entry_id)

    def load_time_entries_for_task(self, task_id: int) -> List[TimeEntry]:
        return [TimeEntry.from_dict(d) for d in db.load_time_entries_for_task(task_id)]

    def validate_project_name(self, name: str, editing_id: Optional[str] = None) -> Optional[str]:
        if not name: return "Name required"
        for p in self.state.projects:
            if p.name.lower() == name.lower() and p.id != editing_id:
                return "Project already exists"
        return None

    def generate_project_id(self, name: str) -> str:
        return str(uuid.uuid4())[:8]

    def save_project(self, project: Project) -> None:
        db.save_project(project.to_dict())

    def delete_project(self, project_id: str) -> int:
        self.state.projects = [p for p in self.state.projects if p.id != project_id]
        count = db.delete_project(project_id)
        self.state.tasks = [t for t in self.state.tasks if t.project_id != project_id]
        self.state.done_tasks = [t for t in self.state.done_tasks if t.project_id != project_id]
        return count

    def reset(self) -> None:
        db.clear_all()
        self.state.tasks.clear()
        self.state.done_tasks.clear()
        self.state.projects.clear()

    def save_settings(self) -> None:
        db.set_setting("default_estimated_minutes", self.state.default_estimated_minutes)
        db.set_setting("email_weekly_stats", self.state.email_weekly_stats)

    def task_name_exists(self, name: str, exclude_task: Task) -> bool:
        all_active = [t.title.lower() for t in self.state.tasks if t != exclude_task]
        return name.lower() in all_active

    def assign_project(self, task: Task, project_id: Optional[str]) -> None:
        task.project_id = project_id
        self.persist_task(task)

    def persist_task_order(self) -> None:
        for i, task in enumerate(self.state.tasks):
            task.sort_order = i
            self.persist_task(task)