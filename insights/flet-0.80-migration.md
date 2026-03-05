# Flet migration guide

## Changes summary

| # | Issue | Fix |
|---|-------|-----|
| 1 | `ft.FilePickerResultEvent` doesn't exist | Removed type annotation |
| 2 | `asyncio.run()` cannot be called from a running event loop | Use ThreadPoolExecutor when loop already running |
| 3 | `ft.alignment.center` doesn't exist | Use `ft.Alignment(x, y)` tuples |
| 4 | `FilePicker(on_result=...)` removed | Async API: `page.services.append()` + `await file_picker.pick_files()` |
| 5 | `PopupMenuItem(text=...)` removed | Use `content=` parameter |
| 6 | `ReorderableDraggable` removed | Add controls directly to `ReorderableListView.controls` |
| 7 | `ft.padding.only/symmetric` deprecated | Use `ft.Padding.only/symmetric` |
| 8 | `ft.app(target=main)` deprecated | Use `ft.run(main)` |
| 9 | `ft.margin.only` deprecated | Use `ft.Margin.only` |
| 10 | `ft.border.all/only` deprecated | Use `ft.Border.all/only` |
| 11 | `ft.ImageFit` removed | Use `ft.BoxFit` |
| 12 | `page.open(dialog)` / `page.close(dialog)` removed | Use `page.show_dialog()` / `page.pop_dialog()` |
| 13 | `ft.ElevatedButton` deprecated | Use `ft.Button` |
| 14 | `ft.border_radius.only` deprecated | Use `ft.BorderRadius.only` |
| 15 | `Dropdown(on_change=...)` removed | Use `on_select=` |
| 16 | `page.run_task` requires coroutine function, not object | Pass `func` not `func()` |
| 17 | Multiple `page.run_task()` calls execute in parallel | Combine sequential async ops into single function |

---

## API reference

### FilePicker
```python
# Old
file_picker = ft.FilePicker(on_result=callback)
page.overlay.append(file_picker)
file_picker.pick_files(...)

# New
file_picker = ft.FilePicker()
page.services.append(file_picker)
files = await file_picker.pick_files(...)
```

### Dialog API
```python
# Old
page.open(dialog) / page.close(dialog)

# New
page.show_dialog(dialog) / page.pop_dialog()
```

### Drawer API
```python
page.drawer = drawer  # attach first
page.run_task(page.show_drawer)
page.run_task(page.close_drawer)
# Or in async context: await page.show_drawer() / await page.close_drawer()
```
`drawer.open = True/False` no longer works.

### page.run_task
```python
# Requires coroutine function, not coroutine object
page.run_task(my_async_func)          # RIGHT
page.run_task(my_async_func())        # WRONG — coroutine object
page.run_task(self._tick_loop())      # WRONG — silently swallowed TypeError
page.run_task(self._tick_loop)        # RIGHT

# With arguments, wrap in closure:
async def wrapper() -> None:
    await my_async_func(arg1, arg2)
page.run_task(wrapper)
```

### Async cleanup ordering
```python
# Multiple run_task calls execute in parallel — combine sequential ops:
async def cleanup_all() -> None:
    await notification_service.cleanup()
    await db.close()
page.run_task(cleanup_all)
```

### Other renames
```python
ft.Dropdown(on_select=callback)           # was on_change
ft.PopupMenuItem(content="Label")         # was text=
ft.Container(content=ctrl, data=my_id)    # replaces ReorderableDraggable
ft.BoxFit.COVER                           # was ft.ImageFit.COVER
```

### Alignment
```python
ft.Alignment(0, 0)    # center
ft.Alignment(1, 0)    # center_right
ft.Alignment(-1, 0)   # center_left
ft.Alignment(0, -1)   # top_center
ft.Alignment(0, 1)    # bottom_center
```

---

## 0.80 → 0.81 bump (Feb 2026)

Bumped minimum to `flet>=0.81.0` in `pyproject.toml`.

No API changes required — all 0.80 code is compatible with 0.81.

## 0.81 → 0.82 bump (Mar 2026)

Bumped to `flet>=0.82.0`. Requires Flutter SDK 3.41.4 (auto-downloaded on first build).

Breaking changes in 0.82: ad controls refactored (InterstitialAd → Service, BannerAd → LayoutControl). Not relevant to Trebnic.

No API changes required for Trebnic — all 0.81 code is compatible with 0.82.
