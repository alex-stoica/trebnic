import uuid
import asyncio
from datetime import date, timedelta
from typing import List, Tuple, Optional, TYPE_CHECKING

import flet as ft

from config import NavItem
from database import db
from models.entities import AppState, Task, Project, TimeEntry
from services.recurrence import calculate_next_recurrence

if TYPE_CHECKING:
    pass


class TaskService:
    def __init__(self, state: AppState, page: Optional[ft.Page] = None) -> None:
        self.state = state
        self._page = page

    def set_page(self, page: ft.Page) -> None:
        """Set the Flet page for async task scheduling."""
        self._page = page

    def _schedule_async(self, coro):
        """Schedule an async coroutine properly based on context.

        - If page is set, use page.run_task() to run on Flet's event loop
        - If no running loop, use asyncio.run()
        - Returns the result for sync callers
        """
        if self._page is not None:
            # In Flet context - schedule on Flet's event loop
            future = asyncio.run_coroutine_threadsafe(
                coro,
                self._page.loop
            )
            return future.result()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already in async context - return the coroutine as a task
            # Caller must await this
            return asyncio.ensure_future(coro)
        else:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(coro)

    @staticmethod
    async def load_state_async() -> AppState:
        """Async version of load_state."""
        state = AppState()

        # Initialize database schema
        await db.init_db()

        # Check if database is empty and seed if needed
        if await db.is_empty():
            await db.seed_default_data()

        for p_dict in await db.load_projects():
            state.projects.append(Project.from_dict(p_dict))

        all_tasks = await db.load_tasks()
        for t_dict in all_tasks:
            task = Task.from_dict(t_dict)
            if t_dict.get("is_done"):
                state.done_tasks.append(task)
            else:
                state.tasks.append(task)

        state.default_estimated_minutes = await db.get_setting("default_estimated_minutes", 15)
        state.email_weekly_stats = await db.get_setting("email_weekly_stats", False)

        return state

    @staticmethod
    def load_state() -> AppState:
        """Sync wrapper for load_state_async - only for initial app load."""
        return asyncio.run(TaskService.load_state_async())

    @staticmethod
    def create_empty_state() -> AppState:
        """Create an empty state without loading from database."""
        return AppState()

    async def add_task_async(self, title: str, project_id: Optional[str] = None, estimated_seconds: int = 900) -> Task:
        task = Task(
            title=title,
            project_id=project_id,
            estimated_seconds=estimated_seconds,
            spent_seconds=0,
            due_date=date.today() if self.state.selected_nav == NavItem.TODAY else None,
            sort_order=len(self.state.tasks)
        )
        # Save to DB first
        task.id = await db.save_task(task.to_dict())
        # Only modify state after DB success
        self.state.tasks.append(task)
        return task

    def add_task(self, title: str, project_id: Optional[str] = None, estimated_seconds: int = 900) -> Task:
        return self._schedule_async(self.add_task_async(title, project_id, estimated_seconds))

    async def persist_task_async(self, task: Task) -> None:
        is_done = task in self.state.done_tasks
        await db.save_task(task.to_dict(is_done=is_done))

    def persist_task(self, task: Task) -> None:
        self._schedule_async(self.persist_task_async(task))

    def rename_task(self, task: Task, new_title: str) -> None:
        """Rename a task."""
        old_title = task.title
        task.title = new_title
        try:
            self.persist_task(task)
        except Exception:
            task.title = old_title  # Rollback on failure
            raise

    def set_task_due_date(self, task: Task, due_date: Optional[date]) -> None:
        """Set or clear a task's due date."""
        old_date = task.due_date
        task.due_date = due_date
        try:
            self.persist_task(task)
        except Exception:
            task.due_date = old_date  # Rollback on failure
            raise

    def set_task_notes(self, task: Task, notes: str) -> None:
        """Update task notes."""
        old_notes = task.notes
        task.notes = notes
        try:
            self.persist_task(task)
        except Exception:
            task.notes = old_notes  # Rollback on failure
            raise

    def update_task_time(self, task: Task, spent_seconds: int) -> None:
        """Update task's spent time."""
        old_seconds = task.spent_seconds
        task.spent_seconds = spent_seconds
        try:
            self.persist_task(task)
        except Exception:
            task.spent_seconds = old_seconds  # Rollback on failure
            raise

    async def complete_task_async(self, task: Task) -> Optional[Task]:
        if task not in self.state.tasks:
            return None

        # Save to DB first
        await db.save_task(task.to_dict(is_done=True))

        # Only modify state after DB success
        self.state.tasks.remove(task)
        self.state.done_tasks.append(task)

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
                # Save new task to DB first
                new_task.id = await db.save_task(new_task.to_dict())
                # Then add to state
                self.state.tasks.append(new_task)
                return new_task
        return None

    def complete_task(self, task: Task) -> Optional[Task]:
        return self._schedule_async(self.complete_task_async(task))

    async def uncomplete_task_async(self, task: Task) -> bool:
        if task not in self.state.done_tasks:
            return False

        # Save to DB first
        await db.save_task(task.to_dict(is_done=False))

        # Only modify state after DB success
        self.state.done_tasks.remove(task)
        self.state.tasks.append(task)
        return True

    def uncomplete_task(self, task: Task) -> bool:
        return self._schedule_async(self.uncomplete_task_async(task))

    async def delete_task_async(self, task: Task) -> None:
        # Delete from DB first
        if task.id:
            await db.delete_task(task.id)

        # Only modify state after DB success
        if task in self.state.tasks:
            self.state.tasks.remove(task)
        elif task in self.state.done_tasks:
            self.state.done_tasks.remove(task)

    def delete_task(self, task: Task) -> None:
        self._schedule_async(self.delete_task_async(task))

    async def duplicate_task_async(self, task: Task) -> Task:
        new_task = Task.from_dict(task.to_dict())
        new_task.id = None
        new_task.title = f"{task.title} (copy)"
        # Save to DB first
        new_task.id = await db.save_task(new_task.to_dict())
        # Then add to state
        self.state.tasks.append(new_task)
        return new_task

    def duplicate_task(self, task: Task) -> Task:
        return self._schedule_async(self.duplicate_task_async(task))

    def postpone_task(self, task: Task) -> date:
        current = task.due_date or date.today()
        old_date = task.due_date
        task.due_date = current + timedelta(days=1)
        try:
            self.persist_task(task)
        except Exception:
            task.due_date = old_date  # Rollback on failure
            raise
        return task.due_date

    def get_filtered_tasks(self) -> Tuple[List[Task], List[Task]]:
        nav = self.state.selected_nav
        today = date.today()

        pending = self.state.tasks
        done = self.state.done_tasks

        if nav == NavItem.TODAY:
            pending = [t for t in pending if t.due_date and t.due_date <= today]
            done = [t for t in done if t.due_date == today]
        elif nav == NavItem.UPCOMING:
            pending = [t for t in pending if t.due_date and t.due_date > today]
            done = []
        elif nav == NavItem.INBOX:
            pending = [t for t in pending if not t.due_date]
            done = []
        elif nav == NavItem.PROJECTS:
            pending = [t for t in pending if t.project_id in self.state.selected_projects]
            done = [t for t in done if t.project_id in self.state.selected_projects]

        return pending, sorted(done, key=lambda x: x.id or 0, reverse=True)

    async def save_time_entry_async(self, entry: TimeEntry) -> int:
        return await db.save_time_entry(entry.to_dict())

    def save_time_entry(self, entry: TimeEntry) -> int:
        return self._schedule_async(self.save_time_entry_async(entry))

    async def delete_time_entry_async(self, entry_id: int) -> None:
        await db.delete_time_entry(entry_id)

    def delete_time_entry(self, entry_id: int) -> None:
        self._schedule_async(self.delete_time_entry_async(entry_id))

    async def update_time_entry_async(self, entry: TimeEntry) -> int:
        """Update an existing time entry."""
        return await db.save_time_entry(entry.to_dict())

    def update_time_entry(self, entry: TimeEntry) -> int:
        """Update an existing time entry."""
        return self._schedule_async(self.update_time_entry_async(entry))

    async def load_time_entries_for_task_async(self, task_id: int) -> List[TimeEntry]:
        return [TimeEntry.from_dict(d) for d in await db.load_time_entries_for_task(task_id)]

    def load_time_entries_for_task(self, task_id: int) -> List[TimeEntry]:
        return self._schedule_async(self.load_time_entries_for_task_async(task_id))

    async def recalculate_task_time_from_entries_async(self, task: Task) -> None:
        """Recalculate task spent_seconds from its time entries."""
        if task.id is None:
            return
        entries = await self.load_time_entries_for_task_async(task.id)
        total = sum(e.duration_seconds for e in entries if e.end_time)
        task.spent_seconds = total
        await self.persist_task_async(task)

    def recalculate_task_time_from_entries(self, task: Task) -> None:
        """Recalculate task spent_seconds from its time entries."""
        self._schedule_async(self.recalculate_task_time_from_entries_async(task))

    def validate_project_name(self, name: str, editing_id: Optional[str] = None) -> Optional[str]:
        if not name:
            return "Name required"
        for p in self.state.projects:
            if p.name.lower() == name.lower() and p.id != editing_id:
                return "Project already exists"
        return None

    def generate_project_id(self, name: str) -> str:
        return str(uuid.uuid4())[:8]

    async def save_project_async(self, project: Project) -> None:
        await db.save_project(project.to_dict())

    def save_project(self, project: Project) -> None:
        self._schedule_async(self.save_project_async(project))

    async def delete_project_async(self, project_id: str) -> int:
        # Delete from DB first
        count = await db.delete_project(project_id)

        # Only modify state after DB success
        self.state.projects = [p for p in self.state.projects if p.id != project_id]
        self.state.tasks = [t for t in self.state.tasks if t.project_id != project_id]
        self.state.done_tasks = [t for t in self.state.done_tasks if t.project_id != project_id]
        return count

    def delete_project(self, project_id: str) -> int:
        return self._schedule_async(self.delete_project_async(project_id))

    async def reset_async(self) -> None:
        await db.clear_all()
        await db.seed_default_data()
        self.state.tasks.clear()
        self.state.done_tasks.clear()
        self.state.projects.clear()
        for p_dict in await db.load_projects():
            self.state.projects.append(Project.from_dict(p_dict))
        for t_dict in await db.load_tasks():
            task = Task.from_dict(t_dict)
            if t_dict.get("is_done"):
                self.state.done_tasks.append(task)
            else:
                self.state.tasks.append(task)

    def reset(self) -> None:
        self._schedule_async(self.reset_async())

    async def save_settings_async(self) -> None:
        await db.set_setting("default_estimated_minutes", self.state.default_estimated_minutes)
        await db.set_setting("email_weekly_stats", self.state.email_weekly_stats)

    def save_settings(self) -> None:
        self._schedule_async(self.save_settings_async())

    def task_name_exists(self, name: str, exclude_task: Task) -> bool:
        all_active = [t.title.lower() for t in self.state.tasks if t != exclude_task]
        return name.lower() in all_active

    def assign_project(self, task: Task, project_id: Optional[str]) -> None:
        old_project_id = task.project_id
        task.project_id = project_id
        try:
            self.persist_task(task)
        except Exception:
            task.project_id = old_project_id  # Rollback on failure
            raise

    async def persist_task_order_async(self) -> None:
        for i, task in enumerate(self.state.tasks):
            task.sort_order = i
            await self.persist_task_async(task)

    def persist_task_order(self) -> None:
        self._schedule_async(self.persist_task_order_async())
