# Notes issues

Audit of daily notes functionality. Core problem: `save_if_editing()` is sync but wraps a fire-and-forget async save.

## 1. Race condition: notes → calendar navigation

`app.py:319-321` calls `save_if_editing()` on every navigation, then immediately builds the next page. When navigating to calendar:

```
save_if_editing()                           → fires async save, returns instantly
page.run_task(_refresh_and_build_calendar)  → loads note_dates from DB
```

Both tasks run concurrently. `_load_note_dates` can query the DB before the save commits, so the calendar won't show a note indicator for the note you just wrote.

## 2. Race condition: re-editing while save is in-flight

`notes_view.py:113-115` — `_start_editing()` calls `save_if_editing()` then immediately reads from `_note_markdown.value`. The save hasn't completed, so `_last_saved_content` hasn't been updated yet. If the save fails, the user never knows.

## 3. UI state set in two conflicting places

When content is unchanged, `save_if_editing()` synchronously calls `_show_display()` / `_show_placeholder()` (lines 154-157). When content changed, the same transitions happen inside the async `_save()` callback (lines 168-171). The notes view stays in editing state until the async save completes — the user sees the text field lingering after navigating away. If they navigate back before the save finishes, the view is in a stale editing state.

## 4. `get_daily_notes_range` doesn't filter empty notes

`database/records.py:247` has no `WHERE content != ''` clause, unlike `get_all_daily_notes` on line 265. `get_dates_with_notes` (feeds calendar indicators) compensates by filtering post-decryption in Python, but the inconsistency between the two query methods is a footgun.

## Fix direction

Make `save_if_editing` async (awaitable) so callers can wait for the save to finish before proceeding. This fixes #1, #2, and #3 in one shot. Issues #4 and #5 are minor DB-layer inconsistencies.
