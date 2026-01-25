import uuid
import asyncio
from datetime import date, timedelta
from typing import List, Tuple, Optional, TYPE_CHECKING

import flet as ft

from config import NavItem
from database import db
from models.entities import AppState, Task, Project, TimeEntry
from services.recurrence import calculate_next_recurrence, calculate_next_recurrence_from_date

if TYPE_CHECKING:
    pass


class TaskService:
    def __init__(self, state: AppState, page: Optional[ft.Page] = None) -> None:
        self.state = state
        self._page = page

    def set_page(self, page: ft.Page) -> None:
        """Set the Flet page for async task scheduling."""
        self._page = page

    def _schedule_async(self, coro, need_result: bool = True):
        """Schedule an async coroutine on the page's event loop.

        This is a compatibility bridge for sync code that needs to call async methods.
        For new code, prefer using async handlers with page.run_task() or direct await.

        Args:
            coro: The coroutine to schedule
            need_result: If True, block and return result. If False, fire-and-forget.

        Returns:
            The result of the coroutine when need_result=True, None otherwise.
        """
        if self._page is not None:
            # Schedule on page's event loop - the standard path for UI operations
            future = asyncio.run_coroutine_threadsafe(coro, self._page.loop)
            if not need_result:
                return None
            return future.result(timeout=30.0)

        # No page available - use asyncio.run() for standalone context (e.g., initial load)
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                coro.close()
                raise RuntimeError("Cannot schedule: already in async context without page reference")
        except RuntimeError:
            pass  # No running loop is fine
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

        # Check for incomplete time entry (timer was running when app closed)
        incomplete_entry = await db.load_incomplete_time_entry()
        if incomplete_entry:
            state.recovered_timer_entry = TimeEntry.from_dict(incomplete_entry)

        return state

    @staticmethod
    def load_state() -> AppState:
        """Sync wrapper for load_state_async - only for initial app load."""
        return asyncio.run(TaskService.load_state_async())

    @staticmethod
    def create_empty_state() -> AppState:
        """Create an empty state without loading from database."""
        return AppState()

    def reload_state(self) -> None:
        """Reload state from database.

        This is useful after encryption unlock when decrypted data becomes available.
        Reloads all tasks and projects with decryption enabled.
        """
        new_state = TaskService.load_state()

        # Update the existing state object in place to preserve references
        self.state.tasks.clear()
        self.state.tasks.extend(new_state.tasks)
        self.state.done_tasks.clear()
        self.state.done_tasks.extend(new_state.done_tasks)
        self.state.projects.clear()
        self.state.projects.extend(new_state.projects)

    async def add_task_async(self, title: str, project_id: Optional[str] = None, estimated_seconds: int = 900) -> Task:
        # Determine default due date based on current view
        if self.state.selected_nav == NavItem.TODAY:
            default_due_date = date.today()
        elif self.state.selected_nav == NavItem.UPCOMING:
            default_due_date = date.today() + timedelta(days=7)
        else:
            default_due_date = None

        # Get current max sort_order from DB for accurate ordering
        all_tasks = await db.load_tasks_filtered(is_done=False, limit=1)
        max_order = max((t.get("sort_order", 0) for t in all_tasks), default=-1) if all_tasks else -1

        task = Task(
            title=title,
            project_id=project_id,
            estimated_seconds=estimated_seconds,
            spent_seconds=0,
            due_date=default_due_date,
            sort_order=max_order + 1
        )
        # Save to DB - this is the single source of truth
        task.id = await db.save_task(task.to_dict())
        # Note: UI should call refresh() after this to update from DB
        return task

    def add_task(self, title: str, project_id: Optional[str] = None, estimated_seconds: int = 900) -> Task:
        return self._schedule_async(self.add_task_async(title, project_id, estimated_seconds))

    async def persist_task_async(self, task: Task) -> None:
        is_done = task in self.state.done_tasks
        await db.save_task(task.to_dict(is_done=is_done))

    def persist_task(self, task: Task, wait_for_result: bool = False) -> None:
        """Persist task to database.

        Args:
            task: The task to persist
            wait_for_result: If True, wait for DB confirmation (enables rollback).
                           If False, fire-and-forget (no rollback possible).
        """
        self._schedule_async(self.persist_task_async(task), need_result=wait_for_result)

    def rename_task(self, task: Task, new_title: str) -> None:
        """Rename a task with rollback on failure."""
        old_title = task.title
        task.title = new_title
        try:
            self.persist_task(task, wait_for_result=True)
        except Exception:
            task.title = old_title
            raise

    def set_task_due_date(self, task: Task, due_date: Optional[date]) -> None:
        """Set or clear a task's due date with rollback on failure."""
        old_date = task.due_date
        task.due_date = due_date
        try:
            self.persist_task(task, wait_for_result=True)
        except Exception:
            task.due_date = old_date
            raise

    def set_task_notes(self, task: Task, notes: str) -> None:
        """Update task notes with rollback on failure."""
        old_notes = task.notes
        task.notes = notes
        try:
            self.persist_task(task, wait_for_result=True)
        except Exception:
            task.notes = old_notes
            raise

    def update_task_time(self, task: Task, spent_seconds: int) -> None:
        """Update task's spent time with rollback on failure."""
        old_seconds = task.spent_seconds
        task.spent_seconds = spent_seconds
        try:
            self.persist_task(task, wait_for_result=True)
        except Exception:
            task.spent_seconds = old_seconds
            raise

    async def complete_task_async(self, task: Task) -> Optional[Task]:
        """Complete a task and optionally create next recurrence.

        DB is the single source of truth. In-memory state is updated for
        backward compatibility but UI should call refresh() after this.
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
        new_task = await self._create_next_recurrence_async(completed_task)
        if new_task:
            new_task.id = await db.save_task(new_task.to_dict())
            return new_task
        return None

    async def _create_next_recurrence_async(self, task: Task) -> Optional[Task]:
        """Create the next occurrence of a recurring task.

        Returns None if task is not recurring, recurrence has ended, or
        a task with the same title and due date already exists in DB.
        """
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

    async def _advance_overdue_recurring_tasks(
        self, tasks: List[Task], today: date
    ) -> List[Task]:
        """Auto-advance recurring tasks whose due_date has passed or isn't a scheduled day.

        For recurring tasks with due_date < today, update their due_date
        to the next valid occurrence. This ensures recurring tasks only
        appear on their scheduled days, not every day after their original date.

        Also handles tasks where due_date == today but today isn't a scheduled weekday.

        Returns the filtered list (excluding tasks that were advanced to a future date).
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

            # Check if today is a valid day for recurring tasks with weekday constraints
            if task.due_date == today and task.recurrence_weekdays:
                if today.weekday() not in task.recurrence_weekdays:
                    # Today is not a scheduled day - advance to next occurrence
                    next_date = calculate_next_recurrence_from_date(task, today)
                    if next_date and next_date != task.due_date:
                        task.due_date = next_date
                        await db.save_task(task.to_dict(is_done=False))
                    # Don't include in today's list (it's now a future task)
                    continue
                # Today is a valid weekday - include it
                result.append(task)
                continue

            # Calculate next occurrence from yesterday to include today if valid
            next_date = calculate_next_recurrence_from_date(task, today - timedelta(days=1))

            if next_date and next_date != task.due_date:
                # Update the task's due_date
                task.due_date = next_date
                await db.save_task(task.to_dict(is_done=False))

                # Only include if next date is today (otherwise it's a future task)
                if next_date == today:
                    result.append(task)
            else:
                # No next occurrence or same date - keep as is
                result.append(task)

        return result

    def complete_task(self, task: Task) -> Optional[Task]:
        return self._schedule_async(self.complete_task_async(task))

    async def uncomplete_task_async(self, task: Task) -> bool:
        """Mark a completed task as not done.

        DB is the single source of truth. UI should call refresh() after this.
        """
        # Load fresh task from DB to avoid stale data issues
        all_done = await db.load_tasks_filtered(is_done=True)
        db_task_dict = next((t for t in all_done if t.get("id") == task.id), None)
        if db_task_dict is None:
            return False

        # Save uncompleted status to DB - single source of truth
        db_task_dict["is_done"] = 0
        await db.save_task(db_task_dict)
        return True

    def uncomplete_task(self, task: Task) -> bool:
        return self._schedule_async(self.uncomplete_task_async(task))

    async def delete_task_async(self, task: Task) -> None:
        """Delete a task from the database.

        DB is the single source of truth. UI should call refresh() after this.
        """
        if task.id:
            await db.delete_task(task.id)
        # Note: In-memory state will be updated when UI calls refresh()

    def delete_task(self, task: Task) -> None:
        self._schedule_async(self.delete_task_async(task), need_result=False)

    async def delete_all_recurring_tasks_async(self, task: Task) -> int:
        """Delete all recurring tasks with the same title as the given task.

        This removes the entire recurrence series (pending and completed instances).

        Args:
            task: A recurring task whose series should be deleted

        Returns:
            Number of tasks deleted
        """
        if not task.recurrent:
            # Not a recurring task, just delete this one
            await self.delete_task_async(task)
            return 1
        return await db.delete_recurring_tasks_by_title(task.title)

    def delete_all_recurring_tasks(self, task: Task) -> int:
        return self._schedule_async(self.delete_all_recurring_tasks_async(task))

    async def duplicate_task_async(self, task: Task) -> Task:
        """Duplicate a task.

        DB is the single source of truth. UI should call refresh() after this.
        """
        new_task = Task.from_dict(task.to_dict())
        new_task.id = None
        new_task.title = f"{task.title} (copy)"
        # Save to DB - single source of truth
        new_task.id = await db.save_task(new_task.to_dict())
        return new_task

    def duplicate_task(self, task: Task) -> Task:
        return self._schedule_async(self.duplicate_task_async(task))

    def postpone_task(self, task: Task) -> date:
        """Postpone task by one day with rollback on failure."""
        current = task.due_date or date.today()
        old_date = task.due_date
        task.due_date = current + timedelta(days=1)
        try:
            self.persist_task(task, wait_for_result=True)
        except Exception:
            task.due_date = old_date
            raise
        return task.due_date

    async def get_filtered_tasks_async(self, done_limit: int = 50) -> Tuple[List[Task], List[Task]]:
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

        # Auto-advance recurring tasks whose due_date has passed
        # This ensures recurring tasks only appear on their scheduled days
        if nav == NavItem.TODAY:
            pending = await self._advance_overdue_recurring_tasks(pending, today)

        # Update in-memory state for pending tasks (these should be kept in sync)
        # Note: We don't update done_tasks here as we intentionally limit them
        return pending, sorted(done, key=lambda x: x.id or 0, reverse=True)

    def get_filtered_tasks(self, done_limit: int = 50) -> Tuple[List[Task], List[Task]]:
        """Get filtered tasks. Uses SQL filtering when page is available.

        Args:
            done_limit: Maximum number of done tasks to return.

        Returns:
            Tuple of (pending_tasks, done_tasks) filtered by current navigation.
        """
        # If page is available, use efficient async database queries
        if self._page is not None:
            return self._schedule_async(self.get_filtered_tasks_async(done_limit))

        # Fallback to in-memory filtering (only for initial load or tests)
        nav = self.state.selected_nav
        today = date.today()

        pending = list(self.state.tasks)
        done = self.state.done_tasks

        # Apply nav-based date filter
        if nav == NavItem.TODAY:
            # For recurring tasks, only show if today matches their schedule
            filtered_pending = []
            for t in pending:
                if not t.due_date:
                    continue
                if t.due_date > today:
                    continue
                # For recurring tasks with past due_date, advance to next occurrence
                if t.recurrent and t.due_date < today:
                    next_date = calculate_next_recurrence_from_date(t, today - timedelta(days=1))
                    if next_date:
                        t.due_date = next_date
                        if next_date == today:
                            filtered_pending.append(t)
                    # If no next date, task recurrence ended - don't show
                else:
                    filtered_pending.append(t)
            pending = filtered_pending
            done = [t for t in done if t.due_date == today]
        elif nav == NavItem.UPCOMING:
            pending = [t for t in pending if t.due_date and t.due_date > today]
            done = [t for t in done if t.due_date and t.due_date > today]
        elif nav == NavItem.INBOX:
            pending = [t for t in pending if not t.due_date]
            done = [t for t in done if not t.due_date]

        # Apply project filter if any projects selected (combines with nav filter)
        if self.state.selected_projects:
            pending = [t for t in pending if t.project_id in self.state.selected_projects]
            done = [t for t in done if t.project_id in self.state.selected_projects]

        # Apply limit to done tasks even for in-memory filtering
        done = sorted(done, key=lambda x: x.id or 0, reverse=True)[:done_limit]

        return pending, done

    async def save_time_entry_async(self, entry: TimeEntry) -> int:
        return await db.save_time_entry(entry.to_dict())

    def save_time_entry(self, entry: TimeEntry) -> int:
        return self._schedule_async(self.save_time_entry_async(entry))

    async def delete_time_entry_async(self, entry_id: int) -> None:
        await db.delete_time_entry(entry_id)

    def delete_time_entry(self, entry_id: int) -> None:
        self._schedule_async(self.delete_time_entry_async(entry_id), need_result=True)

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
        self._schedule_async(self.recalculate_task_time_from_entries_async(task), need_result=False)

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
        self._schedule_async(self.save_project_async(project), need_result=False)

    async def delete_project_async(self, project_id: str) -> int:
        """Delete a project and all its tasks.

        DB is the single source of truth. UI should call refresh() after this.
        Returns the count of tasks that were deleted.
        """
        # Delete from DB - single source of truth
        count = await db.delete_project(project_id)
        # Update projects list (needed for sidebar rebuild)
        self.state.projects = [p for p in self.state.projects if p.id != project_id]
        return count

    def delete_project(self, project_id: str) -> int:
        return self._schedule_async(self.delete_project_async(project_id))

    async def reset_async(self) -> None:
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

    def reset(self) -> None:
        self._schedule_async(self.reset_async(), need_result=True)

    async def save_settings_async(self) -> None:
        await db.set_setting("default_estimated_minutes", self.state.default_estimated_minutes)
        await db.set_setting("email_weekly_stats", self.state.email_weekly_stats)

    def save_settings(self) -> None:
        self._schedule_async(self.save_settings_async(), need_result=False)

    def task_name_exists(self, name: str, exclude_task: Task) -> bool:
        all_active = [t.title.lower() for t in self.state.tasks if t != exclude_task]
        return name.lower() in all_active

    def assign_project(self, task: Task, project_id: Optional[str]) -> None:
        """Assign task to a project with rollback on failure."""
        old_project_id = task.project_id
        task.project_id = project_id
        try:
            self.persist_task(task, wait_for_result=True)
        except Exception:
            task.project_id = old_project_id
            raise

    async def persist_task_order_async(self) -> None:
        """Persist sort order for all tasks in state using batch update."""
        task_orders = [(task.id, i) for i, task in enumerate(self.state.tasks) if task.id is not None]
        if task_orders:
            await db.update_task_sort_orders(task_orders)

    def persist_task_order(self) -> None:
        self._schedule_async(self.persist_task_order_async(), need_result=False)

    async def persist_reordered_tasks_async(self, tasks: List[Task]) -> None:
        """Persist sort_order for a list of tasks using efficient batch update.

        Uses a single SQL transaction instead of N separate UPDATE statements.
        """
        task_orders = [(task.id, task.sort_order) for task in tasks if task.id is not None]
        if task_orders:
            await db.update_task_sort_orders(task_orders)

    def persist_reordered_tasks(self, tasks: List[Task]) -> None:
        """Persist reordered tasks. Use this instead of persist_task_order when
        working with fresh DB objects from get_filtered_tasks().
        """
        self._schedule_async(self.persist_reordered_tasks_async(tasks), need_result=True)
