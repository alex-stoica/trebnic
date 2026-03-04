# UI/UX issues

Audit of user-facing rough edges. Status: ✅ confirmed, ❌ fixed, ⚠️ overstated.

## Broken

### 1. Done tasks have zero actions ✅

`task_tile.py:236-254` — completed tasks render as a plain row with just a checkbox and time display. No menu, no
swipe, no way to delete, rename, view stats, or do anything except uncomplete. If a user completes a task by mistake
and wants to delete it, they have to uncomplete it first, then delete.

### 2. "Add details" button vanishes when input is cleared ✅

`task_view.py:239-241` — the details button visibility is tied to `task_input.value.strip()`. If the user opens
"add details", sets a project and due date, then clears the task title to rethink the name, all their detail choices
are still in `pending_details` but the button disappears. No way to get back to them without typing something first.

### 3. Completion dialog "skip" is ambiguous ⚠️

`task_dialogs.py:935-943` — dialog has three buttons: cancel, skip, and complete. Since cancel is right there, "skip"
reads more as "skip this step, proceed anyway" rather than "cancel everything." Still not ideal — "complete without
logging" or "skip time" would be clearer — but less dangerous than it sounds because cancel is visible.

## Confusing

### 4. Done task tags aren't interactive ✅

`task_tile.py:62-80` — pending tasks have clickable project tags (emitting `TASK_ASSIGN_PROJECT_REQUESTED` at line
89/104), but done tasks render the project name as plain text. The visual looks similar but one is tappable and the
other isn't — inconsistent affordance.

### 5. Recurring task date dialog is a dead end ❌

Fixed. `task_dialogs.py:507-515` now shows two buttons: "close" and "edit recurrence." The edit button closes the
info dialog and opens the recurrence editor directly.

### 6. "Cannot edit running" time entry gives no guidance ✅

`time_entries_view.py:205-207` — shows a snack with `t("cannot_edit_running")` and no hint about what to do (stop the
timer first). User is stuck wondering how to proceed.

### 7. Calendar day columns don't respond to taps ✅

`calendar_view.py:219-228` — the day content area (line 204-209) has no `on_click`, so tapping a day column does
nothing. Only the header (line 189) is tappable and opens the daily note dialog. Users expect the whole column to be
interactive.

## Annoyances / polish

### 8. No delete confirmation for non-recurring tasks ✅

`task_tile.py:178` — single tap on "delete" in the popup menu emits `TASK_DELETE_REQUESTED` with no "are you sure?"
dialog. Recurring tasks get a special dialog (`delete_recurrence`), but non-recurring tasks are deleted instantly.

### 9. Completed tasks nearly unreadable ❌

Partially fixed. Opacity removed, color improved from `#666666` to `#888888`. Still below WCAG AA (~2.9:1 vs 4.5:1
required) but much better than before.

### 11. Mobile task tiles have smaller padding ✅

`task_tile.py:258` vs `284` — mobile tiles use `padding=8` while desktop uses `padding=15`. Combined with the lack of
drag indicator and timer button on mobile, the tap target for the checkbox is small on phones.

### 12. Empty state only shows in Today filter ❌

Fixed. `task_view.py:529-544` now shows the empty state for all views when there are no pending tasks. Icon and text
adapt to context: Today shows "all caught up" with a notes card, Inbox shows "no drafts" with a hint, Projects shows
"no tasks in this project." The notes card remains Today-only.
