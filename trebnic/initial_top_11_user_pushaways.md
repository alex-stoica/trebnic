# Remaining User Push-Away Findings

This file was pruned from the original "top 11" audit after the
backdatable-time-logging refactor and the follow-up workflow pass. Solved items
were removed: manual time entry exists, `Task.completed_at` exists, stats/lists use
completion day, time-entry edit can change start/end without clamping, timer
heartbeat uses `heartbeat_at`, ordinary deletes confirm, gesture help text was
corrected, **completion is now instant (no modal) with an optional "Add time"
action**, **new-task ordering uses MAX(sort_order) and reorder renumbers globally
(no collisions)**, an existing task's **estimate is now editable** from its menu,
and the add bar has **inline Due/Project chips**.

## 1. Task capture: estimate-at-create and natural language

Inline Due/Project chips now cover the common case without a dialog, but setting
an **estimate while creating** a task still needs the "Add details" dialog, and
there is no natural-language quick add like `pay rent Friday 30m`. Pending details
also still reset after each add.

References:
- `trebnic/ui/pages/task_view.py`
- `trebnic/services/claude_service.py`

## 2. Editing an existing task is still menu-scattered

Estimate is now editable from the task menu, but rename / reschedule / postpone /
recurrence / duplicate / stats / delete still live in a kebab, while project is
changed by tapping the project tag and date by the date tag. There is no single
"edit task" surface.

References:
- `trebnic/ui/components/task_tile.py`
- `trebnic/ui/dialogs/task_dialogs.py`

## 3. Navigation still has no real back model (deferred)

`NavigationManager.navigate_to()` only replaces `current_page`; it keeps no route
stack. Several back buttons hardcode a return to Tasks, so flows like
Help -> Feedback -> Back or Stats -> Time entries -> Back cannot reliably return to
the previous screen. The date-change toasts also still explain where a task moved,
which points to an information architecture that is not self-evident. Intentionally
deferred — it is a self-contained refactor (add a route stack / `go_back()`).

References:
- `trebnic/ui/navigation.py`
- `trebnic/ui/pages/help_view.py`, `feedback_view.py`, `stats_view.py`, `time_entries_view.py`

## 4. Very short live timer sessions are discarded (by design)

The live timer keeps a 5-minute minimum-save threshold: stopping earlier discards
the running entry. This is intentional (the user confirmed short sessions like
"brush teeth" should not be logged). Documented so it is not re-flagged as a bug.
Manual logging covers deliberate short entries.

References:
- `trebnic/config.py` (`MIN_TIMER_SECONDS`)
- `trebnic/services/timer.py`

## Through-line

The data-trust and ordering failures are fixed. The remaining items are workflow
ergonomics (capture/edit still span a couple of surfaces) and the navigation
back-stack, plus one intentional product choice (short-timer discard).
