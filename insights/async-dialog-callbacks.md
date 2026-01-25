# Async Dialog Callbacks Pattern

## The Problem

Dialog save handlers that call async service methods **must** use `page.run_task()`. Otherwise:

```python
# WRONG - coroutine is created but never awaited
def save(e):
    self.service.rename_task(task, name)  # Returns coroutine, does nothing!
    self.snack.show("Saved")  # Shows message but DB unchanged
```

The `rename_task()` returns a coroutine object that Python immediately discards. The database operation never executes, but the UI updates as if it did.

## The Solution

Wrap async calls in `page.run_task()`:

```python
# CORRECT - coroutine is properly scheduled
def save(e):
    async def _save():
        await self.service.rename_task(task, name)
        self.snack.show("Saved")
        close(e)
    self.page.run_task(_save)
```

## Why This Happens

1. Flet callbacks are synchronous by default
2. Python doesn't error when you call an async function without `await` - it just returns a coroutine
3. No warning, no error, silent failure
4. Memory-only changes appear to work until app restart

## Affected Patterns

Any dialog that:
- Calls `service.rename_task()`, `service.set_task_due_date()`, `service.set_task_notes()`, etc.
- Calls `service.persist_task()`, `service.assign_project()`, etc.
- Any method in `TaskService` that's marked `async def`

## Detection

Look for service method calls in dialog callbacks that aren't wrapped in:
- `async def` + `await`
- `page.run_task()`
- `service.run_sync()` (deprecated pattern)

## Correct Patterns by Context

### Dialog callbacks (most common)
```python
def save(e):
    async def _save():
        await self.service.some_async_method()
        close(e)
    self.page.run_task(_save)
```

### Event handlers in components
```python
def on_click(e):
    async def _handle():
        await self.service.some_async_method()
        self.page.update()
    self.page.run_task(_handle)
```

### Already in async context
```python
async def handle_something():
    await self.service.some_async_method()  # Direct await is fine
```
