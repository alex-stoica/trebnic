# 📝 Tech Note: Fixing PopupMenu "Gray Screen" Flash

## 🚩 The Problem
When deleting an item via a `PopupMenuButton`, the app exhibited a **0.2s - 0.5s gray screen flash** (stuck modal barrier) before the UI updated.

## ❌ What DIDN'T Work & Why

| Attempt | Why It Failed |
| :--- | :--- |
| **Dimming control (`opacity=0.4`)** | Still triggered a layout recalculation while the popup overlay was active. |
| **Hiding control (`visible=False`)** | Collapsed the layout size to zero, destroying the "Anchor" point the menu relies on. |
| **`threading.Timer` + `show_snack`** | `show_snack` called `page.update()` immediately, interrupting the menu's closing animation. |
| **Removing control immediately** | Destroyed the anchor object in the UI tree before the overlay could dismiss. |
| **Full `refresh_lists()`** | `controls.clear()` + rebuild is too heavy and destroys the specific instance serving as the anchor. |

## 🔍 Root Cause
The `PopupMenuButton` creates an **Overlay (Modal Barrier)** on top of the page. When the menu closes, it runs a fade-out animation.
If `page.update()` is called—specifically one that modifies or removes the button that opened the menu—**during** this animation, the Flutter engine loses the reference to the anchor. The barrier gets "stuck" or the frame renders incorrectly, causing the gray flash.

## ✅ The Solution: Deferred Surgical Update

The fix requires **waiting** for the animation to finish, then performing a **batched, atomic update**.

```python
def show_snack(message, color=None, update=True):
    snack_bar.content = ft.Text(message, color="white")
    snack_bar.bgcolor = color or COLORS["card"]
    snack_bar.open = True
    # OPTIMIZATION: Allow suppressing immediate update to batch changes
    if update:
        page.update()

def delete_task(task_data):
    task_title = task_data['title']
    
    # 1. Remove from data immediately (Logic layer update)
    if task_data in tasks:
        tasks.remove(task_data)
    
    # 2. Capture index BEFORE async work (Snapshot state)
    index_to_remove = None
    for i, ctrl in enumerate(task_list.controls):
        if ctrl.content.data == task_data:
            index_to_remove = i
            break
    
    def delayed_update():
        # 3. CRITICAL: Wait for popup animation to fully close
        time.sleep(0.35) 
        
        # 4. Surgical removal: Remove ONLY this control (avoids full rebuild)
        if index_to_remove is not None and index_to_remove < len(task_list.controls):
            task_list.controls.pop(index_to_remove)
            
            # 5. Re-index: Essential for ReorderableDraggable to work after modification
            for i, ctrl in enumerate(task_list.controls):
                ctrl.index = i
        
        # 6. Prepare snackbar WITHOUT triggering update
        show_snack(f"'{task_title}' deleted", COLORS["danger"], update=False)
        
        # 7. Atomic Commit: Single page.update() handles removal + snackbar
        page.update()
    
    threading.Thread(target=delayed_update, daemon=True).start()
```

## 🧠 Key Insights

1.  **Respect the Animation:** Never call `page.update()` that affects the anchor while a PopupMenu is closing. A `0.35s` delay is the magic number.
2.  **Surgical Updates:** Prefer `list.pop(index)` over `list.clear()` + rebuild. It preserves the state of other items and is computationally cheaper.
3.  **Atomic Updates:** Batch multiple UI changes (removing the row + showing the snackbar) into a **single** `page.update()` call at the very end to prevent frame tearing.
4.  **State Snapshots:** Capture indices (`index_to_remove`) *before* entering a thread to avoid race conditions if the user interacts with the list during the delay.
5.  **Index Syncing:** When manually removing items from a `ReorderableListView`, you must manually update the `.index` property of the remaining items, or drag-and-drop will break.

## 💡 Why Dialogs Don't Have This Issue
When using an `AlertDialog` (e.g., "Assign to project"), the flow acts as a buffer:
1. Popup menu closes.
2. Dialog opens (Focus shifts).
3. User interacts.
4. Dialog closes → `page.update()`.

By the time the dialog closes, the PopupMenu's animation is long finished. Direct actions like **Delete** lack this buffer, so we must artificially create it with `time.sleep()`.