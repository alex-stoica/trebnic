import sqlite3 
import json 
from datetime import date 
from pathlib import Path 
from typing import Optional, Any, Dict, List 

from config import DEFAULT_ESTIMATED_SECONDS 

DB_PATH = Path("trebnic.db") 

sqlite3.register_adapter(date, lambda d: d.isoformat()) 
sqlite3.register_converter("DATE", lambda s: date.fromisoformat(s.decode()) if s else None) 


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
                try: 
                    self._conn.close() 
                except: 
                    pass 
            self._conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False) 
            self._conn.row_factory = sqlite3.Row 
            self._init_schema() 
        return self._conn 

    def _init_schema(self): 
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
                recurrence_frequency TEXT DEFAULT 'weeks',
                recurrence_weekdays TEXT DEFAULT '[]', notes TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                recurrence_end_type TEXT DEFAULT 'never',
                recurrence_end_date DATE
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(is_done);
        """)  
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(tasks)")] 
        if "sort_order" not in cols: 
            self.conn.execute("ALTER TABLE tasks ADD COLUMN sort_order INTEGER DEFAULT 0") 
        if "recurrence_end_type" not in cols: 
            self.conn.execute("ALTER TABLE tasks ADD COLUMN recurrence_end_type TEXT DEFAULT 'never'")  
        if "recurrence_end_date" not in cols:  
            self.conn.execute("ALTER TABLE tasks ADD COLUMN recurrence_end_date DATE")  
        self.conn.commit() 

    def save_task(self, t: Dict) -> int: 
        weekdays = json.dumps(t.get("recurrence_weekdays", [])) 
        params = (t["title"], t["spent_seconds"], t["estimated_seconds"], t["project_id"], 
                  t["due_date"], t.get("is_done", 0), t.get("recurrent", 0), 
                  t.get("recurrence_interval", 1), t.get("recurrence_frequency", "weeks"), 
                  weekdays, t.get("notes", ""), t.get("sort_order", 0),
                  t.get("recurrence_end_type", "never"), t.get("recurrence_end_date"))  
        if t.get("id") is None: 
            cur = self.conn.execute( 
                "INSERT INTO tasks (title,spent_seconds,estimated_seconds,project_id," 
                "due_date,is_done,recurrent,recurrence_interval,recurrence_frequency," 
                "recurrence_weekdays,notes,sort_order,recurrence_end_type,recurrence_end_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", params) 
            self.conn.commit() 
            return cur.lastrowid 
        self.conn.execute( 
            "UPDATE tasks SET title=?,spent_seconds=?,estimated_seconds=?,project_id=?," 
            "due_date=?,is_done=?,recurrent=?,recurrence_interval=?,recurrence_frequency=?," 
            "recurrence_weekdays=?,notes=?,sort_order=?,recurrence_end_type=?,recurrence_end_date=? WHERE id=?", params + (t["id"],)) 
        self.conn.commit() 
        return t["id"] 

    def delete_task(self, task_id: int): 
        self.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,)) 
        self.conn.commit() 

    def load_tasks(self) -> List[Dict]: 
        rows = self.conn.execute("SELECT * FROM tasks ORDER BY sort_order, id") 
        return [{**dict(r), "recurrence_weekdays": json.loads(r["recurrence_weekdays"]),
                 "recurrence_end_type": r["recurrence_end_type"] if "recurrence_end_type" in r.keys() else "never", 
                 "recurrence_end_date": r["recurrence_end_date"] if "recurrence_end_date" in r.keys() else None} for r in rows]  

    def save_project(self, p: Dict): 
        self.conn.execute("INSERT OR REPLACE INTO projects (id,name,icon,color) VALUES (?,?,?,?)", 
                          (p["id"], p["name"], p["icon"], p["color"])) 
        self.conn.commit() 

    def delete_project(self, project_id: str) -> int: 
        count = self.conn.execute("SELECT COUNT(*) FROM tasks WHERE project_id=?", (project_id,)).fetchone()[0] 
        self.conn.execute("DELETE FROM tasks WHERE project_id=?", (project_id,)) 
        self.conn.execute("DELETE FROM projects WHERE id=?", (project_id,)) 
        self.conn.commit() 
        return count 

    def load_projects(self) -> List[Dict]: 
        return [dict(r) for r in self.conn.execute("SELECT * FROM projects")] 

    def get_setting(self, key: str, default: Any = None) -> Any: 
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone() 
        return json.loads(row["value"]) if row else default 

    def set_setting(self, key: str, value: Any): 
        self.conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, json.dumps(value))) 
        self.conn.commit() 

    def clear_all(self): 
        self.conn.executescript("DELETE FROM tasks; DELETE FROM projects; DELETE FROM settings;") 
        self.conn.commit() 

    def is_empty(self) -> bool: 
        return self.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0 


db = Database()