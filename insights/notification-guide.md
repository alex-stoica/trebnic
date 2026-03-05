# Notification implementation guide

## Architecture

```
Python (ft.Service)
  -> _invoke_method("show_notification", args)
    -> Flet protocol (Python <-> Dart)
      -> FletService subclass in Dart
        -> flutter_local_notifications plugin
          -> Android NotificationManager
```

plyer/pyjnius don't work on Android — they depend on Kivy's `PythonActivity` which doesn't exist in Flet.

## Extension

Published as `flet-android-notifications` on PyPI (v0.4.0+). Just instantiate `FletAndroidNotifications()`. Do NOT add to `page.overlay` or `page.services` — it auto-registers via `Service.init()`.

### 0.4.0 API

| Method | Purpose |
|--------|---------|
| `show_notification()` | Show an immediate notification. |
| `schedule_notification()` | Schedule via AlarmManager. Fires even if app is killed or device restarts. |
| `request_exact_alarm_permission()` | Android 14+ requires explicit consent for exact alarms. |
| `cancel(notification_id)` | Cancel a specific scheduled notification. |
| `cancel_all()` | Cancel all active notifications. |

**`show_notification()` / `schedule_notification()` key parameters:**
- `scheduled_time: datetime` — (schedule only) naive = local time, aware = converted to UTC internally
- `schedule_mode: str` — (schedule only) `"alarm_clock"`, `"exact"`, `"exact_allow_while_idle"`, `"inexact"`, `"inexact_allow_while_idle"` (default)
- `match_date_time_components: Optional[str]` — `"time"` (daily), `"day_of_week_and_time"` (weekly), `"day_of_month_and_time"` (monthly), `"date_and_time"` (yearly), or `None` (one-shot)
- `group_key: Optional[str]` — groups notifications under a single stack in the shade (e.g. `"trebnic_tasks"`)
- `color: Optional[str]` — hex color for the notification icon/header tint (e.g. `"#4a9eff"`)
- `style: Optional[BigTextStyle]` — `BigTextStyle(text=body)` makes body expandable instead of truncated to ~2 lines
- `icon: Optional[str]` — custom small icon resource name (defaults to app icon)
- `sound: Optional[str]` — custom sound resource name
- `progress: Optional[dict]` — `{"max": 100, "current": 50, "indeterminate": False}` for progress bar notifications

**Notification ID scheme (digest model)**: Fixed IDs — `9000` (morning digest), `9001` (evening preview), `9002` (overdue nudge). Timer complete uses task-specific IDs.

**cleanup() must NOT cancel alarms**: AlarmManager alarms persist through app close. `reschedule_digests()` re-syncs on next startup.

## Required permissions (pyproject.toml)

```toml
[tool.flet.android.permission]
"android.permission.POST_NOTIFICATIONS" = true
"android.permission.SCHEDULE_EXACT_ALARM" = true
"android.permission.RECEIVE_BOOT_COMPLETED" = true
```

## Required BroadcastReceivers (AndroidManifest.xml)

```xml
<receiver android:exported="false"
    android:name="com.dexterous.flutterlocalnotifications.ScheduledNotificationReceiver" />
<receiver android:exported="false"
    android:name="com.dexterous.flutterlocalnotifications.ScheduledNotificationBootReceiver">
    <intent-filter>
        <action android:name="android.intent.action.BOOT_COMPLETED" />
        <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
        <action android:name="android.intent.action.QUICKBOOT_POWERON" />
        <action android:name="com.htc.intent.action.QUICKBOOT_POWERON" />
    </intent-filter>
</receiver>
```

**IMPORTANT**: `flet build apk` regenerates `AndroidManifest.xml` every time. Re-add these receivers after each clean build.

## Flet extension API cheat sheet

| Concept | Python | Dart |
|---------|--------|------|
| Non-visual service | `ft.Service` | `FletService` subclass |
| Register type | `@ft.control("type_name")` | `createService(Control control)` |
| Call Dart from Python | `await self._invoke_method("name", args)` | `control.addInvokeMethodListener(callback)` |
| Call Python from Dart | `on_event` handler | `control.triggerEvent("name", data)` |

## Dart-side patterns

- **Completer pattern is mandatory**: `FletService.init()` is sync but plugin init is async. Without a Completer, `request_permissions` races against init.
- **Debounce tap callback**: Samsung OneUI fires `onDidReceiveNotificationResponse` immediately on foreground show. Ignore callbacks within 3s.
- **Explicit channel creation**: Call `createNotificationChannel()` after init. Don't rely on implicit creation — silently fails on some OEMs.
- **Inline permission check**: Check `areNotificationsEnabled()` before every `show()`. Android 13+ silently drops notifications without permission.
- **Return real results**: Return `"ok"` / `"error:not_initialized"` / `"error:no_permission"` / `"error:show_failed:..."`.

## Desugaring required

`flutter_local_notifications` v19+ needs in `build.gradle.kts`:
- `isCoreLibraryDesugaringEnabled = true` in `compileOptions{}`
- `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")` in `dependencies{}`

## Debugging

```bash
adb logcat -s "TrebnicNotifications:*"
```

If Dart logs show success but no notification appears, it's OS-level (DND, battery optimization, OEM restrictions).
