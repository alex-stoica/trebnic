# Flet async event handlers - learnings

Hard-won lessons from debugging the feedback send button that silently did nothing.

## Bug #2: stale `.env` overrides revoked key seeding

`config.py` calls `load_dotenv()` at import time, loading `.env` into `os.environ`.
The `_seed_email_config()` function detects a revoked DB key and replaces it — but
reads the replacement from `os.getenv()` first, which returns the SAME revoked key
from the stale `.env` file. The revoked key gets written right back.

**Fix**: Check the env var against the revoked set too:
```python
env_key = os.getenv("RESEND_API_KEY", "")
api_key = env_key if env_key and env_key not in _REVOKED_KEYS else _FALLBACK_KEY
```

## Root cause: silent exception swallowing

Flet's `_trigger_event` in `base_control.py` has **no try/except** around event handler calls.
If a sync handler raises any exception, it propagates into an asyncio Task that may never
be retrieved — the exception vanishes silently. No console output, no error, nothing.

```python
# base_control.py:340-344 — NO try/except wrapping this
elif callable(event_handler):
    if get_param_count(event_handler) == 0:
        event_handler()
    else:
        event_handler(e)
```

## Key rules

### 1. Flet natively supports `async def` event handlers

Flet 0.80+ checks `inspect.iscoroutinefunction(handler)` first and **awaits** async handlers.
This is the cleanest approach — no `page.run_task` workaround needed.

```python
# GOOD: Flet detects async handler and awaits it
async def _on_click(self, e: ft.ControlEvent) -> None:
    result = await some_async_operation()
    self.snack.show("Done", COLORS["green"])

# OK: sync handler + page.run_task for simple async work
def _on_click(self, e: ft.ControlEvent) -> None:
    async def _work():
        await db.set_setting("key", "value")
        self.snack.show("Done", COLORS["green"])
    self.page.run_task(_work)
```

### 2. Never call blocking I/O from async context without a thread

`urllib.request.urlopen()` blocks the event loop. Use `loop.run_in_executor()`:

```python
async def _on_click(self, e):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, blocking_http_call, arg1, arg2)
    # Back on event loop — safe to update UI
    self.snack.show("Done")
```

### 3. Never call Flet UI methods from background threads

`self.snack.show()`, `control.update()`, `page.update()` — all must run on Flet's event loop.
Calling them from a `threading.Thread` or `asyncio.to_thread` silently fails.

If you must use threads, schedule UI updates back via `page.run_task()`:
```python
def thread_worker():
    result = blocking_call()
    async def update_ui():
        self.snack.show(result)
    self.page.run_task(update_ui)
```

### 4. Always wrap handlers in try/except

Because Flet swallows exceptions silently:

```python
async def _on_click(self, e):
    try:
        # ... actual logic ...
    except Exception as exc:
        print(f"[ERROR] {exc}")  # at minimum, log to console
        self.snack.show(f"Error: {exc}", COLORS["danger"])
```

### 5. `page.run_task()` signature

```python
page.run_task(handler, *args, **kwargs)  # handler must be a coroutine function
# Internally does: asyncio.run_coroutine_threadsafe(handler(*args, **kwargs), loop)
```

It accepts args! No need for closure wrappers:
```python
# Instead of:
async def _work():
    await do_thing(value)
page.run_task(_work)

# You can do:
page.run_task(do_thing, value)
```

## Failed approaches (don't repeat)

| Approach | Problem |
|----------|---------|
| Sync handler + `asyncio.to_thread` via `page.run_task` | `asyncio.to_thread` inside `run_task` — double async indirection, unreliable |
| Sync handler + `threading.Thread` + `page.run_task` for UI update | Thread works but exception in sync handler before thread start silently swallowed |
| `_send_http` as instance method with snack.show inside | UI calls from background thread silently fail |
| Blocking HTTP directly in async handler (no executor) | Blocks event loop, UI freezes, snack never renders |

## Working approach

```python
async def _on_send_click(self, e: ft.ControlEvent) -> None:
    try:
        # 1. Read values
        message = self._message_field.value or ""
        api_key = await db.get_setting("resend_api_key", "")

        # 2. Validate
        if not message.strip():
            self.snack.show("Enter a message", COLORS["danger"])
            return

        # 3. Show "sending..." snack
        self.snack.show("Sending...", COLORS["accent"])

        # 4. Blocking HTTP in thread pool
        loop = asyncio.get_running_loop()
        error = await loop.run_in_executor(None, send_http, api_key, message)

        # 5. Back on event loop — update UI
        if error is None:
            self.snack.show("Sent!", COLORS["green"])
        else:
            self.snack.show(f"Failed: {error}", COLORS["danger"])
    except Exception as exc:
        print(f"[ERROR] {exc}")
        self.snack.show(f"Error: {exc}", COLORS["danger"])
```
