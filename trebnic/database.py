import aiosqlite
import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional, Any, Dict, List, AsyncIterator

from config import DEFAULT_ESTIMATED_SECONDS, RecurrenceFrequency

DB_PATH = Path("trebnic.db")

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class Database:
    _instance: Optional["Database"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "Database":
        if cls._instance is None:
            with cls._instance_lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._init_lock = threading.Lock()
                    cls._instance._connection: Optional[aiosqlite.Connection] = None
                    cls._instance._conn_lock: Optional[asyncio.Lock] = None
        return cls._instance

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the async lock (lazy initialization for correct event loop)."""
        if self._conn_lock is None:
            self._conn_lock = asyncio.Lock()
        return self._conn_lock

    async def _ensure_connection(self) -> aiosqlite.Connection:
        """Get or create a persistent database connection."""
        if self._connection is None or not self._connection._running:
            self._connection = await aiosqlite.connect(DB_PATH)
            self._connection.row_factory = aiosqlite.Row
            # Enable WAL mode for better concurrent access
            await self._connection.execute("PRAGMA journal_mode=WAL")
            await self._connection.execute("PRAGMA busy_timeout=5000")
        return self._connection

    @asynccontextmanager
    async def _get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Get a database connection with row_factory pre-configured.

        Uses a persistent connection to avoid high-frequency open/close overhead.
        """
        async with self._get_lock():
            conn = await self._ensure_connection()
            yield conn

    async def close(self) -> None:
        """Close the persistent database connection."""
        if self._connection is not None:
            try:
                await self._connection.close()
            except Exception as e:
                logger.warning(f"Error closing database connection: {e}")
            finally:
                self._connection = None

    async def init_db(self) -> None:
        """Initialize the database schema if needed."""
        with self._init_lock:
            if self._initialized:
                return
            async with self._get_connection() as conn:
                await self._init_schema(conn)
                await self._migrate_schema(conn)
                await conn.commit()
            self._initialized = True

    async def _init_schema(self, conn: aiosqlite.Connection) -> None:
        default_freq = RecurrenceFrequency.WEEKS.value
        try:
            await conn.executescript(f"""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    icon TEXT NOT NULL, color TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                    spent_seconds INTEGER DEFAULT 0,
                    estimated_seconds INTEGER DEFAULT {DEFAULT_ESTIMATED_SECONDS},
                    project_id TEXT, due_date TEXT, is_done INTEGER DEFAULT 0,
                    recurrent INTEGER DEFAULT 0, recurrence_interval INTEGER DEFAULT 1,
                    recurrence_frequency TEXT DEFAULT '{default_freq}',
                    recurrence_weekdays TEXT DEFAULT '[]', notes TEXT DEFAULT '',
                    sort_order INTEGER DEFAULT 0,
                    recurrence_end_type TEXT DEFAULT 'never',
                    recurrence_end_date TEXT
                );
                CREATE TABLE IF NOT EXISTS time_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(is_done);
                CREATE INDEX IF NOT EXISTS idx_time_entries_task ON time_entries(task_id);
                CREATE INDEX IF NOT EXISTS idx_time_entries_start ON time_entries(start_time);
            """)
        except Exception as e:
            logger.error(f"Error initializing database schema: {e}")
            raise DatabaseError(f"Failed to initialize schema: {e}") from e

    async def _migrate_schema(self, conn: aiosqlite.Connection) -> None:
        """Handle schema migrations for existing databases."""
        try:
            async with conn.execute("PRAGMA table_info(tasks)") as cursor:
                cols = [r[1] async for r in cursor]

            if "sort_order" not in cols:
                await conn.execute(
                    "ALTER TABLE tasks ADD COLUMN sort_order INTEGER DEFAULT 0"
                )
            if "recurrence_end_type" not in cols:
                await conn.execute(
                    "ALTER TABLE tasks ADD COLUMN recurrence_end_type TEXT DEFAULT 'never'"
                )
            if "recurrence_end_date" not in cols:
                await conn.execute(
                    "ALTER TABLE tasks ADD COLUMN recurrence_end_date TEXT"
                )
            if "recurrence_from_completion" not in cols:
                await conn.execute(
                    "ALTER TABLE tasks ADD COLUMN recurrence_from_completion INTEGER DEFAULT 0"
                )

            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cursor:
                tables = [r[0] async for r in cursor]

            if "time_entries" not in tables:
                await conn.execute("""
                    CREATE TABLE time_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                    )
                """)
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_time_entries_task ON time_entries(task_id)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_time_entries_start ON time_entries(start_time)"
                )
        except Exception as e:
            logger.error(f"Error during schema migration: {e}")
            raise DatabaseError(f"Failed to migrate schema: {e}") from e

    async def seed_default_data(self) -> None:
        """Insert default seed data after factory reset."""
        try:
            default_projects = [
                {"id": "personal", "name": "Personal", "icon": "📋", "color": "#2196f3"},
                {"id": "work", "name": "Work", "icon": "💼", "color": "#4caf50"},
            ]
            for project in default_projects:
                await self.save_project(project)

            from datetime import datetime, timedelta
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
                "notes": "This is your first task. Check out the Stats to see your time entries!",
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

        except Exception as e:
            logger.error(f"Error seeding default data: {e}")
            raise DatabaseError(f"Failed to seed default data: {e}") from e

    async def save_task(self, t: Dict[str, Any]) -> int:
        weekdays = json.dumps(t.get("recurrence_weekdays", []))
        due_date = t["due_date"]
        if isinstance(due_date, date):
            due_date = due_date.isoformat()
        recurrence_end_date = t.get("recurrence_end_date")
        if isinstance(recurrence_end_date, date):
            recurrence_end_date = recurrence_end_date.isoformat()

        params = (
            t["title"],
            t["spent_seconds"],
            t["estimated_seconds"],
            t["project_id"],
            due_date,
            t.get("is_done", 0),
            t.get("recurrent", 0),
            t.get("recurrence_interval", 1),
            t.get("recurrence_frequency", RecurrenceFrequency.WEEKS.value),
            weekdays,
            t.get("notes", ""),
            t.get("sort_order", 0),
            t.get("recurrence_end_type", "never"),
            recurrence_end_date,
            t.get("recurrence_from_completion", 0),
        )
        try:
            async with self._get_connection() as conn:
                if t.get("id") is None:
                    cursor = await conn.execute(
                        "INSERT INTO tasks "
                        "(title,spent_seconds,estimated_seconds,project_id,"
                        "due_date,is_done,recurrent,recurrence_interval,recurrence_frequency,"
                        "recurrence_weekdays,notes,sort_order,recurrence_end_type,"
                        "recurrence_end_date,recurrence_from_completion) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        params
                    )
                    await conn.commit()
                    return cursor.lastrowid
                await conn.execute(
                    "UPDATE tasks SET title=?,spent_seconds=?,estimated_seconds=?,"
                    "project_id=?,due_date=?,is_done=?,recurrent=?,recurrence_interval=?,"
                    "recurrence_frequency=?,recurrence_weekdays=?,notes=?,sort_order=?,"
                    "recurrence_end_type=?,recurrence_end_date=?,recurrence_from_completion=? WHERE id=?",
                    params + (t["id"],)
                )
                await conn.commit()
                return t["id"]
        except Exception as e:
            logger.error(f"Error saving task: {e}")
            raise DatabaseError(f"Failed to save task: {e}") from e

    async def delete_task(self, task_id: int) -> None:
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM time_entries WHERE task_id=?", (task_id,))
                await conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
                await conn.commit()
        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            raise DatabaseError(f"Failed to delete task: {e}") from e

    async def load_tasks(self) -> List[Dict[str, Any]]:
        try:
            async with self._get_connection() as conn:
                async with conn.execute("SELECT * FROM tasks ORDER BY sort_order, id") as cursor:
                    result = []
                    async for r in cursor:
                        task_dict = dict(r)
                        task_dict["recurrence_weekdays"] = json.loads(
                            task_dict.get("recurrence_weekdays", "[]")
                        )
                        task_dict["recurrence_end_type"] = task_dict.get(
                            "recurrence_end_type", "never"
                        )
                        task_dict["recurrence_from_completion"] = task_dict.get(
                            "recurrence_from_completion", 0
                        )
                        # Convert date strings back to date objects
                        if task_dict.get("due_date"):
                            task_dict["due_date"] = date.fromisoformat(task_dict["due_date"])
                        if task_dict.get("recurrence_end_date"):
                            task_dict["recurrence_end_date"] = date.fromisoformat(
                                task_dict["recurrence_end_date"]
                            )
                        result.append(task_dict)
                    return result
        except Exception as e:
            logger.error(f"Error loading tasks: {e}")
            raise DatabaseError(f"Failed to load tasks: {e}") from e

    async def save_project(self, p: Dict[str, str]) -> None:
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO projects (id,name,icon,color) VALUES (?,?,?,?)",
                    (p["id"], p["name"], p["icon"], p["color"])
                )
                await conn.commit()
        except Exception as e:
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
        except Exception as e:
            logger.error(f"Error deleting project {project_id}: {e}")
            raise DatabaseError(f"Failed to delete project: {e}") from e

    async def load_projects(self) -> List[Dict[str, str]]:
        try:
            async with self._get_connection() as conn:
                async with conn.execute("SELECT * FROM projects") as cursor:
                    return [dict(r) async for r in cursor]
        except Exception as e:
            logger.error(f"Error loading projects: {e}")
            raise DatabaseError(f"Failed to load projects: {e}") from e

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
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
            logger.error(f"Error loading time entries for date {target_date}: {e}")
            raise DatabaseError(f"Failed to load time entries: {e}") from e

    async def delete_time_entry(self, entry_id: int) -> None:
        """Delete a time entry."""
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM time_entries WHERE id=?", (entry_id,))
                await conn.commit()
        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
            logger.error(f"Error getting total tracked today: {e}")
            raise DatabaseError(f"Failed to get total tracked today: {e}") from e

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value. Returns default if not found or on error."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT value FROM settings WHERE key=?",
                    (key,)
                ) as cursor:
                    row = await cursor.fetchone()
                    return json.loads(row["value"]) if row else default
        except Exception as e:
            logger.warning(f"Error getting setting {key}: {e}")
            return default

    async def set_setting(self, key: str, value: Any) -> None:
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
                    (key, json.dumps(value))
                )
                await conn.commit()
        except Exception as e:
            logger.error(f"Error setting {key}: {e}")
            raise DatabaseError(f"Failed to save setting: {e}") from e

    async def clear_all(self) -> None:
        try:
            async with self._get_connection() as conn:
                await conn.executescript(
                    "DELETE FROM time_entries; DELETE FROM tasks; "
                    "DELETE FROM projects; DELETE FROM settings;"
                )
                await conn.commit()
        except Exception as e:
            logger.error(f"Error clearing database: {e}")
            raise DatabaseError(f"Failed to clear database: {e}") from e

    async def is_empty(self) -> bool:
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT COUNT(*) FROM projects"
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] == 0
        except Exception as e:
            logger.error(f"Error checking if database is empty: {e}")
            raise DatabaseError(f"Failed to check database: {e}") from e

    async def load_tasks_filtered(
        self,
        is_done: Optional[bool] = None,
        due_date_lte: Optional[date] = None,
        due_date_gt: Optional[date] = None,
        due_date_eq: Optional[date] = None,
        due_date_is_null: Optional[bool] = None,
        project_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Load tasks with SQL-level filtering for efficient queries.

        Args:
            is_done: Filter by completion status (True/False/None for all)
            due_date_lte: Due date <= this date (for "today" view)
            due_date_gt: Due date > this date (for "upcoming" view)
            due_date_eq: Due date == this date (exact match)
            due_date_is_null: True to get tasks without due date (inbox)
            project_ids: List of project IDs to filter by
            limit: Maximum number of results

        Returns:
            List of task dictionaries matching the filters.
        """
        try:
            conditions = []
            params: List[Any] = []

            if is_done is not None:
                conditions.append("is_done = ?")
                params.append(1 if is_done else 0)

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
                    result = []
                    async for r in cursor:
                        task_dict = dict(r)
                        task_dict["recurrence_weekdays"] = json.loads(
                            task_dict.get("recurrence_weekdays", "[]")
                        )
                        task_dict["recurrence_end_type"] = task_dict.get(
                            "recurrence_end_type", "never"
                        )
                        task_dict["recurrence_from_completion"] = task_dict.get(
                            "recurrence_from_completion", 0
                        )
                        if task_dict.get("due_date"):
                            task_dict["due_date"] = date.fromisoformat(task_dict["due_date"])
                        if task_dict.get("recurrence_end_date"):
                            task_dict["recurrence_end_date"] = date.fromisoformat(
                                task_dict["recurrence_end_date"]
                            )
                        result.append(task_dict)
                    return result
        except Exception as e:
            logger.error(f"Error loading filtered tasks: {e}")
            raise DatabaseError(f"Failed to load filtered tasks: {e}") from e


db = Database()
