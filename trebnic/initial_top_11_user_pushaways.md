# Remaining User Push-Away Findings

This file was pruned from the original "top 11" audit after the
backdatable-time-logging refactor. Solved items were removed: manual time entry
now exists, `Task.completed_at` exists, stats/lists use completion day,
time-entry edit can change start/end without clamping, timer heartbeat uses
`heartbeat_at`, ordinary deletes now confirm, and the outdated gesture help text
was corrected.

## 1. Completing the primary object is still interrupted

Checking off an untimed task still opens a duration dialog before completion.
That dialog is now more correct than before because it can backdate the day, but
it remains a separate flow from the full manual start/end time editor. The common
"mark done" action is still conditional and modal.

References:
- `trebnic/ui/handlers/task_action_handler.py`
- `trebnic/ui/dialogs/task_dialogs.py`

## 2. Task capture with metadata is still heavy

Quick add is title-only. Date, project, and estimate still require opening the
"Add details" dialog, using chips and a slider, saving that dialog, then
submitting the task. Details still reset after each task. There is no local
natural-language quick add like `pay rent Friday 30m`.

References:
- `trebnic/ui/pages/task_view.py`
- `trebnic/services/claude_service.py`

## 3. Editing an existing task still has no stable mental model

Rename, reschedule, postpone, recurrence, duplicate, stats, and delete live in a
menu. Project changes by tapping the project tag; dates by a date tag or the
menu. Estimate is saved on create and displayed later, but there is still no
obvious edit path for a task's estimate after creation.

References:
- `trebnic/ui/components/task_tile.py`
- `trebnic/ui/dialogs/task_dialogs.py`

## 4. Navigation still has no real back model

`NavigationManager.navigate_to()` only replaces `current_page`; it does not keep
a route stack. Several back buttons still hardcode a return to Tasks, so flows
like Help -> Feedback -> Back or Stats -> Time entries -> Back cannot reliably
return to the previous screen. The date-change toasts also still explain where a
task moved, which points to an information architecture that is not self-evident.

References:
- `trebnic/ui/navigation.py`
- `trebnic/ui/pages/help_view.py`
- `trebnic/ui/pages/feedback_view.py`
- `trebnic/ui/pages/stats_view.py`
- `trebnic/ui/pages/time_entries_view.py`
- `trebnic/ui/dialogs/task_dialogs.py`

## 5. Manual ordering is still fragile

New task ordering still appears wrong: `TaskService.add_task()` asks the DB for
one incomplete task, then computes `max(sort_order)` from that one row. Because
the filtered query orders ascending, this is not the real max. Reordering also
assigns `sort_order` only across the currently visible filtered list, so hidden
tasks can still collide with visible tasks' order values.

References:
- `trebnic/services/logic.py`
- `trebnic/database/tasks.py`
- `trebnic/ui/pages/task_view.py`

## 6. Very short live timer sessions are still discarded

Manual entries can record short work, but the live timer still has a 5-minute
minimum save threshold. Stopping before that discards the running entry, which
can still surprise users who expect every measured session to be saved.

References:
- `trebnic/config.py`
- `trebnic/services/timer.py`
- `trebnic/ui/timer_controller.py`

## Through-line

The core data-trust failures are mostly fixed. The remaining issues are now
mostly workflow trust: users can record accurate data, but common paths still
split across different dialogs, navigation does not behave like a real stack,
and ordering/editing behavior can still feel unpredictable.
