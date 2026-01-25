# Key Mistakes & Learnings: Flet ReorderableListView 

## Mistakes Made

1. **Wrong class name**: `ReorderableDragHandle` → actual class is `ReorderableDraggable`
2. **Invalid parameters**: `mouse_cursor`, `spacing` don't exist on these classes
3. **Index mismatch**: Static indices in `ReorderableDraggable` caused wrong drag behavior

## Solutions

### Suboptimal (loses state)
```python
def on_reorder(e):
    tasks.insert(e.new_index, tasks.pop(e.old_index))
    task_list.controls.clear()
    for i, task in enumerate(tasks):
        task_list.controls.append(ft.ReorderableDraggable(index=i, content=create_task(...)))
    page.update()
``` 

### Better Solution (preserves state)
```python
def on_reorder(e):
    tasks.insert(e.new_index, tasks.pop(e.old_index))
    item = task_list.controls.pop(e.old_index)
    task_list.controls.insert(e.new_index, item)
    for i, control in enumerate(task_list.controls):
        control.index = i
    page.update()
```
### Moving Items Between Lists
```python
def complete_task(task_data):
    tasks.remove(task_data)
    done_tasks.append(task_data)
    refresh_lists()  # Rebuild acceptable when changing UI representation
```

### Closures for Event Handlers
```python
def create_task(task_data):
    def on_check(e):
        complete_task(task_data)  # Captured in closure
    return ft.Checkbox(on_change=on_check)
```
### Collapsible UI with Toggle State
```python
expanded = False
def toggle(e):
    nonlocal expanded
    expanded = not expanded
    container.visible = expanded
    page.update()
```
## Key Takeaways 

1. **Data-driven architecture**: Keep task data separate from UI
2. **State preservation**: Move controls instead of rebuilding when possible
3. **Index sync**: Always update `ReorderableDraggable.index` after reorder
4. **Closures**: Bind data to handlers cleanly
5. **`nonlocal`**: Required for modifying outer variables in nested functions
6. **Source > docs**: Verify against actual class definitions