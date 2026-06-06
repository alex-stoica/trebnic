import aiosqlite
import asyncio
import json
import sqlite3
import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional, Any, AsyncIterator

import database as _pkg
from config import DEFAULT_ESTIMATED_SECONDS, RecurrenceFrequency
from database.helpers import DatabaseError

logger = logging.getLogger(__name__)


class DatabaseCore:
    """Async SQLite database with persistent connection and async lock.

    Uses a single persistent connection with an async lock to serialize
    access (SQLite limitation). The connection is lazily initialized on
    first use and reused until explicitly closed.
    """
    _instance: Optional["DatabaseCore"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "DatabaseCore":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._init_lock: Optional[asyncio.Lock] = None
                    cls._instance._conn: Optional[aiosqlite.Connection] = None
                    cls._instance._conn_lock: Optional[asyncio.Lock] = None
        return cls._instance

    async def _ensure_connection(self) -> aiosqlite.Connection:
        """Ensure we have an open connection, creating one if needed."""
        if self._conn is None:
            try:
                self._conn = await aiosqlite.connect(_pkg.DB_PATH)
                self._conn.row_factory = aiosqlite.Row
                await self._conn.execute("PRAGMA journal_mode=WAL")
                await self._conn.execute("PRAGMA busy_timeout=5000")
                await self._conn.execute("PRAGMA foreign_keys=ON")
            except (sqlite3.Error, OSError) as e:
                self._conn = None
                raise DatabaseError(f"Cannot open database at {_pkg.DB_PATH}: {e}") from e
        return self._conn

    async def _get_lock(self) -> asyncio.Lock:
        """Get or create the async lock for connection serialization."""
        if self._conn_lock is None:
            self._conn_lock = asyncio.Lock()
        return self._conn_lock

    @asynccontextmanager
    async def _get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Get a database connection with serialized access."""
        lock = await self._get_lock()
        async with lock:
            conn = await self._ensure_connection()
            yield conn

    async def close(self) -> None:
        """Close the persistent connection."""
        if self._conn is not None:
            try:
                await self._conn.close()
            except (sqlite3.Error, OSError) as e:
                logger.warning(f"Error closing database connection: {e}")
            finally:
                self._conn = None

    async def _get_init_lock(self) -> asyncio.Lock:
        """Get or create the async lock for init serialization."""
        if self._init_lock is None:
            self._init_lock = asyncio.Lock()
        return self._init_lock

    async def init_db(self) -> None:
        """Initialize the database schema if needed."""
        lock = await self._get_init_lock()
        async with lock:
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
                    recurrence_end_date TEXT,
                    is_draft INTEGER DEFAULT 0,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS time_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    heartbeat_at TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS daily_notes (
                    date TEXT PRIMARY KEY,
                    content TEXT DEFAULT '',
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(is_done);
                CREATE INDEX IF NOT EXISTS idx_tasks_done_due_date ON tasks(is_done, due_date);
                CREATE INDEX IF NOT EXISTS idx_time_entries_task ON time_entries(task_id);
                CREATE INDEX IF NOT EXISTS idx_time_entries_start ON time_entries(start_time);
                CREATE INDEX IF NOT EXISTS idx_time_entries_task_end ON time_entries(task_id, end_time);
            """)
            # idx_tasks_done_completed_at is created in _migrate_schema, AFTER the
            # completed_at column is guaranteed to exist (it does not on upgrade when
            # this CREATE-IF-NOT-EXISTS is a no-op on the pre-existing tasks table).
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
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
            if "is_draft" not in cols:
                await conn.execute(
                    "ALTER TABLE tasks ADD COLUMN is_draft INTEGER DEFAULT 0"
                )
            # completed_at: real completion timestamp.
            if "completed_at" not in cols:
                await conn.execute("ALTER TABLE tasks ADD COLUMN completed_at TEXT")

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
                        heartbeat_at TEXT,
                        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                    )
                """)
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_time_entries_task ON time_entries(task_id)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_time_entries_start ON time_entries(start_time)"
                )
            else:
                # heartbeat_at: lets a live timer's entry keep end_time NULL while
                # still persisting liveness for crash recovery.
                async with conn.execute("PRAGMA table_info(time_entries)") as cursor:
                    te_cols = [r[1] async for r in cursor]
                if "heartbeat_at" not in te_cols:
                    await conn.execute("ALTER TABLE time_entries ADD COLUMN heartbeat_at TEXT")

            # Indexes added alongside completed_at/heartbeat_at (idempotent).
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_done_completed_at "
                "ON tasks(is_done, completed_at)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_done_due_date ON tasks(is_done, due_date)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_time_entries_task_end "
                "ON time_entries(task_id, end_time)"
            )

            if "daily_notes" not in tables:
                await conn.execute("""
                    CREATE TABLE daily_notes (
                        date TEXT PRIMARY KEY,
                        content TEXT DEFAULT '',
                        updated_at TEXT
                    )
                """)

            if "scheduled_notifications" in tables:
                await conn.execute("DROP TABLE scheduled_notifications")

            # Reconcile cached spent_seconds from canonical entries. Gated on a
            # one-time settings flag (not "did we just add completed_at") so that
            # beta DBs which already have the column but stale totals are healed too.
            # Runs only now that time_entries is guaranteed to exist (older DBs
            # create it above).
            async with conn.execute(
                "SELECT 1 FROM settings WHERE key = 'spent_reconciled_v1'"
            ) as cursor:
                already_reconciled = await cursor.fetchone()
            if not already_reconciled:
                await self._reconcile_spent_seconds(conn)
                await conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('spent_reconciled_v1', ?)",
                    (json.dumps(True),),
                )
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error during schema migration: {e}")
            raise DatabaseError(f"Failed to migrate schema: {e}") from e

    async def _reconcile_spent_seconds(self, conn: aiosqlite.Connection) -> None:
        """Make task.spent_seconds the canonical sum of completed time entries.

        Robust by design (one-time upgrade step on possibly-messy legacy data):
        - durations are parsed in Python so a stray datetime format never zeroes a
          real value via SQL date math;
        - a task with spent_seconds > 0 but no usable completed entry gets ONE
          synthetic entry preserving that value (so nothing is silently lost);
        - before/after totals are logged so any visible shift on upgrade is
          attributable to healing the original bug, not data loss.
        """
        def _parse(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None

        async with conn.execute("SELECT id, spent_seconds, due_date, completed_at FROM tasks") as cur:
            tasks = [dict(r) async for r in cur]
        async with conn.execute(
            "SELECT task_id, start_time, end_time FROM time_entries WHERE end_time IS NOT NULL"
        ) as cur:
            entries = [dict(r) async for r in cur]

        sums: dict = {}
        for e in entries:
            start = _parse(e.get("start_time"))
            end = _parse(e.get("end_time"))
            if start is None or end is None:
                continue
            secs = int(round((end - start).total_seconds()))
            if secs <= 0:
                continue
            sums[e["task_id"]] = sums.get(e["task_id"], 0) + secs

        before_total = sum(int(t.get("spent_seconds") or 0) for t in tasks)
        synthesized = 0
        for t in tasks:
            tid = t["id"]
            old_spent = int(t.get("spent_seconds") or 0)
            entry_sum = sums.get(tid, 0)
            if entry_sum > 0:
                if entry_sum != old_spent:
                    if old_spent > entry_sum:
                        # Entries are canonical, so this is intentional, but log it:
                        # a legacy cached total exceeded the sum of its entries.
                        logger.info(
                            "reconcile: task %s spent %ds -> %ds (cache exceeded entries)",
                            tid, old_spent, entry_sum,
                        )
                    await conn.execute(
                        "UPDATE tasks SET spent_seconds = ? WHERE id = ?", (entry_sum, tid)
                    )
            elif old_spent > 0:
                # Preserve entry-less spent (legacy update_task_time / imports) by
                # backing it with one synthetic completed entry.
                anchor = _parse(t.get("completed_at"))
                if anchor is None and t.get("due_date"):
                    try:
                        anchor = datetime.fromisoformat(t["due_date"])
                    except (ValueError, TypeError):
                        anchor = None
                if anchor is None:
                    anchor = datetime.now()
                start = anchor - timedelta(seconds=old_spent)
                await conn.execute(
                    "INSERT INTO time_entries (task_id, start_time, end_time) VALUES (?, ?, ?)",
                    (tid, start.isoformat(), anchor.isoformat()),
                )
                synthesized += 1

        async with conn.execute(
            "SELECT COALESCE(SUM(spent_seconds), 0) FROM tasks"
        ) as cur:
            row = await cur.fetchone()
            after_total = int(row[0] or 0)
        logger.info(
            "spent_seconds reconcile: %d tasks, %d synthetic entries, total %ds -> %ds",
            len(tasks), synthesized, before_total, after_total,
        )

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
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
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
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error setting {key}: {e}")
            raise DatabaseError(f"Failed to save setting: {e}") from e

    async def is_empty(self) -> bool:
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT COUNT(*) FROM projects"
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0] == 0
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error checking if database is empty: {e}")
            raise DatabaseError(f"Failed to check database: {e}") from e

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance.

        Note: This method is primarily used for testing to ensure
        a fresh Database instance between test cases. Not typically
        called in production code.
        """
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance._initialized = False
                cls._instance._conn = None
                cls._instance._conn_lock = None
                cls._instance = None
