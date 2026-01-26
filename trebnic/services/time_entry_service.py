from typing import List, Optional

from database import db
from models.entities import TimeEntry


class TimeEntryService:
    """Service for time entry operations.

    Handles time entry CRUD operations with database persistence.
    All data operations are async.
    """

    async def save_time_entry(self, entry: TimeEntry) -> int:
        """Save a time entry to the database.

        Returns the entry ID.
        """
        return await db.save_time_entry(entry.to_dict())

    async def delete_time_entry(self, entry_id: int) -> None:
        """Delete a time entry from the database."""
        await db.delete_time_entry(entry_id)

    async def update_time_entry(self, entry: TimeEntry) -> int:
        """Update an existing time entry.

        Returns the entry ID.
        """
        return await db.save_time_entry(entry.to_dict())

    async def load_time_entries_for_task(self, task_id: int) -> List[TimeEntry]:
        """Load all time entries for a task."""
        return [TimeEntry.from_dict(d) for d in await db.load_time_entries_for_task(task_id)]

    async def load_time_entries(self, limit: Optional[int] = None) -> List[dict]:
        """Load all time entries from the database."""
        return await db.load_time_entries(limit)
