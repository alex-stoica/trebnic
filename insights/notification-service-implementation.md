# Notification service implementation

## Overview

Implemented a cross-platform notification service for Trebnic following the existing singleton patterns (TimerService, CryptoService). The service manages scheduled notifications stored in SQLite with platform-specific delivery backends.

## What worked well

### 1. Following existing patterns
The codebase has well-established patterns that made implementation straightforward:
- Singleton with `_instance`, `_instance_lock`, `_initialized` attributes
- Dependency injection via `inject_dependencies()` method
- Async scheduler loop pattern from `TimerService._tick_loop()`
- Event bus subscriptions with `Subscription` objects for cleanup

### 2. Database-first notification storage
Storing notifications in `scheduled_notifications` table provides:
- Crash recovery - pending notifications survive app restarts
- Centralized management - easy to query, cancel, or reschedule
- Audit trail - delivered/canceled flags for debugging

### 3. Backend abstraction
The `NotificationBackend` enum cleanly separates detection from delivery:
```python
class NotificationBackend(Enum):
    PLYER = "plyer"
    PYJNIUS = "pyjnius"
    NONE = "none"
```
Each backend has its own `_deliver_*` method (`_deliver_plyer_notification`, `_deliver_android_notification`), making it easy to add new backends.

### 4. Event-driven rescheduling
Subscribing to task lifecycle events (`TASK_CREATED`, `TASK_UPDATED`, etc.) ensures notifications stay in sync with task changes without polling.

## Challenges and solutions

### 1. Circular import potential
**Problem:** NotificationService needs to import from events.py and config.py, which could create cycles.

**Solution:** Import only what's needed at module level. Avoid importing from models/entities.py in the service - instead, accept `get_state` callback that returns AppState.

### 2. Async in constructors
**Problem:** Service initialization happens before the event loop exists.

**Solution:** Use lazy initialization pattern - `inject_dependencies()` called after page is available, `start_scheduler()` called when ready to run.

### 3. Android notification complexity
**Problem:** Android notifications require NotificationChannel (API 26+), proper icons, and pending intents.

**Solution:** Basic implementation uses legacy builder pattern. Full Android notification channel support would need to be added for production use on Android 8+.

## Architecture decisions

### Scheduler interval (60 seconds)
Chose 60-second interval because:
- Due reminders typically scheduled hours/minutes in advance - precision not critical
- Lower CPU/battery usage than shorter intervals
- Matches existing timer heartbeat pattern

### Task-based rescheduling
On any task event, we:
1. Delete existing unfired notifications for that task
2. Check if task has due_date and reminders enabled
3. Create new notification if trigger_time is in future

This is simpler than tracking changes and updating in place.

### Quiet hours handling
Notifications that fire during quiet hours are skipped (not delivered, not marked delivered). They stay pending and will be checked next scheduler cycle. This means if quiet hours end, backlogged notifications may fire in burst.

**Alternative considered:** Mark as delivered but don't show. Chose current approach to allow catch-up behavior.

## Integration status

The following integration points are now implemented:

- **App initializer**: `app_initializer.py` wires up the service
- **Scheduler**: Runs every 60 seconds checking for due reminders
- **Timer completion**: `timer_controller.py` sends notifications on timer stop
- **Settings UI**: Profile page has notification toggles and test button
- **Settings persistence**: Notification preferences saved via SettingsService

### Platform status
- **Windows**: Working (plyer backend, pure Python + ctypes)
- **Android**: Not working (plyer imports but fails silently, pyjnius won't load)
- See `insights/proposed_notification_plan.md` for details on Android blockers

## Testing considerations

1. **Backend fallback:** Test on systems without flet_local_notifications to verify plyer fallback works
2. **Quiet hours:** Test overnight quiet hours (22:00 - 07:00) edge case
3. **Task deletion:** Verify CASCADE delete removes notifications when task deleted
4. **Scheduler recovery:** Restart app with pending notifications - verify they fire

## Future enhancements

1. **Daily digest:** Group multiple due tasks into single morning notification
2. **Overdue notifications:** Alert when tasks become overdue
3. **Android notification channels:** Required for Android 8+ proper notification management
4. **iOS support:** Would need native plugin or Flet iOS notification support
5. **Notification actions:** "Mark complete" button on notification (backend dependent)
