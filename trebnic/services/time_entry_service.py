from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from database import db
from models.entities import TimeEntry


class TimeEntryService:
    """Service for time entry operations.

    Handles time entry CRUD operations with database persistence.
    All data operations are async.

    Entries are canonical: task.spent_seconds is their cached sum. Mutating an
    entry must go through the *_with_recompute helpers, which return the affected
    {task_id: new_spent} so callers can sync in-memory tasks (TaskService.apply_spent).
    The plain save/delete below are for the live timer's running row only (end_time
    NULL, excluded from the sum) where no recompute is needed.
    """

    async def save_time_entry(self, entry: TimeEntry) -> int:
        """Save a running/heartbeat entry (no recompute). Returns the entry ID."""
        return await db.save_time_entry(entry.to_dict())

    async def delete_time_entry(self, entry_id: int) -> None:
        """Delete a time entry from the database (no recompute)."""
        await db.delete_time_entry(entry_id)

    @staticmethod
    def _validate_completed(task_id: int, start_time: datetime, end_time: datetime) -> None:
        """Reject invalid completed intervals before they ever hit the DB.

        This is the single chokepoint for manual UI, headless API and the AI tools,
        so future-dated work is blocked here (a small grace covers the timer's
        finalize where end == 'now' a moment earlier).
        """
        if task_id is None:
            raise ValueError("time entry requires a task_id")
        if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
            raise ValueError("time entry start/end must be datetimes")
        if end_time <= start_time:
            raise ValueError("time entry end must be after start")
        if end_time > datetime.now() + timedelta(minutes=1):
            raise ValueError("time entry cannot be in the future")

    async def save_entry_with_recompute(self, entry: TimeEntry) -> Tuple[int, Dict[int, int]]:
        """Upsert a completed entry and recompute affected tasks' spent_seconds.

        Returns (entry_id, {task_id: new_spent}). Validates the interval first.
        """
        self._validate_completed(entry.task_id, entry.start_time, entry.end_time)
        entry_id, affected = await db.save_time_entry_and_recompute(entry.to_dict())
        entry.id = entry_id
        return entry_id, affected

    async def delete_entry_with_recompute(self, entry_id: int) -> Dict[int, int]:
        """Delete an entry and recompute its task's spent_seconds. Returns affected."""
        return await db.delete_time_entry_and_recompute(entry_id)

    async def add_manual_entry(
        self, task_id: int, start_time: datetime, end_time: datetime
    ) -> Tuple[TimeEntry, Dict[int, int]]:
        """Create a completed entry for already-done work and recompute spent.

        Returns (entry, {task_id: new_spent}).
        """
        self._validate_completed(task_id, start_time, end_time)
        entry = TimeEntry(task_id=task_id, start_time=start_time, end_time=end_time)
        _, affected = await self.save_entry_with_recompute(entry)
        return entry, affected

    async def load_time_entries_for_task(self, task_id: int) -> List[TimeEntry]:
        """Load all time entries for a task."""
        return [TimeEntry.from_dict(d) for d in await db.load_time_entries_for_task(task_id)]

    async def load_time_entries(self, limit: Optional[int] = None) -> List[dict]:
        """Load all time entries from the database."""
        return await db.load_time_entries(limit)
