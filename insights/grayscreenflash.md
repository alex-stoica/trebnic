# PopupMenu "gray screen" flash

## The problem
When deleting an item via a `PopupMenuButton`, the app exhibited a 0.2-0.5s gray screen flash (stuck modal barrier) before the UI updated.

## Root cause
The `PopupMenuButton` creates an overlay (modal barrier) on top of the page. When the menu closes, it runs a fade-out animation. If `page.update()` is called — specifically one that modifies or removes the button that opened the menu — **during** this animation, the Flutter engine loses the reference to the anchor. The barrier gets "stuck" or the frame renders incorrectly, causing the gray flash.

## What didn't work

| Attempt | Why it failed |
|---------|---------------|
| Dimming control (`opacity=0.4`) | Still triggered a layout recalculation while the popup overlay was active |
| Hiding control (`visible=False`) | Collapsed the layout size to zero, destroying the anchor point the menu relies on |
| `threading.Timer` + `show_snack` | `show_snack` called `page.update()` immediately, interrupting the menu's closing animation |
| Removing control immediately | Destroyed the anchor object in the UI tree before the overlay could dismiss |
| Full `refresh_lists()` | `controls.clear()` + rebuild is too heavy and destroys the specific instance serving as the anchor |

## Current solution: event-driven deletion

The gray flash was eliminated by decoupling the popup action from the actual deletion. The popup menu emits an event; the handler processes it after the menu has closed.

```python
# task_tile.py — popup menu just emits an event, no direct mutation
lambda e: event_bus.emit(AppEvent.TASK_DELETE_REQUESTED, self.task)
```

The `TASK_DELETE_REQUESTED` handler in `task_action_handler.py` processes the deletion asynchronously via `page.run_task()`. By the time the handler runs, the popup animation has already completed.

## Key insights

1. **Respect the animation**: Never call `page.update()` that affects the anchor while a PopupMenu is closing.
2. **Event decoupling solves timing**: Emitting an event from the popup and handling it asynchronously naturally introduces enough delay for the animation to finish.
3. **Dialogs act as buffers**: Actions that open a dialog (e.g., "Assign to project") don't hit this issue because the dialog opening shifts focus away from the popup, and by the time the dialog closes the popup animation is long finished.
4. **Atomic updates**: Batch multiple UI changes into a single `page.update()` call to prevent frame tearing.
