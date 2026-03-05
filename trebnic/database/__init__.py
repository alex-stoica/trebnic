"""Database package - async SQLite with mixin-based composition.

Public API is unchanged: ``from database import db, DatabaseError`` continues
to work exactly as before the refactor.
"""
from pathlib import Path

_DEFAULT_DB_PATH = Path("trebnic.db")
DB_PATH: Path = _DEFAULT_DB_PATH

# Re-export helpers so consumer code doesn't need to change imports
from database.helpers import (  # noqa: E402
    DatabaseError,
    LockedDataWriteError,
    LOCKED_PLACEHOLDER,
    _encrypt_field,
    _decrypt_field,
    _is_encrypted,
)
from database.core import DatabaseCore  # noqa: E402
from database.tasks import TasksMixin  # noqa: E402
from database.records import RecordsMixin  # noqa: E402
from database.notifications import NotificationsMixin  # noqa: E402
from database.data_ops import DataOpsMixin  # noqa: E402


class Database(DatabaseCore, TasksMixin, RecordsMixin, NotificationsMixin, DataOpsMixin):
    """Composed database class combining all mixins."""
    pass


def configure_db_path(path: Path) -> None:
    """Set a custom database path before any connection is opened.

    Raises:
        RuntimeError: If the database connection is already open.
    """
    global DB_PATH
    if Database._instance is not None and Database._instance._conn is not None:
        raise RuntimeError(
            "Cannot change DB_PATH after a database connection has been opened. "
            "Call configure_db_path() before any database operations."
        )
    DB_PATH = path


db = Database()
