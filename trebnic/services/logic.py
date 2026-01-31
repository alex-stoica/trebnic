import asyncio
import logging
from datetime import date, timedelta
from typing import List, Tuple, Optional

import flet as ft

from config import NavItem
from database import db
from i18n import set_language
from models.entities import AppState, Task, Project, TimeEntry
from registry import registry, Services
from services.recurrence import calculate_next_recurrence, calculate_next_recurrence_from_date

logger = logging.getLogger(__name__)


class TaskService:
    """Service for task operations.

    This service handles only task CRUD operations. Other domain operations
    are handled by their respective services:
    - ProjectService: project CRUD
    - TimeEntryService: time entry CRUD
    - SettingsService: app settings

    All data operations are async. Use page.run_task() or await for async calls.
    """

    def __init__(self, state: AppState, page: Optional[ft.Page] = None) -> None:
        self.state = state
        self._page = page

    def set_page(self, page: ft.Page) -> None:
        """Set the Flet page for async task scheduling."""
        self._page = page

    @staticmethod
    async def load_state_async() -> AppState:
        """Load application state from database."""
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
        state.language = await db.get_setting("language", "en")
        set_language(state.language)

        # Check for incomplete time entry (timer was running when app closed)
        incomplete_entry = await db.load_incomplete_time_entry()
        if incomplete_entry:
            state.recovered_timer_entry = TimeEntry.from_dict(incomplete_entry)

        return state

    @staticmethod
    def load_state() -> AppState:
        """Sync load for initial app startup."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in an async context - create task and run
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, TaskService.load_state_async())
                return future.result()
        else:
            return asyncio.run(TaskService.load_state_async())

    @staticmethod
    def create_empty_state() -> AppState:
        """Create an empty state without loading from database."""
        return AppState()

    async def reload_state_async(self) -> None:
        """Reload state from database asynchronously.

        This is useful after encryption unlock when decrypted data becomes available.
        Reloads all tasks and projects with decryption enabled.

        Emits REFRESH_UI event to notify UI components to rebuild with fresh data.
        """
        new_state = await TaskService.load_state_async()

        # Update the existing state object in place to preserve references
        self.state.tasks.clear()
        self.state.tasks.extend(new_state.tasks)
        self.state.done_tasks.clear()
        self.state.done_tasks.extend(new_state.done_tasks)
        self.state.projects.clear()
        self.state.projects.extend(new_state.projects)

        # Notify UI to rebuild via registry
        from events import AppEvent  # AppEvent enum is safe to import
        event_bus = registry.get(Services.EVENT_BUS)
        if event_bus:
            event_bus.emit(AppEvent.REFRESH_UI)

    def reload_state(self) -> None:
        """Reload state from database (sync wrapper).

        This is useful after encryption unlock when decrypted data becomes available.
        Reloads all tasks and projects with decryption enabled.

        Prefer reload_state_async() when in an async context to avoid event loop conflicts.
        """
        if self._page is not None:
            # Use the page's event loop - safer than asyncio.run()
            future = asyncio.run_coroutine_threadsafe(
                self.reload_state_async(),
                self._page.loop
            )
            future.result(timeout=30.0)
        else:
            # Fallback for testing or early init
            new_state = TaskService.load_state()

            self.state.tasks.clear()
            self.state.tasks.extend(new_state.tasks)
            self.state.done_tasks.clear()
            self.state.done_tasks.extend(new_state.done_tasks)
            self.state.projects.clear()
            self.state.projects.extend(new_state.projects)

            from events import AppEvent  # AppEvent enum is safe to import
            event_bus = registry.get(Services.EVENT_BUS)
            if event_bus:
                event_bus.emit(AppEvent.REFRESH_UI)

    async def add_task(
        self,
        title: str,
        project_id: Optional[str] = None,
        estimated_seconds: int = 900,
        due_date: Optional[date] = None,
    ) -> Task:
        """Add a new task.

        Args:
            title: Task title.
            project_id: Optional project ID to assign the task to.
            estimated_seconds: Estimated duration in seconds (default 15 min).
            due_date: Optional due date. Caller should determine appropriate date
                      based on context (e.g., UI navigation state).

        UI should call refresh() after this.
        """
        # Get current max sort_order from DB for accurate ordering
        all_tasks = await db.load_tasks_filtered(is_done=False, limit=1)
        max_order = max((t.get("sort_order", 0) for t in all_tasks), default=-1) if all_tasks else -1

        task = Task(
            title=title,
            project_id=project_id,
            estimated_seconds=estimated_seconds,
            spent_seconds=0,
            due_date=due_date,
            sort_order=max_order + 1
        )
        task.id = await db.save_task(task.to_dict())
        return task

    async def persist_task(self, task: Task) -> None:
        """Persist task to database."""
        is_done = task in self.state.done_tasks
        await db.save_task(task.to_dict(is_done=is_done))

    async def rename_task(self, task: Task, new_title: str) -> None:
        """Rename a task with rollback on failure."""
        old_title = task.title
        task.title = new_title
        try:
            await self.persist_task(task)
        except Exception:
            task.title = old_title
            raise

    async def set_task_due_date(self, task: Task, due_date: Optional[date]) -> None:
        """Set or clear a task's due date with rollback on failure."""
        old_date = task.due_date
        task.due_date = due_date
        try:
            await self.persist_task(task)
        except Exception:
            task.due_date = old_date
            raise

    async def set_task_notes(self, task: Task, notes: str) -> None:
        """Update task notes with rollback on failure."""
        old_notes = task.notes
        task.notes = notes
        try:
            await self.persist_task(task)
        except Exception:
            task.notes = old_notes
            raise

    async def update_task_time(self, task: Task, spent_seconds: int) -> None:
        """Update task's spent time with rollback on failure."""
        old_seconds = task.spent_seconds
        task.spent_seconds = spent_seconds
        try:
            await self.persist_task(task)
        except Exception:
            task.spent_seconds = old_seconds
            raise

    async def complete_task(self, task: Task) -> Optional[Task]:
        """Complete a task and optionally create next recurrence.

        DB is the single source of truth. UI should call refresh() after this.
        Returns the next recurring task if one was created, None otherwise.
        """
        # Load fresh task from DB to avoid stale data issues
        all_tasks = await db.load_tasks_filtered(is_done=False)
        db_task_dict = next((t for t in all_tasks if t.get("id") == task.id), None)
        if db_task_dict is None:
            return None

        # Apply any updates from the passed task (e.g., spent_seconds from timer)
        db_task_dict["spent_seconds"] = task.spent_seconds

        # Save completed status to DB - single source of truth
        db_task_dict["is_done"] = 1
        await db.save_task(db_task_dict)

        # Handle recurrence - create next occurrence if applicable
        completed_task = Task.from_dict(db_task_dict)
        new_task = await self._create_next_recurrence(completed_task)
        if new_task:
            new_task.id = await db.save_task(new_task.to_dict())
            return new_task
        return None

    async def _create_next_recurrence(self, task: Task) -> Optional[Task]:
        """Create the next occurrence of a recurring task (internal helper)."""
        if not task.recurrent:
            return None

        if task.recurrence_from_completion:
            next_date = calculate_next_recurrence_from_date(task, date.today())
        else:
            next_date = calculate_next_recurrence(task)

        if not next_date:
            return None

        # Check DB for duplicate - query tasks with same due date
        existing_tasks = await db.load_tasks_filtered(is_done=False, due_date_eq=next_date)
        for existing in existing_tasks:
            if existing.get("title") == task.title:
                return None

        return task.create_next_occurrence(next_date)

    def _filter_recurring_tasks_for_today(self, tasks: List[Task], today: date) -> List[Task]:
        """Filter recurring tasks to show only those that should appear today.

        This is a pure filter - it never modifies task due_dates. Recurring tasks
        with overdue due_dates will still appear in the Today view if today matches
        their recurrence pattern (e.g., "every Monday" should show on Mondays).

        Non-recurring tasks are included as-is. Recurring tasks are included only if:
        - due_date == today, OR
        - due_date < today AND today is a valid day per the recurrence pattern

        Returns the filtered list.
        """
        result = []
        for task in tasks:
            # Non-recurring tasks or tasks without due_date pass through unchanged
            if not task.recurrent or not task.due_date:
                result.append(task)
                continue

            # Future tasks pass through unchanged
            if task.due_date > today:
                result.append(task)
                continue

            # Task is due today or overdue - check if today is a valid recurrence day
            if task.recurrence_weekdays:
                # Has weekday constraints - only include if today matches
                if today.weekday() in task.recurrence_weekdays:
                    result.append(task)
                # Otherwise skip (today is not a scheduled day)
            else:
                # No weekday constraints - include it (daily/weekly/monthly without specific days)
                result.append(task)

        return result

    async def uncomplete_task(self, task: Task) -> bool:
        """Mark a completed task as not done. UI should call refresh() after this."""
        all_done = await db.load_tasks_filtered(is_done=True)
        db_task_dict = next((t for t in all_done if t.get("id") == task.id), None)
        if db_task_dict is None:
            return False

        db_task_dict["is_done"] = 0
        await db.save_task(db_task_dict)
        return True

    async def delete_task(self, task: Task) -> None:
        """Delete a task from the database. UI should call refresh() after this."""
        if task.id:
            await db.delete_task(task.id)

    async def delete_all_recurring_tasks(self, task: Task) -> int:
        """Delete all recurring tasks with the same title.

        Returns number of tasks deleted.
        """
        if not task.recurrent:
            await self.delete_task(task)
            return 1
        return await db.delete_recurring_tasks_by_title(task.title)

    async def duplicate_task(self, task: Task) -> Task:
        """Duplicate a task. UI should call refresh() after this."""
        new_task = Task.from_dict(task.to_dict())
        new_task.id = None
        new_task.title = f"{task.title} (copy)"
        new_task.id = await db.save_task(new_task.to_dict())
        return new_task

    async def postpone_task(self, task: Task) -> date:
        """Postpone task by one day with rollback on failure."""
        current = task.due_date or date.today()
        old_date = task.due_date
        task.due_date = current + timedelta(days=1)
        try:
            await self.persist_task(task)
        except Exception:
            task.due_date = old_date
            raise
        return task.due_date

    async def refresh_state_tasks(self) -> None:
        """Refresh state.tasks and state.done_tasks from database.

        This ensures state reflects the current database contents,
        which is needed for views like calendar that read from state directly.
        """
        all_tasks = await db.load_tasks()
        self.state.tasks.clear()
        self.state.done_tasks.clear()
        for t_dict in all_tasks:
            task = Task.from_dict(t_dict)
            if t_dict.get("is_done"):
                self.state.done_tasks.append(task)
            else:
                self.state.tasks.append(task)

    async def get_filtered_tasks(self, done_limit: int = 50) -> Tuple[List[Task], List[Task]]:
        """Get filtered tasks using efficient SQL queries.

        Args:
            done_limit: Maximum number of done tasks to return (prevents loading
                       thousands of historical tasks into memory).

        Returns:
            Tuple of (pending_tasks, done_tasks) filtered by current navigation.
        """
        nav = self.state.selected_nav
        today = date.today()

        # Build filter parameters based on navigation
        pending_kwargs: dict = {"is_done": False}
        done_kwargs: dict = {"is_done": True, "limit": done_limit}

        # Apply nav-based date filter
        if nav == NavItem.TODAY:
            pending_kwargs["due_date_lte"] = today
            done_kwargs["due_date_eq"] = today
        elif nav == NavItem.UPCOMING:
            pending_kwargs["due_date_gt"] = today
            done_kwargs["due_date_gt"] = today
        elif nav == NavItem.INBOX:
            pending_kwargs["due_date_is_null"] = True
            done_kwargs["due_date_is_null"] = True

        # Apply project filter if any projects selected (combines with nav filter)
        if self.state.selected_projects:
            project_ids = list(self.state.selected_projects)
            pending_kwargs["project_ids"] = project_ids
            done_kwargs["project_ids"] = project_ids

        # Query database with filters
        pending_dicts = await db.load_tasks_filtered(**pending_kwargs)
        done_dicts = await db.load_tasks_filtered(**done_kwargs)

        pending = [Task.from_dict(d) for d in pending_dicts]
        done = [Task.from_dict(d) for d in done_dicts]

        # Filter recurring tasks to only show those scheduled for today
        # This ensures recurring tasks only appear on their scheduled days
        if nav == NavItem.TODAY:
            pending = self._filter_recurring_tasks_for_today(pending, today)

        return pending, sorted(done, key=lambda x: x.id or 0, reverse=True)

    async def reset(self) -> None:
        """Reset database to default state."""
        await db.clear_all()
        await db.seed_default_data()
        self.state.tasks.clear()
        self.state.done_tasks.clear()
        self.state.projects.clear()
        self.state.viewing_task_id = None
        for p_dict in await db.load_projects():
            self.state.projects.append(Project.from_dict(p_dict))
        for t_dict in await db.load_tasks():
            task = Task.from_dict(t_dict)
            if t_dict.get("is_done"):
                self.state.done_tasks.append(task)
            else:
                self.state.tasks.append(task)

    def task_name_exists(self, name: str, exclude_task: Task) -> bool:
        """Check if a task name already exists (sync, in-memory check)."""
        all_active = [t.title.lower() for t in self.state.tasks if t != exclude_task]
        return name.lower() in all_active

    async def assign_project(self, task: Task, project_id: Optional[str]) -> None:
        """Assign task to a project with rollback on failure."""
        old_project_id = task.project_id
        task.project_id = project_id
        try:
            await self.persist_task(task)
        except Exception:
            task.project_id = old_project_id
            raise

    async def persist_task_order(self) -> None:
        """Persist sort order for all tasks in state using batch update."""
        task_orders = [(task.id, i) for i, task in enumerate(self.state.tasks) if task.id is not None]
        if task_orders:
            await db.update_task_sort_orders(task_orders)

    async def persist_reordered_tasks(self, tasks: List[Task]) -> None:
        """Persist sort_order for a list of tasks using efficient batch update."""
        task_orders = [(task.id, task.sort_order) for task in tasks if task.id is not None]
        if task_orders:
            await db.update_task_sort_orders(task_orders)
