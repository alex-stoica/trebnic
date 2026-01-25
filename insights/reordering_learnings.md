# Flet ReorderableListView: Deep Dive & Learnings

## The Core Problem

Flet's `ReorderableListView` maintains internal state that can desync from your data model. This causes seemingly random behavior where:
- Reorders work sometimes but not others
- Tasks "snap back" to original positions
- Data gets corrupted (e.g., project assignments lost)

## What Went Wrong (Chronologically)

### Issue 1: Stale Object References
**Symptom**: After reordering, all projects got unassigned from tasks.

**Root Cause**: The code was iterating over `self.state.tasks` (loaded once at startup) and persisting ALL of them to DB. But these stale objects had old/null values for fields like `project_id`.

**Fix**: Always work with fresh data from DB via `get_filtered_tasks()` when persisting.

### Issue 2: Wrong Index Adjustment
**Symptom**: Moving task from position 0 to 1 did nothing (task stayed at 0).

**Root Cause**: Incorrect assumption about Flet's index convention. The code applied `new_idx -= 1` when `old_idx < new_idx`, but Flet reports the **final desired position**, not the insert-before-removal position.

```python
# WRONG - causes no-op when moving from 0 to 1
adjusted_new_idx = new_idx
if old_idx < new_idx:
    adjusted_new_idx -= 1  # 1 - 1 = 0, item goes back to position 0!

# CORRECT - use new_idx directly
list.insert(new_idx, list.pop(old_idx))
```

### Issue 3: UI/DB Order Divergence
**Symptom**: After several reorders, some operations would "revert" the order.

**Root Cause**: We were manipulating both the UI controls AND the DB separately. If they ever got out of sync (due to timing, failed persistence, etc.), subsequent reorders would apply incorrect indices.

**Fix**: Calculate the desired order from current UI state, then persist that exact order to DB, then rebuild UI from DB.

### Issue 4: Flet Internal State Conflicts (Issue #5093)
**Symptom**: Calling `refresh()` after reorder reverted the visual order.

**Root Cause**: Flet's ReorderableListView tracks item positions internally. If you rebuild controls while Flet has cached state, it can "forget" the current indices.

**Initial Workaround**: Manipulate `task_list.controls` directly (pop/insert) instead of calling refresh.

**Better Solution**: Persist to DB immediately, then call refresh to rebuild from DB. Since we create NEW draggable objects each time, Flet's stale cache is irrelevant.

## The Final Working Solution

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

## Key Principles

1. **Store task ID on draggables**: Use `data=task.id` on `ReorderableDraggable` to identify tasks reliably.

2. **UI state is source of truth for order**: When reordering, read the current UI order (via task IDs), then sync DB to match.

3. **Don't mix object identity with equality**: Use task IDs for lookups, not Python object identity (`task in list`).

4. **Fresh data for persistence**: Always fetch fresh from DB before persisting to avoid overwriting with stale values.

5. **No index adjustment needed**: Flet reports final position, not insert-before-removal position.

6. **Rebuild is safer than manipulate**: Rather than trying to keep UI controls in sync manually, persist and rebuild from DB.

## Debugging Tips

Add prints at key points:
```python
print(f"[REORDER] Event: old_idx={old_idx}, new_idx={new_idx}")
print(f"[REORDER] UI order before: {ui_task_ids}")
print(f"[REORDER] Desired order: {new_order}")
print(f"[REORDER] DB order: {db_order}")
```

This helps identify:
- Whether Flet is reporting correct indices
- Whether UI and DB are in sync
- Whether sort_order values are being assigned correctly
