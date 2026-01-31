# Flet 0.28.x to 0.80.x migration guide

API breaking changes encountered when upgrading from flet 0.28.x to 0.80.x.

## Changes made

| # | Issue | Fix |
|---|-------|-----|
| 1 | `ft.FilePickerResultEvent` doesn't exist | Removed type annotation in `profile_view.py` and `stats_view.py` |
| 2 | `asyncio.run()` cannot be called from a running event loop | Flet 0.80.x runs its own event loop. Fixed `load_state()` in `logic.py` to use ThreadPoolExecutor when loop already running |
| 3 | `ft.alignment.center` doesn't exist | Replaced all `ft.alignment.*` with `ft.Alignment(x, y)` tuples across all files |
| 4 | Sed replacement corrupted `ft.alignment.center_right` | Fixed manually - be careful with batch replacements |
| 5 | `FilePicker(on_result=...)` removed | Changed to async API: `page.services.append()` + `await file_picker.pick_files()` |
| 6 | `PopupMenuItem(text=...)` removed | Changed to `content=` parameter in `app.py` |
| 7 | `ReorderableDraggable` removed | Add controls directly to `ReorderableListView.controls`. Use Container with `data=` for identification |
| 8 | `ft.padding.only/symmetric` deprecated | Changed to `ft.Padding.only/symmetric` across all files |
| 9 | `ft.app(target=main)` deprecated | Changed to `ft.run(main)` in `main.py` |
| 10 | `ft.margin.only` deprecated | Changed to `ft.Margin.only` across all files |
| 11 | `ft.border.all/only` deprecated | Changed to `ft.Border.all/only` across all files |
| 12 | `ft.ImageFit` removed | Changed to `ft.BoxFit` in `profile_view.py` |
| 13 | `page.open(dialog)` / `page.close(dialog)` removed | Changed to `page.show_dialog()` / `page.pop_dialog()` |
| 14 | `ft.ElevatedButton` deprecated | Changed to `ft.Button` across all files |
| 15 | `ft.border_radius.only` deprecated | Changed to `ft.BorderRadius.only` |
| 16 | Gesture events `local_x`/`local_y` removed | Changed to `local_position.x`/`local_position.y` in `duration_knob.py` |
| 17 | `Dropdown(on_change=...)` removed | Changed to `on_select=` in `task_dialogs.py` |
| 18 | `page.run_task` requires coroutine function, not object | Changed `run_task(func())` to `run_task(func)` in `timer.py` |
| 19 | Multiple `page.run_task()` calls execute in parallel | Combined sequential async operations into single function in `app.py` |

---

## API reference

### FilePicker (major change)
Old (0.28.x):
```python
file_picker = ft.FilePicker(on_result=callback)
page.overlay.append(file_picker)
file_picker.pick_files(...)  # result comes via callback
```

New (0.80.x):
```python
file_picker = ft.FilePicker()
page.services.append(file_picker)
files = await file_picker.pick_files(...)  # result returned directly
```

### App entry point
```python
# Old
ft.app(target=main)

# New
ft.run(main)
```

### Dialog API
```python
# Old
page.open(dialog)
page.close(dialog)

# New
page.show_dialog(dialog)
page.pop_dialog()  # closes topmost dialog, no argument needed
```

### page.run_task
Now requires a coroutine **function**, not a coroutine object:
```python
# Old - worked with coroutine objects
page.run_task(my_async_func())

# New - requires the function itself
page.run_task(my_async_func)
```

### Async cleanup ordering
Multiple `page.run_task()` calls may execute in parallel. Combine sequential operations:
```python
# Old (broken - parallel execution)
page.run_task(cleanup_notifications)  # may run after db closes!
page.run_task(close_db)

# New (correct - sequential execution)
async def cleanup_all() -> None:
    await notification_service.cleanup()
    await db.close()

page.run_task(cleanup_all)
```

### Gesture events (TapEvent, DragUpdateEvent)
```python
# Old
e.local_x, e.local_y
e.global_x, e.global_y

# New
e.local_position.x, e.local_position.y
e.global_position.x, e.global_position.y
```

### Dropdown
```python
# Old
ft.Dropdown(on_change=callback)

# New
ft.Dropdown(on_select=callback)
```

### PopupMenuItem
```python
# Old
ft.PopupMenuItem(text="Label")

# New
ft.PopupMenuItem(content="Label")
```

### ReorderableListView
```python
# Old
ft.ReorderableDraggable(index=i, content=my_control, data=my_id)

# New - add controls directly, wrap in Container if you need data property
ft.Container(content=my_control, data=my_id)
```

### ImageFit enum renamed
```python
# Old
ft.ImageFit.COVER

# New
ft.BoxFit.COVER
```

---

## Deprecation warnings (will break in future versions)

### Padding helpers (breaks in 0.83.x)
- `ft.padding.only(...)` → `ft.Padding.only(...)`
- `ft.padding.symmetric(...)` → `ft.Padding.symmetric(...)`

### Margin helpers (breaks in 0.83.x)
- `ft.margin.only(...)` → `ft.Margin.only(...)`
- `ft.margin.symmetric(...)` → `ft.Margin.symmetric(...)`

### Border helpers (breaks in 0.83.x)
- `ft.border.all(...)` → `ft.Border.all(...)`
- `ft.border.only(...)` → `ft.Border.only(...)`

### BorderRadius helpers (breaks in 0.83.x)
- `ft.border_radius.only(...)` → `ft.BorderRadius.only(...)`

### ElevatedButton (removed in 1.0)
- `ft.ElevatedButton(...)` → `ft.Button(...)`

---

## Alignment API reference

Old syntax → New syntax:
- `ft.alignment.center` → `ft.Alignment(0, 0)`
- `ft.alignment.center_right` → `ft.Alignment(1, 0)`
- `ft.alignment.center_left` → `ft.Alignment(-1, 0)`
- `ft.alignment.top_center` → `ft.Alignment(0, -1)`
- `ft.alignment.bottom_center` → `ft.Alignment(0, 1)`
- `ft.alignment.top_left` → `ft.Alignment(-1, -1)`
- `ft.alignment.top_right` → `ft.Alignment(1, -1)`
- `ft.alignment.bottom_left` → `ft.Alignment(-1, 1)`
- `ft.alignment.bottom_right` → `ft.Alignment(1, 1)`

---

## Lessons learned

- Sed batch replacements can corrupt code when patterns overlap (e.g., `center` matching inside `center_right`). Do targeted manual fixes instead.
- When upgrading major versions, test incrementally rather than all at once.
- Check deprecation warnings early - they become errors in future versions.
