# Dual-API Bloat Refactoring

## Problem
TaskService had a "shadow" version of every method - both sync (`method()`) and async (`method_async()`) versions. This doubled the surface area for bugs and created maintenance burden.

## Solution
Consolidated to a single async API with explicit sync bridging where needed.

### Key Changes

1. **Removed all sync wrapper methods** - No more `method()` + `method_async()` pairs
2. **All data operations are now async** - Single implementation per operation
3. **Sync bridging uses `page.run_task()`** - No custom `run_sync` utility; Flet's built-in method handles scheduling async work from sync contexts
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
# Use page.run_task to schedule async work from sync context
async def save_orphaned_entry():
    await self.timer_svc._time_entry_svc.save_time_entry(entry)
self.page.run_task(save_orphaned_entry)
```

### Code Reduction
- Before: ~630 lines in logic.py
- After: ~498 lines (as of 2026-02)
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
1. Flet natively supports async event handlers — use `async def` handlers directly or `page.run_task()` from sync callbacks
2. No custom sync bridge needed — `page.run_task(async_fn)` handles all sync-to-async bridging
3. Don't create unnecessary abstractions — simple `page.run_task(async_fn)` pattern is clear and works well
