"""Schema-migration tests against a hand-built pre-completed_at database.

These use a temp FILE database (not the shared :memory: `services` fixture) because
the whole point is to exercise the upgrade path on an OLD on-disk schema. Each test
resets the db singleton in a finally block so it does not leak into other tests.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import database as db_module
from database import db

# tasks table as it existed BEFORE completed_at, with NO time_entries table at all
# (the oldest shape, to also exercise the "time_entries created during migrate" branch).
_OLD_SCHEMA = """
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    spent_seconds INTEGER DEFAULT 0, estimated_seconds INTEGER DEFAULT 900,
    project_id TEXT, due_date TEXT, is_done INTEGER DEFAULT 0,
    recurrent INTEGER DEFAULT 0, recurrence_interval INTEGER DEFAULT 1,
    recurrence_frequency TEXT DEFAULT 'weeks', recurrence_weekdays TEXT DEFAULT '[]',
    notes TEXT DEFAULT '', sort_order INTEGER DEFAULT 0,
    recurrence_end_type TEXT DEFAULT 'never', recurrence_end_date TEXT,
    is_draft INTEGER DEFAULT 0
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _make_old_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(_OLD_SCHEMA)
    # Legacy completed task: spent recorded but NO time entries exist for it.
    con.execute(
        "INSERT INTO tasks (title, spent_seconds, is_done, due_date) VALUES (?, ?, 1, ?)",
        ("Legacy done", 600, "2026-01-05"),
    )
    con.commit()
    con.close()


async def _reset_singleton_to_memory() -> None:
    await db.close()
    db._initialized = False
    db._conn_lock = None
    db_module.DB_PATH = Path(":memory:")


async def test_migration_adds_completed_at_and_preserves_entry_less_spent(tmp_path):
    await db.close()
    db._initialized = False
    db._conn_lock = None
    old = tmp_path / "old.db"
    _make_old_db(old)
    db_module.DB_PATH = old
    try:
        await db.init_db()

        row = await db.load_task_by_id(1)
        assert "completed_at" in row  # column added by migration
        # Entry-less legacy spent must be PRESERVED, not recomputed to 0...
        assert row["spent_seconds"] == 600
        # ...by synthesizing one backing entry so it becomes canonical.
        entries = await db.load_time_entries_for_task(1)
        assert len(entries) == 1
        dur = int(
            (datetime.fromisoformat(entries[0]["end_time"])
             - datetime.fromisoformat(entries[0]["start_time"])).total_seconds()
        )
        assert dur == 600
    finally:
        await _reset_singleton_to_memory()


async def test_migration_is_idempotent(tmp_path):
    """Running init_db twice must not double-synthesize or change totals."""
    await db.close()
    db._initialized = False
    db._conn_lock = None
    old = tmp_path / "old.db"
    _make_old_db(old)
    db_module.DB_PATH = old
    try:
        await db.init_db()
        # Force a second migration pass on the same file.
        db._initialized = False
        await db.init_db()

        row = await db.load_task_by_id(1)
        assert row["spent_seconds"] == 600
        entries = await db.load_time_entries_for_task(1)
        assert len(entries) == 1  # not duplicated by a second reconcile
    finally:
        await _reset_singleton_to_memory()
