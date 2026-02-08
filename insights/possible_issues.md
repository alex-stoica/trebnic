# Possible issues

Audit of the Trebnic codebase. Covers code quality, UI friction, race conditions, and missing safety nets.

---

## 1. Bad practices

### 1.1 Imports inside functions (CLAUDE.md forbids this)

`services/logic.py` has three conditional imports inside methods:
- `from events import AppEvent` inside `reload_state_async()` (line 114)
- `from events import AppEvent` inside `reload_state()` (line 145)
- `import concurrent.futures` inside `load_state()` (line 83)

The comment says _"AppEvent enum is safe to import"_ - the circular dependency concern is real, but this should be solved architecturally (e.g., by moving the enum to a separate module) rather than violating the project rule.

### 1.2 No tests

The `tests/` directory contains only an empty `__init__.py`. There are zero test files. For a codebase with encryption, async database operations, recurrence date math, and timer state machines, this is a significant risk.

---

## 2. Race conditions and async issues

### 2.1 Timer stop uses stale task reference

`services/timer.py`: In the `stop()` method, task state is captured (reference to `self.active_task`) before the stop logic runs. If the same task is modified elsewhere between capture and execution of `_finalize_stop`, the spent-time update operates on stale data. The task is not reloaded from the database before `task.spent_seconds += elapsed`.

### 2.2 Timezone-naive datetimes throughout the codebase

`services/notification_service.py` uses `datetime.now()` (timezone-naive) in 4 places (lines 266, 482, 529, 629). All comparisons like `trigger_time <= now` are naive. If the system timezone changes (e.g., mobile travel, DST) or data is migrated, notifications will misfire. Should use `datetime.now(timezone.utc)` or handle timezone consistently.

### 2.3 Navigation drawer close races with state update on mobile

`ui/navigation.py`: `select_nav()` calls `self.page.run_task(self.page.close_drawer)` without awaiting, then immediately calls `update_nav()` synchronously. On mobile, the drawer may still be animating closed when state updates and UI rebuilds, causing visual glitches.

---

## 3. Functionality gaps

### 3.1 Stats placeholder methods silently return empty data

`services/stats.py:329-360`: `calculate_weekly_stats()` and `calculate_estimation_breakdown()` are documented as part of the API but return empty lists silently. If a caller depends on this data, they get no error and no indication the feature isn't implemented. Should raise `NotImplementedError`.

### 3.2 Recovered timer entry may reference deleted task

`services/logic.py:66-69`: On app startup, if there's an incomplete time entry it's loaded into `state.recovered_timer_entry`, but the corresponding task might have been deleted since the entry was created. No validation is done, which could cause errors when trying to resume the timer.

---

## 4. UI non-intuitive

### 4.1 No confirmation dialog for task deletion

`task_tile.py` emits `TASK_DELETE_REQUESTED` directly from the popup menu without asking _"Are you sure?"_. A single accidental tap deletes a task permanently (unless it's recurring, which gets a special dialog). Non-recurring tasks have no safety net.

### 4.2 Duration knob lacks clear affordance

`duration_knob.py`: The radial slider shows "drag to adjust" text in the center but:
- No indication that tapping also works
- The 5-minute snap increments aren't explained
- Min/max labels ("5m" / "8h20m") are small and positioned at the edges
- No keyboard accessibility
- Users unfamiliar with radial controls have no reference for expected interaction

### 4.3 Encrypted task titles show as "[Locked]" without explanation

`task_tile.py`: When encryption is active and the app is locked, task titles show as "Encrypted" with a lock icon. This is confusing because:
- Users don't know if this is intentional or an error
- There's no inline "tap to unlock" or "enter password" action
- The locked state looks like data corruption to unfamiliar users

### 4.4 Date picker blocks recurring tasks without actionable guidance

`task_dialogs.py`: Attempting to set a due date on a recurring task shows _"Recurrent tasks use their recurrence pattern"_ but doesn't offer a button to edit the recurrence settings. The user hits a dead end.

### 4.5 Calendar day columns aren't clickable

`calendar_view.py`: The weekly calendar displays tasks per day but clicking a day column doesn't navigate to that day's task view. Tasks are display-only in the calendar, which contradicts the affordance of a clickable grid.

### 4.6 Color contrast fails accessibility (WCAG)

`config.py:203-204`: `done_text` color `#666666` on `done_bg` `#1a1a1a` gives a contrast ratio of ~2.5:1. WCAG AA requires 4.5:1 for normal text. Completed tasks may be unreadable for users with low vision.

### 4.7 "Skip" button ambiguity in task completion dialog

`task_dialogs.py`: The completion dialog offers "Skip" which completes the task without logging time. But "Skip" sounds like it cancels the action entirely. A label like "Complete without time" would be clearer.

### 4.8 Empty states lack guidance

`time_entries_view.py`: "No time entries" message appears but doesn't explain how to create one (e.g., _"Start the timer on a task to create an entry"_). New users won't know what to do.

### 4.9 Hardcoded widths may overflow on small screens

Several components use fixed pixel widths:
- `time_entries_view.py`: `width=180` for duration knob
- `stats_view.py`: `width=200` for progress bar
- `stats_view.py`: `height=280` for project list

These may overflow or get clipped on narrow phone screens.

### 4.10 Profile settings page is overloaded

`profile_view.py`: The preferences section combines estimated time, notifications (with sub-settings), email preferences, reset defaults, save, and factory reset in one scrollable column. This is a lot of cognitive load - grouping into collapsible sections or tabs would help.

---

## 5. Version / dependency

### 5.1 Pinned to `>=0.80.0`, latest is `0.80.5`

`requirements.txt` and `pyproject.toml` both specify `flet>=0.80.0`. The latest release is **0.80.5** (January 30, 2026). While the `>=` constraint allows upgrades, the build artifacts in `trebnic/build/` may bundle an older version. Worth running `pip install --upgrade flet` and rebuilding.

---

## 6. Insight docs audit

Review of `insights/*.md` files for accuracy, relevance, and staleness.

### 6.1 Out of scope with code

**`biometric-auth-implementation.md`** - describes `keyring`-based biometric auth architecture (Windows Hello, Touch ID, Android BiometricPrompt) as if implemented. Reality: `keyring` is not in `requirements.txt` or `pyproject.toml`. The `PasskeyService` in `services/auth.py` has placeholder methods only. The doc's status line says "not wired up" but then spends 130 lines detailing implementation that doesn't exist. Should be rewritten as a proposal/design doc or deleted until actually implemented.

**`dual-api-refactoring.md`** - documents a completed one-time refactoring (sync+async API consolidation). Purely historical. The line counts are accurate (logic.py is still 498 lines) but the doc has zero future utility. No one needs to know what the code looked like before the refactor.

### 6.2 Security concern in credential storage

**`feedback-email.md`** documents that `credentials.py` (containing the Resend API key) gets bundled into the APK by `flet build`. The API key ships inside every APK binary. Should be replaced with a backend proxy (e.g. Cloudflare Worker) so no secrets live in the app.

### 6.4 Still accurate and useful

These files are current, concise, and match the codebase:
- `flet-0.80-migration.md` - comprehensive API reference, all changes verified
- `auth-flow-patterns.md` - state machine and dialog patterns match `auth_controller.py`
- `reordering_learnings.md` - `_on_reorder` pattern still used in `task_view.py`
- `grayscreenflash.md` - `TASK_DELETE_REQUESTED` event pattern still active
- `async-dialog-callbacks.md` - `page.run_task()` patterns still used throughout
- `encryption-implementation.md` - registry pattern and crypto format verified

---

## Summary by severity

| Severity | Count | Items |
|----------|-------|-------|
| High | 3 | No tests (1.2), no delete confirmation (4.1), contrast fail (4.6) |
| Medium | 5 | Imports in functions (1.1), timer stale ref (2.1), timezone-naive (2.2), recovered timer (3.2), API key in APK (6.2) |
| Low | 12 | Flet version (5.1), stats placeholders (3.1), UI polish (4.2-4.10), stale docs (6.1) |
