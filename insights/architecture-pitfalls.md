# Architecture Pitfalls and Fixes

Documenting five critical issues discovered in the codebase and their solutions.

## 1. Encryption Breaks SQL-Based Queries

**Problem**: Methods like `delete_recurring_tasks_by_title` used SQL WHERE clauses to match titles, but titles are encrypted with AES-GCM using random nonces. The same plaintext produces different ciphertext each time, so SQL matching always fails.

**Solution**: Fetch all candidates from DB, decrypt in memory, filter by matching decrypted values, then delete by ID.

```python
# WRONG - encrypted titles won't match plaintext
SELECT id FROM tasks WHERE title = ? AND recurrent = 1

# CORRECT - fetch all, decrypt in Python, then filter
async with conn.execute("SELECT id, title FROM tasks WHERE recurrent = 1") as cursor:
    rows = [dict(row) async for row in cursor]

for row in rows:
    decrypted_title = _decrypt_field(row.get("title", ""))
    if decrypted_title == title:
        task_ids.append(row["id"])
```

**Key Learning**: Any SQL query on encrypted fields must be converted to fetch-decrypt-filter pattern.

## 2. Sync/Async Bridging is Dangerous

**Problem**: `asyncio.run()` creates a new event loop, which conflicts with:
- Existing running loops (RuntimeError)
- Database connections bound to different loops
- Flet's page.loop

**Solution**: Prioritize using page.loop with `run_coroutine_threadsafe`:

```python
def run_sync(self, coro, wait: bool = True):
    # BEST: use page's event loop
    if self._page is not None:
        future = asyncio.run_coroutine_threadsafe(coro, self._page.loop)
        return future.result(timeout=30.0)

    # FALLBACK: only during initial startup before page exists
    return asyncio.run(coro)
```

**Key Learning**: Always prefer `page.run_task()` or `await` in async contexts. Reserve `asyncio.run()` only for initial app startup.

## 3. EventBus Weak References Drop Lambdas

**Problem**: `weakref` to lambdas/temporary functions causes immediate garbage collection:

```python
# WRONG - lambda gets GC'd immediately, subscription silently stops working
event_bus.subscribe(AppEvent.REFRESH_UI, lambda data: self.refresh())
```

**Solution**: Added `strong=True` parameter and logging:

```python
# CORRECT - bound method (preferred)
event_bus.subscribe(AppEvent.REFRESH_UI, self.on_refresh)

# CORRECT - strong reference (remember to unsubscribe!)
self._sub = event_bus.subscribe(AppEvent.REFRESH_UI, lambda d: ..., strong=True)
```

**Key Learning**: Weak references are a foot-gun with closures. Always use bound methods or explicitly opt-in to strong refs.

## 4. State Reload Doesn't Update UI References

**Problem**: After `reload_state()`, the state containers have new Task objects, but UI components (TaskTile) might still hold references to old objects with encrypted data.

**Solution**: Emit `REFRESH_UI` event after reload, and ensure UI rebuilds with fresh data:

```python
async def reload_state_async(self) -> None:
    # ... reload data ...

    # CRITICAL: notify UI to rebuild
    event_bus.emit(AppEvent.REFRESH_UI)
```

**Key Learning**: Mutable shared state requires explicit notification when updated. The UI must rebuild, not just re-render.

## 5. DatePicker Overlay Memory Leak

**Problem**: Each dialog instance creates a new `ft.DatePicker` and appends it to `page.overlay`. If dialogs are recreated, old pickers accumulate.

**Solution**: Use class-level shared pickers:

```python
class TaskDialogs:
    # Shared across all instances
    _shared_date_picker: Optional[ft.DatePicker] = None
    _shared_picker_page: Optional[ft.Page] = None

    def _ensure_date_picker(self) -> ft.DatePicker:
        cls = TaskDialogs
        if cls._shared_date_picker is None or cls._shared_picker_page != self.page:
            # Remove old picker if page changed
            if cls._shared_date_picker is not None:
                try:
                    cls._shared_picker_page.overlay.remove(cls._shared_date_picker)
                except ValueError:
                    pass
            # Create new picker
            cls._shared_date_picker = ft.DatePicker(...)
            self.page.overlay.append(cls._shared_date_picker)
            cls._shared_picker_page = self.page
        return cls._shared_date_picker
```

**Key Learning**: Flet's overlay is a list that persists for the session. Always reuse or explicitly remove overlay controls.

## General Principles

1. **Encryption changes query patterns** - can't use SQL WHERE on encrypted fields
2. **Event loops are singleton-ish** - don't create new ones after app starts
3. **Weak refs need strong owners** - lambdas need explicit storage
4. **State updates need UI signals** - mutable state changes are invisible without events
5. **Overlays accumulate** - treat overlay controls as persistent resources to manage
