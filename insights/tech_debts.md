# Tech debts

Audit from 2026-03-01. Categorized by severity.

## Bugs (crash or wrong behavior)

### 1. `load_task_by_id` doesn't decrypt `notes`
- **File**: `database.py:988-1002`
- All other task-loading methods decrypt both `title` and `notes`, but `load_task_by_id` only decrypts `title`.
  Called during `complete_task` (logic.py:268), so completing a task with encrypted notes could corrupt the notes field.

### 2. New tasks get wrong sort order
- **File**: `services/logic.py:207-209`
- Uses `load_tasks_filtered(limit=1)` which returns the *lowest* sort_order (ASC ordering), then sets new task's
  order to `lowest + 1`. Should get the *highest*. New tasks collide on sort_order and appear in wrong positions.

### 3. Weekly recurrence ignores interval when weekdays are set
- **File**: `services/recurrence.py:42-47`
- "Every 2 weeks on Tuesday" fires every Tuesday because `_find_next_weekday` doesn't respect the interval.
  Only the fallback path (no weekdays) uses the interval.

### 4. `SnackService.show()` called as class method in stats export
- **File**: `ui/pages/stats_view.py:644-646`
- `SnackService.show(self.page, ...)` treats an instance method as a class method. Crashes with `AttributeError`
  whenever the user exports stats to JSON. `StatsPage` never receives a `SnackService` instance.

### 5. `_overdue_section` accessed before initialization
- **File**: `ui/pages/task_view.py:507-510`
- Created in `build()` (line 623) but `_refresh_async` can run before `build()`. Unlike `_section_label` and
  `_done_section` (initialized to `None` on lines 51-52), `_overdue_section` has no such initialization.
  Crashes with `AttributeError`.

## Logic errors

### 6. `persist_task` uses identity check for done status
- **File**: `services/logic.py:223-225`
- `task in self.state.done_tasks` uses dataclass equality. If any field was modified since loading, equality
  fails and the task silently gets saved as not-done.

### 7. Note indicators missing on first calendar render
- **File**: `ui/pages/calendar_view.py:243-296`
- `build()` uses `self._note_dates` but never calls `_load_note_dates()`. The set starts empty, so the
  first render never shows note icons on days that have notes.

### 8. Conversation history drops tool_use blocks
- **File**: `ui/pages/chat_view.py:142-143`
- Only stores text response, not full Claude response with tool_use/tool_result blocks. Multi-turn
  conversations lose tool context.

## Performance

### 9. `uncomplete_task` loads ALL done tasks to find one by ID
- **File**: `services/logic.py:347-348`
- Loads every completed task and iterates. Should use `load_task_by_id` for a single indexed lookup.

### 10. `delete_recurring_tasks_by_title` loads ALL recurring tasks
- **File**: `database.py:509-540`
- Fetches every recurring task into memory and decrypts each one to match titles. Unavoidable with encryption
  but worth noting as a scaling bottleneck.

### 11. O(projects x done_tasks) on every profile build
- **File**: `ui/pages/profile_view.py:484-490`
- For each project, iterates all done tasks. A single-pass `Counter` would be O(D).

### 12. `get_task_by_id` concatenates two lists on every call
- **File**: `models/entities.py:243`
- `for t in self.tasks + self.done_tasks` creates a new list each call. Called from hot paths.
  A dict lookup would be O(1).

## Fragile patterns

### 13. Hardcoded `.controls[1]` into Row children
- **Files**: `ui/pages/task_view.py:234,430,549,553-555,566`, `ui/pages/profile_view.py:415`
- Accesses the Nth child of a Row/Column by index. Any layout change silently breaks or crashes.
  Should use named references.

### 14. Direct manipulation of `CryptoService` private attributes
- **File**: `services/auth.py:1020-1029, 1071-1072`
- `unlock_with_passkey` and `change_master_password` directly set `crypto._key` and `crypto._aesgcm`.
  Bypasses any future validation. Partial re-encryption failure in `change_master_password` leaves
  orphaned data that can't be decrypted.

### 15. Double `pop_dialog` assumes exact dialog stack depth
- **File**: `ui/dialogs/project_dialogs.py:441-442`
- Assumes the dialog stack is exactly 2 deep. If any dialog is pushed between them, wrong one gets closed.

### 16. `FilePicker` leaks on every export click
- **File**: `ui/pages/stats_view.py:629-631`
- Every click creates and appends a new picker to `page.services`. Never removed.

### 17. `FilePicker` leaks on `ProfilePage` re-instantiation
- **File**: `ui/pages/profile_view.py:48`
- Appended to `page.services` in `__init__`. If `ProfilePage` is re-created, old picker is never removed.

### 18. `RecurrenceDialogController` initialized with no-op `on_close`
- **File**: `ui/dialogs/task_dialogs.py:610-611`
- Created with `on_close=lambda e: None`, then immediately overwritten. If `__init__` ever calls
  `on_close`, the call is silently swallowed.

## Missing error handling

### 19. Bare `except Exception` in feedback and chat
- **Files**: `ui/pages/feedback_view.py:146-148`, `ui/pages/chat_view.py:148-149`
- Project rules forbid bare `except Exception`. Should use specific exception types.

### 20. Duration silently clamped, can corrupt data on save
- **File**: `ui/pages/time_entries_view.py:209-210`
- If a time entry is shorter than 5 min or longer than 500 min, the edit dialog clamps the value
  without informing the user. Saving overwrites the original duration silently.

## Threading / async concerns

### 21. `asyncio.Event` created at construction time
- **Files**: `services/timer.py:37`, `services/notification_service.py:137`
- Created before the event loop is running. May bind to wrong loop, causing `RuntimeError`.

## Dead code

### 22. Unused state field `projects_expanded`
- **File**: `models/entities.py:209`

### 23. `calculate_weekly_stats` and `calculate_estimation_breakdown` are stubs
- **File**: `services/stats.py:329-360`

### 24. Passkey enable is a no-op
- **File**: `ui/auth_controller.py:196-199`

### 25. `UIController` class adds indirection without value
- **File**: `ui/controller.py`

### 26. `_subscribe_to_events` is an empty `pass`
- **File**: `ui/app_initializer.py:298-301`
