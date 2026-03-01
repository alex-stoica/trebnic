"""Daily notes service - CRUD operations for daily notes.

One note per day, typically written after completing all tasks for the day.
"""
import logging
from datetime import date, datetime
from typing import Optional, List

from database import db, DatabaseError
from models.entities import DailyNote

logger = logging.getLogger(__name__)


class DailyNoteService:
    """Service for daily note CRUD operations."""

    async def get_note(self, note_date: date) -> Optional[DailyNote]:
        """Get a daily note for a specific date. Returns None if no note exists."""
        result = await db.get_daily_note(note_date)
        if result is None:
            return None
        return DailyNote.from_dict(result)

    async def save_note(self, note_date: date, content: str) -> DailyNote:
        """Save or update a daily note. Returns the saved note."""
        await db.save_daily_note(note_date, content)
        return DailyNote(date=note_date, content=content, updated_at=datetime.now())

    async def get_notes_range(self, start: date, end: date) -> List[DailyNote]:
        """Get daily notes for a date range (inclusive). Returns only dates that have notes."""
        results = await db.get_daily_notes_range(start, end)
        return [DailyNote.from_dict(r) for r in results]

    async def get_recent_notes(self, limit: int = 50) -> List[DailyNote]:
        """Get recent daily notes ordered by date descending."""
        results = await db.get_all_daily_notes(limit)
        return [DailyNote.from_dict(r) for r in results]

    async def get_dates_with_notes(self, start: date, end: date) -> set:
        """Get the set of dates that have notes in a range. Efficient for calendar indicators."""
        notes = await self.get_notes_range(start, end)
        return {n.date for n in notes if n.content.strip()}
