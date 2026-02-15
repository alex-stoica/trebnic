# Async patterns in Flet

## The silent failure problem

Flet's `_trigger_event` has no try/except around handler calls. If a sync handler raises, the exception propagates into an asyncio Task that's never retrieved — it vanishes silently.

Calling an async function without `await` also fails silently — Python returns a coroutine object that gets discarded. No warning, no error.

## Rules

### 1. Flet 0.80+ natively supports `async def` handlers

Flet checks `inspect.iscoroutinefunction(handler)` and awaits it. This is the cleanest approach:

```python
async def _on_click(self, e: ft.ControlEvent) -> None:
    result = await some_async_operation()
    self.snack.show("Done", COLORS["green"])
```

### 2. Sync handler + `page.run_task()` also works

```python
def save(e):
    async def _save():
        await self.service.rename_task(task, name)
        self.snack.show("Saved")
        close(e)
    self.page.run_task(_save)
```

`page.run_task()` accepts args directly — no closure needed:
```python
page.run_task(do_thing, value)  # instead of wrapping in async def
```

### 3. Never call blocking I/O from async context

Use `loop.run_in_executor()`:
```python
async def _on_click(self, e):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, blocking_http_call, arg1)
    self.snack.show("Done")  # back on event loop, safe to update UI
```

### 4. Never call UI methods from background threads

`snack.show()`, `control.update()`, `page.update()` must run on Flet's event loop. From threads, schedule back via `page.run_task()`.

### 5. Always wrap handlers in try/except

Because Flet swallows exceptions silently:
```python
async def _on_click(self, e):
    try:
        ...
    except Exception as exc:
        print(f"[ERROR] {exc}")
        self.snack.show(f"Error: {exc}", COLORS["danger"])
```

## Stale `.env` bug

`load_dotenv()` at import time loads `.env` into `os.environ`. If a function detects a revoked key and tries to replace it from `os.getenv()`, it reads the same stale value. Always check env vars against known-bad values before using them.
