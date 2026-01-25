# Dual-API Bloat Refactoring

## Problem
TaskService had a "shadow" version of every method - both sync (`method()`) and async (`method_async()`) versions. This doubled the surface area for bugs and created maintenance burden.

## Solution
Consolidated to a single async API with explicit sync bridging where needed.

### Key Changes

1. **Removed all sync wrapper methods** - No more `method()` + `method_async()` pairs
2. **Renamed `_schedule_async` to `run_sync`** - Explicit name for the sync bridge utility
3. **All data operations are now async** - Single implementation per operation
4. **Kept sync only for**:
   - `load_state()` - static method for app startup before event loop exists
   - Pure in-memory checks (`validate_project_name`, `task_name_exists`)

### Call Site Patterns

**Async contexts (preferred):**
```python
# In async handlers or methods
await self.service.add_task(title)
await self.service.persist_task(task)
```

**Sync event handlers:**
```python
def on_click(e):
    async def _async_work():
        await self.service.delete_task(task)
        self.refresh()
    self.page.run_task(_async_work)
```

**Callbacks that must be sync (e.g., TimerService):**
```python
def _save_time_entry_sync(self, entry: TimeEntry) -> int:
    return self.service.run_sync(self.service.save_time_entry(entry))
```

### Code Reduction
- Before: ~630 lines in logic.py
- After: ~482 lines
- Eliminated ~25 duplicate method definitions

### Files Modified
- `services/logic.py` - Core refactoring
- `app.py` - Async handlers with `page.run_task()`
- `ui/controller.py` - Method name updates
- `ui/timer_controller.py` - Sync wrapper callbacks for TimerService
- `ui/pages/task_view.py` - Method name updates
- `ui/pages/time_entries_view.py` - Async handlers
- `ui/pages/profile_view.py` - Async handlers
- `ui/dialogs/task_dialogs.py` - Async handlers
- `ui/dialogs/project_dialogs.py` - Async handlers

### Key Learnings
1. Flet natively supports async event handlers - use `page.run_task()` for async work from sync callbacks
2. Keep `run_sync()` as explicit bridge for the few places that truly need sync (cleanup, timer callbacks)
3. Internal async methods can keep `_async` suffix to distinguish from sync wrappers in the same class
4. Don't create unnecessary abstractions - simple `page.run_task(async_fn)` pattern is clear and works well
