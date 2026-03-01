import json
import sqlite3
import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from config import RecurrenceFrequency
from database.helpers import (
    DatabaseError,
    _encrypt_field,
    _is_encrypted,
)

logger = logging.getLogger(__name__)


class DataOpsMixin:
    """Seed, clear, import/export, and re-encryption operations mixin."""

    async def seed_default_data(self) -> None:
        """Insert default seed data after factory reset."""
        try:
            default_projects = [
                {"id": "personal", "name": "Personal", "icon": "📋", "color": "#2196f3"},
                {"id": "work", "name": "Work", "icon": "💼", "color": "#9c27b0"},
                {"id": "sport", "name": "Sport", "icon": "🏋️", "color": "#4caf50"},
            ]
            for project in default_projects:
                await self.save_project(project)

            now = datetime.now()

            welcome_task = {
                "id": None,
                "title": "Welcome to Trebnic!",
                "spent_seconds": 1800,
                "estimated_seconds": 3600,
                "project_id": "personal",
                "due_date": date.today().isoformat(),
                "is_done": 0,
                "recurrent": 0,
                "recurrence_interval": 1,
                "recurrence_frequency": RecurrenceFrequency.WEEKS.value,
                "recurrence_weekdays": [],
                "notes": "",
                "sort_order": 0,
                "recurrence_end_type": "never",
                "recurrence_end_date": None,
            }
            task_id = await self.save_task(welcome_task)

            entry1_start = now - timedelta(hours=2, minutes=30)
            entry1_end = entry1_start + timedelta(minutes=20)
            await self.save_time_entry({
                "id": None,
                "task_id": task_id,
                "start_time": entry1_start.isoformat(),
                "end_time": entry1_end.isoformat(),
            })

            entry2_start = now - timedelta(minutes=45)
            entry2_end = entry2_start + timedelta(minutes=10)
            await self.save_time_entry({
                "id": None,
                "task_id": task_id,
                "start_time": entry2_start.isoformat(),
                "end_time": entry2_end.isoformat(),
            })

            # Recurring gym task - Tue/Thu/Sat
            gym_weekdays = [1, 3, 5]
            gym_due_date = date.today()
            if gym_due_date.weekday() not in gym_weekdays:
                for offset in range(1, 8):
                    candidate = gym_due_date + timedelta(days=offset)
                    if candidate.weekday() in gym_weekdays:
                        gym_due_date = candidate
                        break
            gym_task = {
                "id": None,
                "title": "Gym",
                "spent_seconds": 0,
                "estimated_seconds": 3600,
                "project_id": "sport",
                "due_date": gym_due_date.isoformat(),
                "is_done": 0,
                "recurrent": 1,
                "recurrence_interval": 1,
                "recurrence_frequency": RecurrenceFrequency.WEEKS.value,
                "recurrence_weekdays": [1, 3, 5],
                "notes": "",
                "sort_order": 1,
                "recurrence_end_type": "never",
                "recurrence_end_date": None,
            }
            await self.save_task(gym_task)

        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error seeding default data: {e}")
            raise DatabaseError(f"Failed to seed default data: {e}") from e

    async def clear_all(self) -> None:
        try:
            async with self._get_connection() as conn:
                await conn.executescript(
                    "DELETE FROM scheduled_notifications; DELETE FROM time_entries; "
                    "DELETE FROM tasks; DELETE FROM projects; DELETE FROM daily_notes; "
                    "DELETE FROM settings;"
                )
                await conn.commit()
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error clearing database: {e}")
            raise DatabaseError(f"Failed to clear database: {e}") from e

    async def import_all(
        self,
        projects: List[Dict],
        tasks: List[Dict],
        time_entries: List[Dict],
        daily_notes: List[Dict],
        settings: Dict[str, Any],
    ) -> None:
        """Atomically import a full dataset, replacing all existing data.

        Uses explicit IDs for tasks and time entries to preserve foreign-key
        relationships across export/import cycles.
        """
        try:
            await self.clear_all()
            async with self._get_connection() as conn:
                # Projects (string IDs, use save_project logic inline)
                for p in projects:
                    name = _encrypt_field(p["name"])
                    await conn.execute(
                        "INSERT OR REPLACE INTO projects (id, name, icon, color) VALUES (?, ?, ?, ?)",
                        (p["id"], name, p.get("icon", ""), p.get("color", "")),
                    )

                # Tasks with explicit IDs
                for t in tasks:
                    weekdays = json.dumps(t.get("recurrence_weekdays", []))
                    due = t.get("due_date")
                    if isinstance(due, date):
                        due = due.isoformat()
                    rec_end = t.get("recurrence_end_date")
                    if isinstance(rec_end, date):
                        rec_end = rec_end.isoformat()
                    title = _encrypt_field(t["title"])
                    notes = _encrypt_field(t.get("notes", ""))
                    await conn.execute(
                        "INSERT INTO tasks "
                        "(id,title,spent_seconds,estimated_seconds,project_id,"
                        "due_date,is_done,recurrent,recurrence_interval,recurrence_frequency,"
                        "recurrence_weekdays,notes,sort_order,recurrence_end_type,"
                        "recurrence_end_date,recurrence_from_completion,is_draft) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            t["id"], title, t.get("spent_seconds", 0),
                            t.get("estimated_seconds", 0), t.get("project_id"),
                            due, t.get("is_done", 0), t.get("recurrent", 0),
                            t.get("recurrence_interval", 1),
                            t.get("recurrence_frequency", "weeks"),
                            weekdays, notes, t.get("sort_order", 0),
                            t.get("recurrence_end_type", "never"), rec_end,
                            t.get("recurrence_from_completion", 0),
                            t.get("is_draft", 0),
                        ),
                    )

                # Time entries with explicit IDs
                for e in time_entries:
                    await conn.execute(
                        "INSERT INTO time_entries (id, task_id, start_time, end_time) VALUES (?, ?, ?, ?)",
                        (e["id"], e["task_id"], e["start_time"], e["end_time"]),
                    )

                # Daily notes
                for n in daily_notes:
                    note_date = n["date"]
                    if isinstance(note_date, date) and not isinstance(note_date, str):
                        note_date = note_date.isoformat()
                    content = _encrypt_field(n.get("content", ""))
                    updated_at = n.get("updated_at") or datetime.now().isoformat()
                    await conn.execute(
                        "INSERT OR REPLACE INTO daily_notes (date, content, updated_at) VALUES (?, ?, ?)",
                        (note_date, content, updated_at),
                    )

                # Settings (allow-listed keys only)
                for key, value in settings.items():
                    await conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                        (key, json.dumps(value)),
                    )

                await conn.commit()
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error importing data: {e}")
            raise DatabaseError(f"Failed to import data: {e}") from e

    async def reencrypt_all_data(
        self,
        decrypt_fn: Callable[[str], Optional[str]],
        encrypt_fn: Callable[[str], str]
    ) -> Tuple[int, int]:
        """Re-encrypt all sensitive fields with a new key.

        This is used during password change to migrate data from old key to new key.

        Args:
            decrypt_fn: Function to decrypt with OLD key (value) -> plaintext
            encrypt_fn: Function to encrypt with NEW key (plaintext) -> encrypted

        Returns:
            Tuple of (tasks_updated, projects_updated) counts.
        """
        try:
            async with self._get_connection() as conn:
                tasks_updated = 0
                projects_updated = 0

                # Re-encrypt task titles and notes
                async with conn.execute("SELECT id, title, notes FROM tasks") as cursor:
                    tasks = [dict(r) async for r in cursor]

                for task in tasks:
                    old_title = task.get("title", "")
                    old_notes = task.get("notes", "")
                    new_title = old_title
                    new_notes = old_notes

                    if old_title and _is_encrypted(old_title):
                        decrypted_title = decrypt_fn(old_title)
                        if decrypted_title is not None:
                            new_title = encrypt_fn(decrypted_title)

                    if old_notes and _is_encrypted(old_notes):
                        decrypted_notes = decrypt_fn(old_notes)
                        if decrypted_notes is not None:
                            new_notes = encrypt_fn(decrypted_notes)

                    if new_title != old_title or new_notes != old_notes:
                        await conn.execute(
                            "UPDATE tasks SET title = ?, notes = ? WHERE id = ?",
                            (new_title, new_notes, task["id"])
                        )
                        tasks_updated += 1

                # Re-encrypt project names
                async with conn.execute("SELECT id, name FROM projects") as cursor:
                    projects = [dict(r) async for r in cursor]

                for project in projects:
                    old_name = project.get("name", "")
                    new_name = old_name

                    if old_name and _is_encrypted(old_name):
                        decrypted_name = decrypt_fn(old_name)
                        if decrypted_name is not None:
                            new_name = encrypt_fn(decrypted_name)

                    if new_name != old_name:
                        await conn.execute(
                            "UPDATE projects SET name = ? WHERE id = ?",
                            (new_name, project["id"])
                        )
                        projects_updated += 1

                # Re-encrypt daily notes
                async with conn.execute("SELECT date, content FROM daily_notes") as cursor:
                    notes = [dict(r) async for r in cursor]

                for note in notes:
                    old_content = note.get("content", "")
                    new_content = old_content

                    if old_content and _is_encrypted(old_content):
                        decrypted = decrypt_fn(old_content)
                        if decrypted is not None:
                            new_content = encrypt_fn(decrypted)

                    if new_content != old_content:
                        await conn.execute(
                            "UPDATE daily_notes SET content = ? WHERE date = ?",
                            (new_content, note["date"])
                        )

                await conn.commit()
                return tasks_updated, projects_updated

        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error re-encrypting data: {e}")
            raise DatabaseError(f"Failed to re-encrypt data: {e}") from e
