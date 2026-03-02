# Flet ReorderableListView learnings

## Working solution

```python
def _on_reorder(self, e: ft.OnReorderEvent) -> None:
    old_idx, new_idx = e.old_index, e.new_index

    # Validate indices
    if old_idx < 0 or old_idx >= len(controls): return
    if new_idx < 0 or new_idx > len(controls): return
    if old_idx == new_idx: return

    # 1. Get task IDs from current UI order
    ui_task_ids = [ctrl.data for ctrl in self.task_list.controls]

    # 2. Apply reorder to get desired order
    moved_id = ui_task_ids.pop(old_idx)
    ui_task_ids.insert(new_idx, moved_id)

    # 3. Get fresh tasks from DB
    filtered, _ = self.service.get_filtered_tasks()
    task_map = {t.id: t for t in filtered}

    # 4. Assign sort_order based on desired UI order
    for i, task_id in enumerate(ui_task_ids):
        if task_id in task_map:
            task_map[task_id].sort_order = i

    # 5. Persist to DB (blocking)
    self.service.persist_reordered_tasks(list(task_map.values()))

    # 6. Rebuild UI from DB
    self.refresh()
```

## Key principles

1. **Store task ID on controls**: Use `data=task.id` on `Container` wrappers inside `ReorderableListView`.
2. **UI state is source of truth for order**: Read current UI order via task IDs, then sync DB to match.
3. **Use task IDs for lookups**, not Python object identity (`task in list`).
4. **Fresh data for persistence**: Always fetch fresh from DB before persisting to avoid overwriting stale values.
5. **No index adjustment needed**: Flet reports final position, not insert-before-removal position.
6. **Rebuild is safer than manipulate**: Persist and rebuild from DB rather than keeping UI controls in sync manually.
