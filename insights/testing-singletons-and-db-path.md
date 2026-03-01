# Testing singletons and DB path pitfalls

## Singleton reset breaks module-level imports

**Problem**: `Database.reset_instance()` sets `cls._instance = None`, but every module that did `from database import db` at import time still holds a reference to the **old** object. Calling `Database()` after reset creates a *new* singleton, but the module-level `db` in `database.py`, `logic.py`, etc. still points to the old one. The old object has `_conn = None` (from reset) and tries to open a fresh `:memory:` DB, but never runs `init_db()` on it because the new singleton is a different object.

**Fix**: Don't call `reset_instance()`. Instead, reset internal state on the existing module-level singletons:

```python
from database import db
from events import event_bus
from registry import registry

await db.close()
db._initialized = False
db._conn_lock = None
event_bus.clear()
registry.clear()
```

This preserves the object identity that all modules already reference.

**Also needed**: a session-scoped event loop fixture, because aiosqlite connections are tied to the event loop they were created on. If pytest-asyncio creates a new loop per test (the default), the second test's `_ensure_connection()` creates a connection on a different loop and things break.

```python
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

## Relative DB path resolves per working directory

**Problem**: `DB_PATH = Path("trebnic.db")` is relative. Where the DB file lands depends on CWD:

- `cd trebnic/trebnic && python seed.py` → creates `trebnic/trebnic/trebnic.db`
- `cd trebnic && flet run trebnic/main.py` → reads `trebnic/trebnic.db`

Two different files. The app shows stale data because it reads the old DB at the project root.

**Fix**: When running scripts that use `bootstrap()`, always run from the same directory that `flet run` uses (the project root), and set `sys.path` to include the package:

```python
sys.path.insert(0, "trebnic")
from core import bootstrap
```

Or use `bootstrap(db_path=Path("/absolute/path/trebnic.db"))` to be explicit.
