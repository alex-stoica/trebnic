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
    FLET_LOCAL = "flet_local"
    ANDROID_NATIVE = "android_native"
    PLYER_FALLBACK = "plyer"
    NONE = "none"
```
Each backend has its own `_deliver_*` method, making it easy to add new backends.

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

## Integration points (not yet implemented)

### 1. App initializer registration
```python
# In app_initializer.py _init_services():
from services.notification_service import notification_service
notification_service.inject_dependencies(
    page=self.page,
    async_scheduler=self.page.run_task,
    get_state=lambda: self.components.state,
)
registry.register(Services.NOTIFICATION, notification_service)
```

### 2. Starting the scheduler
```python
# After app is fully initialized:
notification_service.start_scheduler()
```

### 3. Timer completion notification
```python
# In TimerController or where timer stops:
if timer_data and isinstance(timer_data, dict):
    task = timer_data.get("task")
    elapsed = timer_data.get("elapsed", 0)
    if task and elapsed > 0:
        await notification_service.schedule_timer_complete_notification(task, elapsed)
```

### 4. Settings UI
Add to ProfilePage or new settings dialog:
- Toggle for `notifications_enabled`
- Toggle for `notify_timer_complete`
- Toggle for `notify_due_reminders`
- Number input for `reminder_minutes_before`
- Time pickers for `quiet_hours_start` and `quiet_hours_end`

### 5. Settings persistence
Update `SettingsService` to load/save notification settings:
```python
state.notifications_enabled = await db.get_setting("notifications_enabled", False)
state.notify_timer_complete = await db.get_setting("notify_timer_complete", True)
# ... etc
```

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
