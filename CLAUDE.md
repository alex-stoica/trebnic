# Trebnic

Flet-based task manager with timer tracking, recurring tasks, and calendar view.

## Architecture principles

1. **Event-driven decoupling**: UI components emit events to the EventBus, handlers react to them. Components never call services directly - this allows testing in isolation and swapping implementations without changing UI code.

2. **Async-first with sync wrappers**: All database operations are async (aiosqlite). Services expose async methods, and `page.run_task()` bridges sync UI callbacks to async operations. Never block the UI thread.

3. **State flows down, events flow up**: `AppState` holds all application data and flows down to components. User interactions flow up as events. Components read from state but never modify it directly - they emit events that handlers process.

## Rules

- Line length: 120 chars max
- FORBIDDEN: imports inside functions
- FORBIDDEN: bare `except Exception` (acceptable only in very rare cases, try to use specific exceptions)
- Avoid unnecessary capitalization: capitalize only sentence starts and proper nouns (e.g., "Privacy-first task manager" not "Privacy-First Task Manager", "New York" is fine)
- Some tasks are harder than others, if you keep going back and forth and need many iterations to solve an issue, write the key learnings to `insights/` to a `.md` file to make sure you never do the same mistakes again
- **Translations**: All user-facing text must use `t("key")` from `i18n.py`. Add both English and Romanian translations. Use "treabă/treburi" (not "sarcină/sarcini") for "task/tasks" in Romanian

## Structure

```
trebnic/
├── main.py                         # Entry point - just calls ft.app()
├── app.py                          # Orchestrates components, wires callbacks, builds layout
├── config.py                       # All constants, colors, enums - single source of truth for magic values
├── database.py                     # Async SQLite with aiosqlite - all SQL lives here
├── events.py                       # Pub/sub event bus - decouples components without direct references
├── i18n.py                         # Internationalization - t("key") returns translated string
├── registry.py                     # Service registry - dependency injection to avoid circular imports
├── models/
│   └── entities.py                 # Task, Project, TimeEntry, AppState - no business logic, just data
├── services/
│   ├── logic.py                    # TaskService - bridges UI actions to DB via async scheduling
│   ├── recurrence.py               # Date math for recurring tasks - pure functions, no state
│   ├── timer.py                    # TimerService - tracks active timer state and elapsed time
│   ├── crypto.py                   # AES-256-GCM encryption, Argon2/PBKDF2 key derivation
│   ├── auth.py                     # Master password setup, lock/unlock state, passkey placeholders
│   └── stats.py                    # StatsService - calculates user stats and analytics
└── ui/
    ├── app_initializer.py          # Builds all components in correct order - dependency injection point
    ├── controller.py               # UIController - navigation and project utilities only
    ├── navigation.py               # NavigationManager - handles nav state, drawer, sidebar switching
    ├── helpers.py                  # UI utilities: SnackService, accent_btn, format_duration
    ├── timer_controller.py         # Glue between TimerService and TimerWidget with page.run_task
    ├── auth_controller.py          # Coordinates auth UI flows (unlock, setup, settings dialogs)
    ├── handlers/
    │   └── task_action_handler.py  # Handles TASK_*_REQUESTED events from EventBus
    ├── components/
    │   ├── task_tile.py            # Single task row - checkbox, menu, swipe actions
    │   ├── timer_widget.py         # Header timer display - responds to timer events
    │   ├── project_sidebar_item.py  # Clickable project row with selection state
    │   └── duration_knob.py        # Radial slider for time input - math-heavy gesture handling
    ├── dialogs/
    │   ├── base.py                 # open_dialog() factory - consistent dialog styling
    │   ├── dialog_state.py         # RecurrenceState - dialog-specific state separate from model
    │   ├── task_dialogs.py         # All task-related dialogs: rename, date, recurrence, stats
    │   ├── project_dialogs.py      # Project create/edit dialog with color picker
    │   └── auth_dialogs.py         # Unlock, setup password, change password, encryption settings
    ├── pages/
    │   ├── task_view.py            # Main task list with ReorderableListView - most complex UI
    │   ├── calendar_view.py        # Week view grid - reads from state.tasks directly
    │   ├── time_entries_view.py    # Time entry list for a specific task
    │   ├── profile_view.py         # User profile with preferences (estimated time, notifications, factory reset)
    │   ├── stats_view.py           # User statistics with charts and analytics
    │   ├── help_view.py            # How to use guide with privacy emphasis
    │   └── feedback_view.py        # Donation info and feedback form
    ├── presenters/
    │   └── task_presenter.py       # Pure formatting functions for task display
    └── formatters/
        └── time_formatter.py       # Converts seconds to "1h 30m" format
```

## Authentication & Encryption

Field-level encryption for sensitive data (task titles, notes, project names):

- **Master password** derives encryption key via Argon2id (never stored)
- **Salt + verification hash** stored in settings table
- **AES-256-GCM** encrypts fields transparently in database.py
- **Graceful degradation** - works without encryption if user skips setup

Remaining TODOs (see `insights/encryption-implementation.md`):
- Passkey/biometrics integration (platform-specific)
- SQLCipher for whole-database encryption

## Stats feature

User stats page accessible from profile settings. Core elements implemented, advanced features stubbed:

**Implemented:**
- Basic stats cards (tasks completed, time tracked, estimation accuracy)
- Time tracked by day chart (last 7 days bar chart)
- Project filter dropdown
- Stats service with core calculations

**Not implemented (stubs/placeholders):**
- Weekly aggregation view (toggle between daily/weekly)
- Postponement analytics (count, average per task)
- Estimation vs actual detailed breakdown
- Date range picker for custom periods
- Export stats to CSV

Location: `ui/pages/stats_view.py`, `services/stats.py`

## Other Folders

- `insights/` - Development notes and learnings (Flet quirks, build issues, etc.)
