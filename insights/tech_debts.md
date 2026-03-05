# Tech debts

Audit from 2026-03-01. Categorized by severity, ordered by importance within each category.

## Bugs (crash or wrong behavior)

### 1. New tasks get wrong sort order
- **File**: `services/logic.py:217`
- Uses `load_tasks_filtered(limit=1)` which returns the *lowest* sort_order (ASC ordering), then sets new task's
  order to `lowest + 1`. Should get the *highest*. New tasks collide on sort_order and appear in wrong positions.

## Logic errors

### 2. Conversation history drops tool_use blocks
- **File**: `ui/pages/chat_view.py:143-144`
- Only stores text response, not full Claude response with tool_use/tool_result blocks. Multi-turn
  conversations lose tool context.

## Fragile patterns

### 3. `FilePicker` leaks on `ProfilePage` re-instantiation
- **File**: `ui/pages/profile_view.py:47-48`
- Appended to `page.services` in `__init__`. If `ProfilePage` is re-created, old picker is never removed.

### 4. `RecurrenceDialogController` initialized with no-op `on_close`
- **File**: `ui/dialogs/task_dialogs.py:617`
- Created with `on_close=lambda e: None`, then immediately overwritten. If `__init__` ever calls
  `on_close`, the call is silently swallowed.

### 5. `get_daily_notes_range` has no SQL-level empty filter
- **File**: `database/records.py:252-267`
- No `WHERE content != ''` clause. Filtering happens post-decryption in Python (line 264), which is correct
  given encryption, but all empty rows are still fetched from SQLite. Worth noting as a scaling consideration.

## Performance

### 6. `uncomplete_task` loads ALL done tasks to find one by ID
- **File**: `services/logic.py:354-357`
- Loads every completed task and iterates. Should use `load_task_by_id` for a single indexed lookup.

### 7. `get_task_by_id` concatenates two lists on every call
- **File**: `models/entities.py:243-247`
- `for t in self.tasks + self.done_tasks` creates a new list each call. Called from hot paths.
  A dict lookup would be O(1).

### 8. O(projects x done_tasks) on every profile build
- **File**: `ui/pages/profile_view.py:489-493`
- For each project, iterates all done tasks. A single-pass `Counter` would be O(D).

### 9. `delete_recurring_tasks_by_title` loads ALL recurring tasks
- **File**: `database/tasks.py:114-134`
- Fetches every recurring task into memory and decrypts each one to match titles. Unavoidable with encryption
  but worth noting as a scaling bottleneck.

## Dead code

### 10. Passkey enable is a no-op
- **File**: `ui/auth_controller.py:196-198`
- `handle_toggle_passkey` only handles the `not enable` branch. When `enable=True`, the function does nothing.
