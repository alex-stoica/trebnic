import sqlite3
import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional, Any, Dict, List

from config import DEFAULT_ESTIMATED_SECONDS, RecurrenceFrequency

DB_PATH = Path("trebnic.db")

logger = logging.getLogger(__name__)

sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_converter(
    "DATE",
    lambda s: date.fromisoformat(s.decode()) if s else None
)


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class Database:
    _instance: Optional["Database"] = None

    def __new__(cls) -> "Database":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = None
        return cls._instance

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None or not DB_PATH.exists():
            if self._conn is not None:
                self._close_connection()
            self._conn = sqlite3.connect(
                DB_PATH,
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def _close_connection(self) -> None:
        """Safely close the database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error as e:
                logger.warning(f"Error closing database connection: {e}")
            finally:
                self._conn = None

    def _init_schema(self) -> None:
        default_freq = RecurrenceFrequency.WEEKS.value
        try:
            self.conn.executescript(f"""  
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    icon TEXT NOT NULL, color TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                    spent_seconds INTEGER DEFAULT 0,
                    estimated_seconds INTEGER DEFAULT {DEFAULT_ESTIMATED_SECONDS},
                    project_id TEXT, due_date DATE, is_done INTEGER DEFAULT 0,
                    recurrent INTEGER DEFAULT 0, recurrence_interval INTEGER DEFAULT 1,
                    recurrence_frequency TEXT DEFAULT '{default_freq}',
                    recurrence_weekdays TEXT DEFAULT '[]', notes TEXT DEFAULT '',
                    sort_order INTEGER DEFAULT 0,
                    recurrence_end_type TEXT DEFAULT 'never',
                    recurrence_end_date DATE
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
            self._migrate_schema()
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error initializing database schema: {e}")
            raise DatabaseError(f"Failed to initialize schema: {e}") from e

    def _migrate_schema(self) -> None:
        """Handle schema migrations for existing databases."""
        try:
            cols = [r[1] for r in self.conn.execute("PRAGMA table_info(tasks)")]
            if "sort_order" not in cols:
                self.conn.execute(
                    "ALTER TABLE tasks ADD COLUMN sort_order INTEGER DEFAULT 0"
                )
            if "recurrence_end_type" not in cols:
                self.conn.execute(
                    "ALTER TABLE tasks ADD COLUMN recurrence_end_type TEXT DEFAULT 'never'"
                )
            if "recurrence_end_date" not in cols:
                self.conn.execute(
                    "ALTER TABLE tasks ADD COLUMN recurrence_end_date DATE"
                )
            tables = [r[0] for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
            if "time_entries" not in tables:
                self.conn.execute("""  
                    CREATE TABLE time_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                    )
                """)
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_time_entries_task ON time_entries(task_id)"
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_time_entries_start ON time_entries(start_time)"
                )
        except sqlite3.Error as e:
            logger.error(f"Error during schema migration: {e}")
            raise DatabaseError(f"Failed to migrate schema: {e}") from e

    def seed_default_data(self) -> None:
        """Insert default seed data after factory reset."""
        try: 
            default_projects = [
                {"id": "personal", "name": "Personal", "icon": "📋", "color": "#2196f3"},
                {"id": "work", "name": "Work", "icon": "💼", "color": "#4caf50"},
            ]
            for project in default_projects:
                self.save_project(project)
 
            from datetime import datetime, timedelta  
            now = datetime.now() 
            
            welcome_task = {
                "id": None,
                "title": "Welcome to Trebnic!",
                "spent_seconds": 1800, 
                "estimated_seconds": 3600,  
                "project_id": "personal",
                "due_date": date.today(),
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
            task_id = self.save_task(welcome_task)
             
            entry1_start = now - timedelta(hours=2, minutes=30) 
            entry1_end = entry1_start + timedelta(minutes=20)  
            self.save_time_entry({
                "id": None,
                "task_id": task_id,
                "start_time": entry1_start.isoformat(),
                "end_time": entry1_end.isoformat(),
            })
             
            entry2_start = now - timedelta(minutes=45)
            entry2_end = entry2_start + timedelta(minutes=10)
            self.save_time_entry({
                "id": None,
                "task_id": task_id,
                "start_time": entry2_start.isoformat(),
                "end_time": entry2_end.isoformat(),
            })
            
        except sqlite3.Error as e:
            logger.error(f"Error seeding default data: {e}")
            raise DatabaseError(f"Failed to seed default data: {e}") from e

    def save_task(self, t: Dict[str, Any]) -> int:
        weekdays = json.dumps(t.get("recurrence_weekdays", []))
        params = (
            t["title"],
            t["spent_seconds"],
            t["estimated_seconds"],
            t["project_id"],
            t["due_date"],
            t.get("is_done", 0),
            t.get("recurrent", 0),
            t.get("recurrence_interval", 1),
            t.get("recurrence_frequency", RecurrenceFrequency.WEEKS.value),
            weekdays,
            t.get("notes", ""),
            t.get("sort_order", 0),
            t.get("recurrence_end_type", "never"),
            t.get("recurrence_end_date"),
        )
        try:
            if t.get("id") is None:
                cur = self.conn.execute(
                    "INSERT INTO tasks "
                    "(title,spent_seconds,estimated_seconds,project_id,"
                    "due_date,is_done,recurrent,recurrence_interval,recurrence_frequency,"
                    "recurrence_weekdays,notes,sort_order,recurrence_end_type,"
                    "recurrence_end_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    params
                )
                self.conn.commit()
                return cur.lastrowid
            self.conn.execute(
                "UPDATE tasks SET title=?,spent_seconds=?,estimated_seconds=?,"
                "project_id=?,due_date=?,is_done=?,recurrent=?,recurrence_interval=?,"
                "recurrence_frequency=?,recurrence_weekdays=?,notes=?,sort_order=?,"
                "recurrence_end_type=?,recurrence_end_date=? WHERE id=?",
                params + (t["id"],)
            )
            self.conn.commit()
            return t["id"]
        except sqlite3.Error as e:
            logger.error(f"Error saving task: {e}")
            raise DatabaseError(f"Failed to save task: {e}") from e

    def delete_task(self, task_id: int) -> None:
        try:
            self.conn.execute("DELETE FROM time_entries WHERE task_id=?", (task_id,))
            self.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            raise DatabaseError(f"Failed to delete task: {e}") from e

    def load_tasks(self) -> List[Dict[str, Any]]:
        try:
            rows = self.conn.execute("SELECT * FROM tasks ORDER BY sort_order, id")
            result = []
            for r in rows:
                task_dict = dict(r)
                task_dict["recurrence_weekdays"] = json.loads(r["recurrence_weekdays"])
                task_dict["recurrence_end_type"] = (
                    r["recurrence_end_type"]
                    if "recurrence_end_type" in r.keys()
                    else "never"
                )
                task_dict["recurrence_end_date"] = (
                    r["recurrence_end_date"]
                    if "recurrence_end_date" in r.keys()
                    else None
                )
                result.append(task_dict)
            return result
        except sqlite3.Error as e:
            logger.error(f"Error loading tasks: {e}")
            raise DatabaseError(f"Failed to load tasks: {e}") from e

    def save_project(self, p: Dict[str, str]) -> None:
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO projects (id,name,icon,color) VALUES (?,?,?,?)",
                (p["id"], p["name"], p["icon"], p["color"])
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error saving project: {e}")
            raise DatabaseError(f"Failed to save project: {e}") from e

    def delete_project(self, project_id: str) -> int:
        try:
            count = self.conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE project_id=?",
                (project_id,)
            ).fetchone()[0]
            self.conn.execute(
                "DELETE FROM time_entries WHERE task_id IN "
                "(SELECT id FROM tasks WHERE project_id=?)",
                (project_id,)
            )
            self.conn.execute("DELETE FROM tasks WHERE project_id=?", (project_id,))
            self.conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            self.conn.commit()
            return count
        except sqlite3.Error as e:
            logger.error(f"Error deleting project {project_id}: {e}")
            raise DatabaseError(f"Failed to delete project: {e}") from e

    def load_projects(self) -> List[Dict[str, str]]:
        try:
            return [dict(r) for r in self.conn.execute("SELECT * FROM projects")]
        except sqlite3.Error as e:
            logger.error(f"Error loading projects: {e}")
            raise DatabaseError(f"Failed to load projects: {e}") from e

    def save_time_entry(self, entry: Dict[str, Any]) -> int:
        """Save a time entry to the database."""
        try:
            if entry.get("id") is None:
                cur = self.conn.execute(
                    "INSERT INTO time_entries (task_id, start_time, end_time) "
                    "VALUES (?, ?, ?)",
                    (entry["task_id"], entry["start_time"], entry["end_time"])
                )
                self.conn.commit()
                return cur.lastrowid
            self.conn.execute(
                "UPDATE time_entries SET task_id=?, start_time=?, end_time=? "
                "WHERE id=?",
                (entry["task_id"], entry["start_time"], entry["end_time"], entry["id"])
            )
            self.conn.commit()
            return entry["id"]
        except sqlite3.Error as e:
            logger.error(f"Error saving time entry: {e}")
            raise DatabaseError(f"Failed to save time entry: {e}") from e

    def load_time_entries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Load time entries from the database, ordered by start time descending."""
        try:
            if limit is not None:
                rows = self.conn.execute(
                    "SELECT * FROM time_entries ORDER BY start_time DESC LIMIT ?",
                    (limit,)
                )
            else:
                rows = self.conn.execute(
                    "SELECT * FROM time_entries ORDER BY start_time DESC"
                )
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error(f"Error loading time entries: {e}")
            raise DatabaseError(f"Failed to load time entries: {e}") from e

    def load_time_entries_for_task(self, task_id: int) -> List[Dict[str, Any]]:
        """Load time entries for a specific task."""
        try:
            return [
                dict(r) for r in self.conn.execute(
                    "SELECT * FROM time_entries WHERE task_id=? ORDER BY start_time DESC",
                    (task_id,)
                )
            ]
        except sqlite3.Error as e:
            logger.error(f"Error loading time entries for task {task_id}: {e}")
            raise DatabaseError(f"Failed to load time entries: {e}") from e

    def load_time_entries_by_date(self, target_date: date) -> List[Dict[str, Any]]:
        """Load time entries for a specific date."""
        try:
            date_str = target_date.isoformat()
            return [
                dict(r) for r in self.conn.execute(
                    "SELECT * FROM time_entries "
                    "WHERE date(start_time) = ? "
                    "ORDER BY start_time ASC",
                    (date_str,)
                )
            ]
        except sqlite3.Error as e:
            logger.error(f"Error loading time entries for date {target_date}: {e}")
            raise DatabaseError(f"Failed to load time entries: {e}") from e

    def delete_time_entry(self, entry_id: int) -> None:
        """Delete a time entry."""
        try:
            self.conn.execute("DELETE FROM time_entries WHERE id=?", (entry_id,))
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error deleting time entry {entry_id}: {e}")
            raise DatabaseError(f"Failed to delete time entry: {e}") from e

    def get_total_tracked_today(self) -> int:
        """Get total tracked seconds for today."""
        try:
            today = date.today().isoformat()
            result = self.conn.execute(
                "SELECT SUM("
                "  CASE WHEN end_time IS NOT NULL THEN "
                "    (julianday(end_time) - julianday(start_time)) * 86400 "
                "  ELSE 0 END"
                ") as total FROM time_entries WHERE date(start_time) = ?",
                (today,)
            ).fetchone()
            return int(result[0] or 0)
        except sqlite3.Error as e:
            logger.error(f"Error getting total tracked today: {e}")
            raise DatabaseError(f"Failed to get total tracked today: {e}") from e

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value. Returns default if not found or on error."""
        try:
            row = self.conn.execute(
                "SELECT value FROM settings WHERE key=?",
                (key,)
            ).fetchone()
            return json.loads(row["value"]) if row else default
        except sqlite3.Error as e:
            logger.warning(f"Error getting setting {key}: {e}")
            return default 

    def set_setting(self, key: str, value: Any) -> None:
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
                (key, json.dumps(value))
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error setting {key}: {e}")
            raise DatabaseError(f"Failed to save setting: {e}") from e

    def clear_all(self) -> None:
        try:
            self.conn.executescript(
                "DELETE FROM time_entries; DELETE FROM tasks; "
                "DELETE FROM projects; DELETE FROM settings;"
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error clearing database: {e}")
            raise DatabaseError(f"Failed to clear database: {e}") from e

    def is_empty(self) -> bool:
        try:
            return self.conn.execute(
                "SELECT COUNT(*) FROM projects"
            ).fetchone()[0] == 0
        except sqlite3.Error as e:
            logger.error(f"Error checking if database is empty: {e}")
            raise DatabaseError(f"Failed to check database: {e}") from e


db = Database()