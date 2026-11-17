# Trebnic development

From the repository root: `poetry install`, then
`poetry run flet run trebnic/main.py`.

## Android

Enable USB debugging; `adb devices` must show an authorized device.
On Windows, set `PYTHONIOENCODING=utf-8`. With Flutter on PATH:

```sh
poetry run flet build apk
poetry run flet-android-notifications-patch --project-root build/flutter
cd build/flutter
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Continue after a missing-desugaring failure only; fix other build errors first.
Reapply patches after regeneration. Export data before upgrading older builds;
import afterward. New builds use persistent storage. Don't uninstall.

## Chat recurrence

The phone command bridge supports `set_recurrence` and `clear_recurrence` on
pending tasks. `set_recurrence` accepts `task_id`, `frequency` (`days`, `weeks`,
`months`), `interval` (1–1000), `weekdays` (unique integers, Monday=0 through
Sunday=6, weekly only), `from_completion` (boolean), and `until` (inclusive
YYYY-MM-DD or null). It uses the app's existing initial-date calculation from
yesterday; the returned `due_date` is the resulting first occurrence.
Clearing recurrence preserves the due date. Task lists include the recurrence
rule. New recurring tasks use `add_task` followed by `set_recurrence`.

The hosted MCP service and Android app must both be updated. Every mutation
uses a unique `request_key`; retry the same intent with the same key and check
`get_command_status` until applied before reporting success.

## Task editing

New tasks captured in the UI start without a due date or estimate. Internally,
`estimated_seconds = 0` means not estimated; existing positive estimates are
preserved. Tap a task title to edit its metadata and notes in one panel.
Notes are one editable text field per task; clearing it removes the text.
Time summaries remain visible on mobile, including completed tasks. Tracked
time is derived from time entries and is never overwritten by metadata edits.

## Task reminders

Task details include an optional local reminder time (`HH:MM`). With no days
selected, it fires on the due date. Selected weekdays allow reminders before
the deadline; weekly recurring tasks restrict these to their own recurrence
window. Completing a recurring task copies the reminder to the next occurrence.
Notes do not implicitly schedule alarms. Clearing the time disables the custom
reminder and restores the usual morning task nudge.

Notifications must be enabled in Profile. Android schedules reminders for the
next seven days and refreshes them when tasks change or the app resumes. Exact
timing requires Android's Alarms and reminders permission. Custom reminders
replace the individual morning nudge; daily and overdue summaries still apply.

The reminder migration only adds columns. Existing file databases are first
snapshotted with SQLite's backup API to `trebnic-before-reminders.db` alongside
the live database. Export includes reminders and works on Android via the
native save dialog. Install updates with `adb install -r`; never uninstall or
clear application data to upgrade.

## Progress and history

Profile shows points, XP and levels (50 XP per level). The first positive task
estimate sets its completion reward at one point per 15 minutes. Each later
postponement reduces that reward by 10%, capped at 50%. Marking a task failed
deducts 90% of its original reward; logged work still earns one point per hour.
Penalties affect points, not XP. Reopening reverses completion or failure.
Scores are derived from saved tasks and time entries, so deleting a task also
removes its contribution. Existing work is baselined on upgrade: level 1, zero
points, with recorded time preserved. A SQLite backup precedes migration.

Task history and calendar day columns scroll independently. Completed tasks
appear on their completion date. To check on desktop, run the tests, then try
Profile, completion with the 15-minute-step slider (up to four hours), the task
menu's failure confirmation, and scrolling a day containing many closed tasks.
