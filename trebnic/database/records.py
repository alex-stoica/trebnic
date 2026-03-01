import sqlite3
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from database.helpers import (
    DatabaseError,
    LockedDataWriteError,
    LOCKED_PLACEHOLDER,
    _encrypt_field,
    _decrypt_field,
)

logger = logging.getLogger(__name__)


class RecordsMixin:
    """Project, time entry, and daily note operations mixin."""

    # ========================================================================
    # Projects
    # ========================================================================

    async def save_project(self, p: Dict[str, str]) -> None:
        # Guard against saving locked placeholder data
        if p.get("name") == LOCKED_PLACEHOLDER:
            raise LockedDataWriteError(
                "Cannot save project with locked placeholder data. "
                "This would overwrite encrypted content. Unlock the app first."
            )

        try:
            # Encrypt project name
            name = _encrypt_field(p["name"])
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO projects (id,name,icon,color) VALUES (?,?,?,?)",
                    (p["id"], name, p["icon"], p["color"])
                )
                await conn.commit()
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error saving project: {e}")
            raise DatabaseError(f"Failed to save project: {e}") from e

    async def delete_project(self, project_id: str) -> int:
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE project_id=?",
                    (project_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    count = row[0]

                await conn.execute(
                    "DELETE FROM time_entries WHERE task_id IN "
                    "(SELECT id FROM tasks WHERE project_id=?)",
                    (project_id,)
                )
                await conn.execute("DELETE FROM tasks WHERE project_id=?", (project_id,))
                await conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
                await conn.commit()
                return count
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error deleting project {project_id}: {e}")
            raise DatabaseError(f"Failed to delete project: {e}") from e

    async def load_projects(self) -> List[Dict[str, str]]:
        try:
            async with self._get_connection() as conn:
                async with conn.execute("SELECT * FROM projects") as cursor:
                    result = []
                    async for r in cursor:
                        project = dict(r)
                        # Decrypt project name
                        project["name"] = _decrypt_field(project.get("name", ""))
                        result.append(project)
                    return result
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading projects: {e}")
            raise DatabaseError(f"Failed to load projects: {e}") from e

    # ========================================================================
    # Time Entries
    # ========================================================================

    async def save_time_entry(self, entry: Dict[str, Any]) -> int:
        """Save a time entry to the database."""
        try:
            async with self._get_connection() as conn:
                if entry.get("id") is None:
                    cursor = await conn.execute(
                        "INSERT INTO time_entries (task_id, start_time, end_time) "
                        "VALUES (?, ?, ?)",
                        (entry["task_id"], entry["start_time"], entry["end_time"])
                    )
                    await conn.commit()
                    return cursor.lastrowid
                await conn.execute(
                    "UPDATE time_entries SET task_id=?, start_time=?, end_time=? "
                    "WHERE id=?",
                    (entry["task_id"], entry["start_time"], entry["end_time"], entry["id"])
                )
                await conn.commit()
                return entry["id"]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error saving time entry: {e}")
            raise DatabaseError(f"Failed to save time entry: {e}") from e

    async def load_time_entries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Load time entries from the database, ordered by start time descending."""
        try:
            async with self._get_connection() as conn:
                if limit is not None:
                    query = "SELECT * FROM time_entries ORDER BY start_time DESC LIMIT ?"
                    async with conn.execute(query, (limit,)) as cursor:
                        return [dict(r) async for r in cursor]
                else:
                    query = "SELECT * FROM time_entries ORDER BY start_time DESC"
                    async with conn.execute(query) as cursor:
                        return [dict(r) async for r in cursor]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading time entries: {e}")
            raise DatabaseError(f"Failed to load time entries: {e}") from e

    async def load_time_entries_for_task(self, task_id: int) -> List[Dict[str, Any]]:
        """Load time entries for a specific task."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM time_entries WHERE task_id=? ORDER BY start_time DESC",
                    (task_id,)
                ) as cursor:
                    return [dict(r) async for r in cursor]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading time entries for task {task_id}: {e}")
            raise DatabaseError(f"Failed to load time entries: {e}") from e

    async def load_time_entries_by_date(self, target_date: date) -> List[Dict[str, Any]]:
        """Load time entries for a specific date."""
        try:
            date_str = target_date.isoformat()
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM time_entries "
                    "WHERE date(start_time) = ? "
                    "ORDER BY start_time ASC",
                    (date_str,)
                ) as cursor:
                    return [dict(r) async for r in cursor]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading time entries for date {target_date}: {e}")
            raise DatabaseError(f"Failed to load time entries: {e}") from e

    async def delete_time_entry(self, entry_id: int) -> None:
        """Delete a time entry."""
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM time_entries WHERE id=?", (entry_id,))
                await conn.commit()
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error deleting time entry {entry_id}: {e}")
            raise DatabaseError(f"Failed to delete time entry: {e}") from e

    async def load_incomplete_time_entry(self) -> Optional[Dict[str, Any]]:
        """Load the first incomplete time entry (end_time is NULL).

        Returns the entry if found, or None if no incomplete entries exist.
        """
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM time_entries WHERE end_time IS NULL "
                    "ORDER BY start_time DESC LIMIT 1"
                ) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading incomplete time entry: {e}")
            return None

    async def get_total_tracked_today(self) -> int:
        """Get total tracked seconds for today."""
        try:
            today = date.today().isoformat()
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT SUM("
                    "  CASE WHEN end_time IS NOT NULL THEN "
                    "    (julianday(end_time) - julianday(start_time)) * 86400 "
                    "  ELSE 0 END"
                    ") as total FROM time_entries WHERE date(start_time) = ?",
                    (today,)
                ) as cursor:
                    result = await cursor.fetchone()
                    return int(result[0] or 0)
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error getting total tracked today: {e}")
            raise DatabaseError(f"Failed to get total tracked today: {e}") from e

    # ========================================================================
    # Daily Notes
    # ========================================================================

    async def get_daily_note(self, note_date: date) -> Optional[Dict[str, Any]]:
        """Get a daily note for a specific date."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM daily_notes WHERE date = ?",
                    (note_date.isoformat(),)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row is None:
                        return None
                    result = dict(row)
                    result["content"] = _decrypt_field(result.get("content", ""))
                    return result
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading daily note for {note_date}: {e}")
            raise DatabaseError(f"Failed to load daily note: {e}") from e

    async def save_daily_note(self, note_date: date, content: str) -> None:
        """Save or update a daily note."""
        if content == LOCKED_PLACEHOLDER:
            raise LockedDataWriteError(
                "Cannot save daily note with locked placeholder data."
            )
        encrypted_content = _encrypt_field(content)
        now = datetime.now().isoformat()
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO daily_notes (date, content, updated_at) VALUES (?, ?, ?)",
                    (note_date.isoformat(), encrypted_content, now)
                )
                await conn.commit()
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error saving daily note for {note_date}: {e}")
            raise DatabaseError(f"Failed to save daily note: {e}") from e

    async def get_daily_notes_range(self, start: date, end: date) -> List[Dict[str, Any]]:
        """Get daily notes for a date range (inclusive)."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM daily_notes WHERE date >= ? AND date <= ? ORDER BY date",
                    (start.isoformat(), end.isoformat())
                ) as cursor:
                    result = []
                    async for row in cursor:
                        note = dict(row)
                        note["content"] = _decrypt_field(note.get("content", ""))
                        result.append(note)
                    return result
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading daily notes for range {start}-{end}: {e}")
            raise DatabaseError(f"Failed to load daily notes: {e}") from e

    async def get_all_daily_notes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all daily notes ordered by date descending."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM daily_notes WHERE content != '' ORDER BY date DESC LIMIT ?",
                    (limit,)
                ) as cursor:
                    result = []
                    async for row in cursor:
                        note = dict(row)
                        note["content"] = _decrypt_field(note.get("content", ""))
                        result.append(note)
                    return result
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading all daily notes: {e}")
            raise DatabaseError(f"Failed to load daily notes: {e}") from e
