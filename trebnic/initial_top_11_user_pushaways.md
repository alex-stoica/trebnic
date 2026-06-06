# Initial Top 11 User Push-Away Findings

> **HISTORICAL (pre-refactor snapshot).** This is the original read-through that
> motivated the backdatable-time-logging + day-attribution refactor. Many items
> are now fixed: `Task.completed_at` exists, stats/lists attribute by real
> completion day, time entries have editable start/end (no clamp), manual "Add
> time entry" + global "Log time" exist, the timer heartbeat no longer writes a
> fake `end_time`, and `spent_seconds` is a canonical sum of entries. Treat the
> details below as the problem statement, not the current state; see
> `insights/errors.md` and git history for what changed.

This captures the first deep read-through of issues likely to push users away. It focuses on behavior and data trust rather than implementation cleanup.

## 1. Past work is not a first-class action

The main timer path starts at `datetime.now()`, and the completion dialog creates time ending "now". The time-entry editor only changes duration from a fixed start time. There is no normal "add time entry for Tuesday 14:00-15:30" UI.

References:
- `trebnic/services/timer.py`
- `trebnic/ui/dialogs/task_dialogs.py`
- `trebnic/ui/pages/time_entries_view.py`

## 2. Completion analytics are structurally wrong

`Task` has no `completed_at`. `complete_task` only flips `is_done`. Stats bucket completions and streaks by `due_date`, with a TODO acknowledging that this is a proxy. No-date completed tasks vanish from completion stats; future-due tasks count in the future.

References:
- `trebnic/models/entities.py`
- `trebnic/services/logic.py`
- `trebnic/services/stats.py`

## 3. Crash recovery can lose or desync tracked time

Timer heartbeats save `end_time` into the database, then clear it only in memory. Recovery only looks for rows where `end_time IS NULL`, so after a crash the app may not recover the active timer, while `spent_seconds` was never incremented.

References:
- `trebnic/services/timer.py`
- `trebnic/database/records.py`

## 4. Fixing time is lossy

Editing a time entry clamps duration to 5-500 minutes, cannot move the start date, and saving rewrites the end time from that clamped duration. Short sessions under 5 minutes are discarded by the timer. A user trying to repair data can destroy it.

References:
- `trebnic/config.py`
- `trebnic/ui/pages/time_entries_view.py`
- `trebnic/services/timer.py`

## 5. Completing the primary object is interrupted

Checking off an untimed task opens a duration modal. That makes the most common action conditional and slower. Notification "Done" bypasses that prompt entirely, so completion behavior differs by entry point.

References:
- `trebnic/ui/controllers/task_action_handler.py`
- `trebnic/ui/dialogs/task_dialogs.py`
- `trebnic/services/notification_service.py`

## 6. Task capture punishes metadata

Quick add is title-only. Date, project, and estimate require opening "Add details", using chips and a slider, saving that modal, then submitting the task. Details reset after every task. There is no local natural-language quick add like "pay rent Friday 30m".

References:
- `trebnic/ui/pages/task_view.py`
- `trebnic/ui/pages/chat_view.py`
- `trebnic/services/claude_service.py`

## 7. Editing a task has no stable mental model

Rename, reschedule, postpone, recurrence, duplicate, stats, and delete live in a kebab menu. Project changes by tapping the project tag. Date changes by tapping the date tag only if a date already exists. Estimated time is displayed but has no edit path after creation.

References:
- `trebnic/ui/components/task_tile.py`
- `trebnic/ui/dialogs/task_dialogs.py`

## 8. Navigation makes tasks feel like they disappear

Internal `TODAY` is labeled "Tasks"; there are Inbox/Draft, Tasks, Today/Next chips, Calendar, Notes, Projects, plus Stats/Chat hidden under a gear. Date changes emit explanatory toasts about where the task went, which is a sign the information architecture is not self-evident. Completed no-date tasks are absent from Today's done section.

References:
- `trebnic/config.py`
- `trebnic/app.py`
- `trebnic/ui/dialogs/task_dialogs.py`
- `trebnic/services/logic.py`

## 9. Ordinary deletes are too easy

Recurring-task deletion gets a dialog, but a normal task delete from the menu immediately deletes the task and its time entries, with no confirm or undo. Time-entry deletion is also immediate.

References:
- `trebnic/ui/controllers/task_action_handler.py`
- `trebnic/database/tasks.py`
- `trebnic/ui/pages/time_entries_view.py`

## 10. Manual ordering is likely unreliable

New tasks try to append by loading one incomplete task, but the DB query orders ascending, so this is not the max `sort_order`. That can create duplicate sort orders. Reordering persists only the currently visible filtered list, which can collide with hidden tasks.

References:
- `trebnic/services/logic.py`
- `trebnic/database/tasks.py`
- `trebnic/ui/pages/task_view.py`

## 11. Help promises gestures the UI does not appear to implement

Help text tells users to swipe right to start timers, swipe left to delete, long-press/use menu, and swipe calendar weeks. The inspected UI has normal buttons, menus, tags, and reorder controls, but no matching swipe/long-press gesture implementation.

References:
- `trebnic/i18n.py`
- `trebnic/ui/components/task_tile.py`

## Through-line

The deepest pattern is data trust. Trebnic asks users to build a habit around tasks and time, but the app currently makes correction hard, makes common actions modal, and reports analytics from proxies. Once users notice one wrong total or one vanished task, the whole system stops feeling dependable.
