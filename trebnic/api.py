"""Programmatic API facade for Trebnic.

Composes TaskService and TimeEntryService to provide high-level operations
that cross service boundaries (e.g., completing a task with time logging).

Usage:
    from core import bootstrap
    from api import TrebnicAPI

    svc = await bootstrap(db_path=Path(":memory:"))
    api = TrebnicAPI(svc)

    task = await api.add_task("Write docs")
    await api.complete_task(task, duration_seconds=3600)
"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from config import RecurrenceFrequency
from core import ServiceContainer
from database import db
from events import AppEvent, event_bus
from models.entities import DailyNote, Project, Task, TimeEntry
from services.recurrence import calculate_next_recurrence_from_date


class TrebnicAPI:
    """High-level facade over Trebnic services.

    Each method performs a complete operation: DB persistence, state update,
    and event emission. Callers don't need to coordinate multiple services.
    """

    def __init__(self, services: ServiceContainer) -> None:
        self._svc = services

    @property
    def state(self):
        return self._svc.state

    async def add_task(
        self,
        title: str,
        project_id: Optional[str] = None,
        estimated_seconds: int = 900,
        due_date: Optional[date] = None,
    ) -> Task:
        """Create a new pending task.

        Returns the persisted Task with its database ID set.
        """
        task = await self._svc.task.add_task(
            title=title,
            project_id=project_id,
            estimated_seconds=estimated_seconds,
            due_date=due_date,
        )
        self._svc.state.tasks.append(task)
        event_bus.emit(AppEvent.TASK_CREATED, task)
        return task

    async def complete_task(
        self,
        task: Task,
        duration_seconds: int = 0,
        ended_at: Optional[datetime] = None,
    ) -> Optional[Task]:
        """Complete a task, optionally logging time spent.

        Args:
            task: The task to complete.
            duration_seconds: Time spent in seconds. If >0, a TimeEntry is created.
            ended_at: When the work ended. Defaults to now.

        Returns:
            The next recurring task if one was created, None otherwise.
        """
        if ended_at is None:
            ended_at = datetime.now()

        if duration_seconds > 0:
            entry = TimeEntry(
                task_id=task.id,
                start_time=ended_at - timedelta(seconds=duration_seconds),
                end_time=ended_at,
            )
            await self._svc.time_entry.save_time_entry(entry)
            task.spent_seconds += duration_seconds

        next_task = await self._svc.task.complete_task(task)

        # Move from pending to done in state
        if task in self._svc.state.tasks:
            self._svc.state.tasks.remove(task)
        self._svc.state.done_tasks.append(task)
        event_bus.emit(AppEvent.TASK_COMPLETED, task)

        if next_task:
            self._svc.state.tasks.append(next_task)
            event_bus.emit(AppEvent.TASK_CREATED, next_task)

        return next_task

    async def add_completed_task(
        self,
        title: str,
        duration_seconds: int,
        completed_at: Optional[datetime] = None,
        project_id: Optional[str] = None,
        estimated_seconds: Optional[int] = None,
    ) -> Task:
        """Create a task that was already completed (backdated entry).

        Useful for logging work done outside the app. Creates both the task
        and a backdated TimeEntry in one operation.

        Args:
            title: Task title.
            duration_seconds: How long the work took.
            completed_at: When the work was finished. Defaults to now.
            project_id: Optional project to assign to.
            estimated_seconds: Estimated duration. Defaults to duration_seconds.

        Returns:
            The completed Task.
        """
        if completed_at is None:
            completed_at = datetime.now()
        if estimated_seconds is None:
            estimated_seconds = duration_seconds

        task = await self._svc.task.add_task(
            title=title,
            project_id=project_id,
            estimated_seconds=estimated_seconds,
            due_date=completed_at.date(),
        )
        task.spent_seconds = duration_seconds
        await db.save_task(task.to_dict(is_done=True))

        entry = TimeEntry(
            task_id=task.id,
            start_time=completed_at - timedelta(seconds=duration_seconds),
            end_time=completed_at,
        )
        await self._svc.time_entry.save_time_entry(entry)

        self._svc.state.done_tasks.append(task)
        event_bus.emit(AppEvent.TASK_CREATED, task)
        event_bus.emit(AppEvent.TASK_COMPLETED, task)
        return task

    async def delete_task(self, task: Task) -> None:
        """Delete a task and its associated time entries.

        Removes the task from both database (cascades to time_entries)
        and in-memory state.
        """
        await self._svc.task.delete_task(task)

        if task in self._svc.state.tasks:
            self._svc.state.tasks.remove(task)
        elif task in self._svc.state.done_tasks:
            self._svc.state.done_tasks.remove(task)

        event_bus.emit(AppEvent.TASK_DELETED, task)

    async def log_time(
        self,
        task: Task,
        duration_seconds: int,
        ended_at: Optional[datetime] = None,
    ) -> TimeEntry:
        """Log time spent on a task without completing it.

        Creates a TimeEntry and increments spent_seconds atomically.

        Args:
            task: The task to log time against.
            duration_seconds: Time spent in seconds.
            ended_at: When the work ended. Defaults to now.

        Returns:
            The created TimeEntry.
        """
        if ended_at is None:
            ended_at = datetime.now()

        entry = TimeEntry(
            task_id=task.id,
            start_time=ended_at - timedelta(seconds=duration_seconds),
            end_time=ended_at,
        )
        entry_id = await self._svc.time_entry.save_time_entry(entry)
        entry.id = entry_id

        await db.increment_spent_seconds(task.id, duration_seconds)
        task.spent_seconds += duration_seconds

        return entry

    # -----------------------------------------------------------------------
    # Drafts
    # -----------------------------------------------------------------------

    async def add_draft(
        self,
        title: str,
        project_id: Optional[str] = None,
        estimated_seconds: int = 900,
    ) -> Task:
        """Create a draft task that doesn't appear in the active task list.

        Drafts live in the database only and are not loaded into AppState.
        Use publish_draft() to promote a draft to an active task.

        Returns the persisted draft Task with its database ID set.
        """
        task = Task(
            title=title,
            project_id=project_id,
            estimated_seconds=estimated_seconds,
            spent_seconds=0,
            due_date=None,
            is_draft=True,
        )
        task.id = await db.save_task(task.to_dict())
        return task

    async def get_drafts(self) -> List[Task]:
        """Return all draft tasks."""
        rows = await db.load_tasks_filtered(is_done=False, is_draft=True)
        return [Task.from_dict(r) for r in rows]

    async def publish_draft(self, task: Task) -> Task:
        """Promote a draft to an active task.

        Sets is_draft=False, assigns a due date of today, persists,
        and adds the task to AppState.
        """
        task.is_draft = False
        task.due_date = date.today()
        await self._svc.task.persist_task(task)
        self._svc.state.tasks.append(task)
        event_bus.emit(AppEvent.TASK_CREATED, task)
        return task

    # -----------------------------------------------------------------------
    # Queries
    # -----------------------------------------------------------------------

    @property
    def projects(self) -> List[Project]:
        """All projects in the current state."""
        return self._svc.state.projects

    async def get_tasks(
        self,
        project_id: Optional[str] = None,
        due_before: Optional[date] = None,
        due_after: Optional[date] = None,
    ) -> List[Task]:
        """Return pending tasks, optionally filtered by project and due date.

        Queries the database directly so callers are not coupled to UI
        navigation state (selected_nav / task_filter).

        Args:
            project_id: Only return tasks in this project.
            due_before: Only return tasks due on or before this date.
            due_after: Only return tasks due after this date.
        """
        rows = await db.load_tasks_filtered(
            is_done=False,
            project_ids=[project_id] if project_id else None,
            due_date_lte=due_before,
            due_date_gt=due_after,
        )
        return [Task.from_dict(r) for r in rows]

    async def get_done_tasks(
        self,
        project_id: Optional[str] = None,
        limit: int = 50,
        due_before: Optional[date] = None,
        due_after: Optional[date] = None,
    ) -> List[Task]:
        """Return completed tasks, optionally filtered by project and due date."""
        rows = await db.load_tasks_filtered(
            is_done=True,
            project_ids=[project_id] if project_id else None,
            limit=limit,
            due_date_lte=due_before,
            due_date_gt=due_after,
        )
        return [Task.from_dict(r) for r in rows]

    async def get_time_entries(self, task_id: int) -> List[TimeEntry]:
        """Return all time entries for a task."""
        return await self._svc.time_entry.load_time_entries_for_task(task_id)

    # -----------------------------------------------------------------------
    # Task mutations
    # -----------------------------------------------------------------------

    async def rename_task(self, task: Task, new_title: str) -> None:
        """Rename a task. Rolls back on database failure."""
        await self._svc.task.rename_task(task, new_title)
        event_bus.emit(AppEvent.TASK_RENAMED, task)

    async def postpone_task(self, task: Task) -> date:
        """Postpone a task by one day. Returns the new due date."""
        new_date = await self._svc.task.postpone_task(task)
        event_bus.emit(AppEvent.TASK_POSTPONED, task)
        return new_date

    async def set_due_date(self, task: Task, due_date: Optional[date]) -> None:
        """Set or clear a task's due date."""
        await self._svc.task.set_task_due_date(task, due_date)
        event_bus.emit(AppEvent.TASK_UPDATED, task)

    async def assign_project(self, task: Task, project_id: Optional[str]) -> None:
        """Move a task to a different project (or unassign with None)."""
        await self._svc.task.assign_project(task, project_id)
        event_bus.emit(AppEvent.TASK_UPDATED, task)

    async def create_project(
        self, name: str, icon: str = "📁", color: str = "#2196f3",
    ) -> Project:
        """Create a new project. Returns the created Project."""
        project_id = self._svc.project.generate_project_id(name)
        project = Project(id=project_id, name=name, icon=icon, color=color)
        await self._svc.project.save_project(project)
        self._svc.state.projects.append(project)
        event_bus.emit(AppEvent.SIDEBAR_REBUILD)
        return project

    # -----------------------------------------------------------------------
    # Daily notes
    # -----------------------------------------------------------------------

    async def save_daily_note(self, note_date: date, content: str) -> DailyNote:
        """Save or update a daily note. Returns the saved note."""
        if self._svc.daily_notes is None:
            raise RuntimeError("Daily notes service not available")
        return await self._svc.daily_notes.save_note(note_date, content)

    async def get_recent_notes(self, limit: int = 30) -> list:
        """Get recent daily notes ordered by date descending."""
        if self._svc.daily_notes is None:
            return []
        notes = await self._svc.daily_notes.get_recent_notes(limit)
        return [
            {"date": n.date.isoformat(), "content": n.content}
            for n in notes if n.content.strip()
        ]

    # -----------------------------------------------------------------------
    # Recurrence
    # -----------------------------------------------------------------------

    async def set_recurrence(
        self,
        task: Task,
        frequency: RecurrenceFrequency,
        interval: int = 1,
        weekdays: Optional[List[int]] = None,
        from_completion: bool = False,
        until: Optional[date] = None,
    ) -> None:
        """Configure a recurring schedule on a task.

        Sets recurrence fields, calculates the initial due_date from yesterday
        (so today is eligible), persists, and emits TASK_UPDATED.
        """
        task.recurrent = True
        task.recurrence_frequency = frequency
        task.recurrence_interval = interval
        task.recurrence_weekdays = weekdays or []
        task.recurrence_from_completion = from_completion
        task.recurrence_end_type = "on_date" if until else "never"
        task.recurrence_end_date = until

        base_date = date.today() - timedelta(days=1)
        next_date = calculate_next_recurrence_from_date(task, base_date)
        if next_date:
            task.due_date = next_date

        await self._svc.task.persist_task(task)
        event_bus.emit(AppEvent.TASK_UPDATED, task)

    async def clear_recurrence(self, task: Task) -> None:
        """Remove recurrence from a task."""
        task.recurrent = False
        task.recurrence_interval = 1
        task.recurrence_frequency = RecurrenceFrequency.WEEKS
        task.recurrence_weekdays = []
        task.recurrence_from_completion = False
        task.recurrence_end_type = "never"
        task.recurrence_end_date = None

        await self._svc.task.persist_task(task)
        event_bus.emit(AppEvent.TASK_UPDATED, task)

    # -----------------------------------------------------------------------
    # Export / Import
    # -----------------------------------------------------------------------

    _SAFE_SETTINGS = {
        "default_estimated_minutes", "email_weekly_stats", "language",
        "notifications_enabled", "notify_timer_complete",
        "remind_1h_before", "remind_6h_before", "remind_12h_before",
        "remind_24h_before", "reminder_minutes_before", "notify_overdue",
    }

    async def export_data(self) -> Dict[str, Any]:
        """Export a full-fidelity snapshot of all data.

        The output is suitable for ``import_data()`` and round-trips
        losslessly: export -> import -> export yields identical output.
        """
        projects = [Project.from_dict(p).to_dict() for p in await db.load_projects()]

        all_rows = await db.load_tasks()
        tasks = []
        for r in all_rows:
            t = Task.from_dict(r)
            d = t.to_dict(is_done=bool(r.get("is_done", 0)))
            # Serialize date objects to ISO strings for JSON compatibility
            if isinstance(d.get("due_date"), date):
                d["due_date"] = d["due_date"].isoformat()
            if isinstance(d.get("recurrence_end_date"), date):
                d["recurrence_end_date"] = d["recurrence_end_date"].isoformat()
            tasks.append(d)

        raw_entries = await db.load_time_entries()
        time_entries = [TimeEntry.from_dict(e).to_dict() for e in raw_entries]

        raw_notes = await db.get_all_daily_notes(limit=10000)
        daily_notes = [DailyNote.from_dict(n).to_dict() for n in raw_notes]

        settings: Dict[str, Any] = {}
        for key in self._SAFE_SETTINGS:
            val = await db.get_setting(key)
            if val is not None:
                settings[key] = val

        return {
            "version": 1,
            "exported_at": datetime.now().isoformat(),
            "projects": projects,
            "tasks": tasks,
            "time_entries": time_entries,
            "daily_notes": daily_notes,
            "settings": settings,
        }

    async def import_data(self, data: Dict[str, Any]) -> Dict[str, int]:
        """Validate and import a full snapshot, replacing all existing data.

        Returns a summary dict with counts of imported entities.
        Raises ``ValueError`` on validation failures.
        """
        # --- validation ---
        version = data.get("version")
        if version != 1:
            raise ValueError(f"Unsupported export version: {version}")

        projects = data.get("projects", [])
        tasks = data.get("tasks", [])
        time_entries = data.get("time_entries", [])
        daily_notes = data.get("daily_notes", [])
        settings = data.get("settings", {})

        project_ids = {p["id"] for p in projects}
        task_ids = {t["id"] for t in tasks if t.get("id") is not None}

        for t in tasks:
            if not t.get("title"):
                raise ValueError("Each task must have a title")
            pid = t.get("project_id")
            if pid is not None and pid not in project_ids:
                raise ValueError(f"Task '{t['title']}' references unknown project_id '{pid}'")

        for e in time_entries:
            if e.get("task_id") not in task_ids:
                raise ValueError(f"Time entry references unknown task_id {e.get('task_id')}")

        # --- filter settings to allow-list ---
        safe_settings = {k: v for k, v in settings.items() if k in self._SAFE_SETTINGS}

        # --- import ---
        await db.import_all(
            projects=projects,
            tasks=tasks,
            time_entries=time_entries,
            daily_notes=daily_notes,
            settings=safe_settings,
        )

        # --- reload in-memory state directly (skip seed_default_data) ---
        self._svc.state.projects.clear()
        for p_dict in await db.load_projects():
            self._svc.state.projects.append(Project.from_dict(p_dict))

        self._svc.state.tasks.clear()
        self._svc.state.done_tasks.clear()
        for t_dict in await db.load_tasks():
            if t_dict.get("is_draft"):
                continue
            task = Task.from_dict(t_dict)
            if t_dict.get("is_done"):
                self._svc.state.done_tasks.append(task)
            else:
                self._svc.state.tasks.append(task)

        self._svc.state.default_estimated_minutes = await db.get_setting("default_estimated_minutes", 15)
        self._svc.state.language = await db.get_setting("language", "en")
        self._svc.state.notifications_enabled = await db.get_setting("notifications_enabled", False)
        self._svc.state.notify_timer_complete = await db.get_setting("notify_timer_complete", True)
        self._svc.state.remind_1h_before = await db.get_setting("remind_1h_before", True)
        self._svc.state.remind_6h_before = await db.get_setting("remind_6h_before", True)
        self._svc.state.remind_12h_before = await db.get_setting("remind_12h_before", True)
        self._svc.state.remind_24h_before = await db.get_setting("remind_24h_before", True)
        self._svc.state.reminder_minutes_before = await db.get_setting("reminder_minutes_before", 60)
        self._svc.state.notify_overdue = await db.get_setting("notify_overdue", True)

        event_bus.emit(AppEvent.DATA_RESET)

        return {
            "projects": len(projects),
            "tasks": len(tasks),
            "time_entries": len(time_entries),
            "daily_notes": len(daily_notes),
            "settings": len(safe_settings),
        }
