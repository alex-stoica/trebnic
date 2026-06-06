import json
import sqlite3
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from config import RecurrenceFrequency
from database.helpers import (
    DatabaseError,
    LockedDataWriteError,
    LOCKED_PLACEHOLDER,
    _encrypt_field,
    _decrypt_field,
    _deserialize_task_row,
)

logger = logging.getLogger(__name__)


class TasksMixin:
    """Task CRUD operations mixin for the Database class."""

    async def save_task(self, t: Dict[str, Any]) -> int:
        # Guard against saving locked placeholder data
        title = t.get("title", "")
        notes = t.get("notes", "")
        if title == LOCKED_PLACEHOLDER or notes == LOCKED_PLACEHOLDER:
            raise LockedDataWriteError(
                "Cannot save task with locked placeholder data. "
                "This would overwrite encrypted content. Unlock the app first."
            )

        weekdays = json.dumps(t.get("recurrence_weekdays", []))
        due_date = t["due_date"]
        if isinstance(due_date, date):
            due_date = due_date.isoformat()
        recurrence_end_date = t.get("recurrence_end_date")
        if isinstance(recurrence_end_date, date):
            recurrence_end_date = recurrence_end_date.isoformat()
        completed_at = t.get("completed_at")
        if isinstance(completed_at, datetime):
            completed_at = completed_at.isoformat()

        # Encrypt sensitive fields
        title = _encrypt_field(t["title"])
        notes = _encrypt_field(t.get("notes", ""))

        # Metadata values, in column order, EXCLUDING spent_seconds. spent_seconds is
        # canonical (sum of completed time entries) and is only ever written by the
        # recompute helpers / migration — never by a metadata save, so a stale
        # in-memory value cannot clobber the cache. See database/records.py.
        meta = (
            title,
            t["estimated_seconds"],
            t["project_id"],
            due_date,
            t.get("is_done", 0),
            t.get("recurrent", 0),
            t.get("recurrence_interval", 1),
            t.get("recurrence_frequency", RecurrenceFrequency.WEEKS.value),
            weekdays,
            notes,
            t.get("sort_order", 0),
            t.get("recurrence_end_type", "never"),
            recurrence_end_date,
            t.get("recurrence_from_completion", 0),
            t.get("is_draft", 0),
            completed_at,
        )
        try:
            async with self._get_connection() as conn:
                if t.get("id") is None:
                    # INSERT sets spent_seconds for the brand-new row (0/known).
                    cursor = await conn.execute(
                        "INSERT INTO tasks "
                        "(title,estimated_seconds,project_id,"
                        "due_date,is_done,recurrent,recurrence_interval,recurrence_frequency,"
                        "recurrence_weekdays,notes,sort_order,recurrence_end_type,"
                        "recurrence_end_date,recurrence_from_completion,is_draft,completed_at,"
                        "spent_seconds)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        meta + (t.get("spent_seconds", 0),)
                    )
                    await conn.commit()
                    return cursor.lastrowid
                await conn.execute(
                    "UPDATE tasks SET title=?,estimated_seconds=?,"
                    "project_id=?,due_date=?,is_done=?,recurrent=?,recurrence_interval=?,"
                    "recurrence_frequency=?,recurrence_weekdays=?,notes=?,sort_order=?,"
                    "recurrence_end_type=?,recurrence_end_date=?,recurrence_from_completion=?,"
                    "is_draft=?,completed_at=? WHERE id=?",
                    meta + (t["id"],)
                )
                await conn.commit()
                return t["id"]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error saving task: {e}")
            raise DatabaseError(f"Failed to save task: {e}") from e

    async def delete_task(self, task_id: int) -> None:
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM time_entries WHERE task_id=?", (task_id,))
                await conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
                await conn.commit()
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            raise DatabaseError(f"Failed to delete task: {e}") from e

    async def delete_recurring_tasks_by_title(self, title: str) -> int:
        """Delete all recurring tasks with the given title.

        Since titles are encrypted with random nonces, we cannot match in SQL.
        Instead, we fetch all recurring tasks, decrypt in memory, and filter.

        Returns:
            Number of tasks deleted
        """
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT id, title FROM tasks WHERE recurrent = 1"
                ) as cursor:
                    rows = [dict(row) async for row in cursor]

                task_ids = []
                for row in rows:
                    decrypted_title = _decrypt_field(row.get("title", ""))
                    if decrypted_title == title:
                        task_ids.append(row["id"])

                if not task_ids:
                    return 0

                placeholders = ",".join("?" * len(task_ids))
                await conn.execute(
                    f"DELETE FROM time_entries WHERE task_id IN ({placeholders})",
                    tuple(task_ids)
                )
                await conn.execute(
                    f"DELETE FROM tasks WHERE id IN ({placeholders})",
                    tuple(task_ids)
                )
                await conn.commit()
                return len(task_ids)
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error deleting recurring tasks '{title}': {e}")
            raise DatabaseError(f"Failed to delete recurring tasks: {e}") from e

    async def get_max_sort_order(self) -> int:
        """Highest sort_order across all tasks, or -1 if there are none.

        Used so a new task lands LAST. (The old limit=1 query returned the lowest
        order because rows are sorted ascending.)
        """
        try:
            async with self._get_connection() as conn:
                async with conn.execute("SELECT COALESCE(MAX(sort_order), -1) FROM tasks") as cursor:
                    row = await cursor.fetchone()
                    return int(row[0]) if row and row[0] is not None else -1
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error getting max sort_order: {e}")
            raise DatabaseError(f"Failed to get max sort_order: {e}") from e

    async def update_task_sort_orders(self, task_orders: List[tuple]) -> None:
        """Update sort_order for multiple tasks in a single transaction."""
        if not task_orders:
            return
        try:
            async with self._get_connection() as conn:
                await conn.executemany(
                    "UPDATE tasks SET sort_order = ? WHERE id = ?",
                    [(order, task_id) for task_id, order in task_orders]
                )
                await conn.commit()
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error updating task sort orders: {e}")
            raise DatabaseError(f"Failed to update task sort orders: {e}") from e

    async def load_tasks(self) -> List[Dict[str, Any]]:
        try:
            async with self._get_connection() as conn:
                async with conn.execute("SELECT * FROM tasks ORDER BY sort_order, id") as cursor:
                    return [_deserialize_task_row(r) async for r in cursor]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading tasks: {e}")
            raise DatabaseError(f"Failed to load tasks: {e}") from e

    async def load_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Load a single task by ID. Returns None if not found."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
                    row = await cursor.fetchone()
                    return _deserialize_task_row(row) if row else None
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading task by id: {e}")
            raise DatabaseError(f"Failed to load task {task_id}: {e}") from e

    async def load_tasks_filtered(
        self,
        is_done: Optional[bool] = None,
        due_date_lte: Optional[date] = None,
        due_date_gt: Optional[date] = None,
        due_date_eq: Optional[date] = None,
        due_date_is_null: Optional[bool] = None,
        completed_on: Optional[date] = None,
        project_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        is_draft: Optional[bool] = False,
    ) -> List[Dict[str, Any]]:
        """Load tasks with SQL-level filtering for efficient queries.

        completed_on: tasks completed on this calendar day. Uses an index-friendly
        half-open range on completed_at; legacy rows with NULL completed_at fall
        back to due_date == that day so pre-upgrade data still appears.
        """
        try:
            conditions = []
            params: List[Any] = []

            if is_done is not None:
                conditions.append("is_done = ?")
                params.append(1 if is_done else 0)

            if is_draft is not None:
                conditions.append("is_draft = ?")
                params.append(1 if is_draft else 0)

            if due_date_lte is not None:
                conditions.append("due_date IS NOT NULL AND due_date <= ?")
                params.append(due_date_lte.isoformat())

            if due_date_gt is not None:
                conditions.append("due_date IS NOT NULL AND due_date > ?")
                params.append(due_date_gt.isoformat())

            if due_date_eq is not None:
                conditions.append("due_date = ?")
                params.append(due_date_eq.isoformat())

            if due_date_is_null is True:
                conditions.append("due_date IS NULL")

            if completed_on is not None:
                day_start = datetime.combine(completed_on, datetime.min.time()).isoformat()
                next_day = datetime.combine(
                    completed_on + timedelta(days=1), datetime.min.time()
                ).isoformat()
                conditions.append(
                    "((completed_at >= ? AND completed_at < ?) "
                    "OR (completed_at IS NULL AND due_date = ?))"
                )
                params.extend([day_start, next_day, completed_on.isoformat()])

            if project_ids is not None and len(project_ids) > 0:
                placeholders = ",".join("?" * len(project_ids))
                conditions.append(f"project_id IN ({placeholders})")
                params.extend(project_ids)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            query = f"SELECT * FROM tasks WHERE {where_clause} ORDER BY sort_order, id"

            if limit is not None:
                query += " LIMIT ?"
                params.append(limit)

            async with self._get_connection() as conn:
                async with conn.execute(query, tuple(params)) as cursor:
                    return [_deserialize_task_row(r) async for r in cursor]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading filtered tasks: {e}")
            raise DatabaseError(f"Failed to load filtered tasks: {e}") from e

    async def load_all_encrypted_data_raw(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Load all tasks and projects with encrypted fields as-is (no decryption)."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute("SELECT id, title, notes FROM tasks") as cursor:
                    tasks = [dict(r) async for r in cursor]

                async with conn.execute("SELECT id, name FROM projects") as cursor:
                    projects = [dict(r) async for r in cursor]

                return tasks, projects
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading encrypted data: {e}")
            raise DatabaseError(f"Failed to load encrypted data: {e}") from e
