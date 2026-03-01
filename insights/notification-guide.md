# Notification implementation guide

## Why plyer/pyjnius don't work on Android

Both depend on Kivy's `PythonActivity`, which doesn't exist in Flet (Flutter-based, not Kivy-based). Python has zero direct access to Android Java APIs in Flet.

| Dead end | Why |
|----------|-----|
| `plyer` on Android | Uses Pyjnius/Kivy's PythonActivity |
| `android-notify` | Same Pyjnius dependency |
| `flet_notifications` (Bbalduzz) | Abandoned, broken imports on 0.80+ |
| Any Pyjnius approach | Flet's Python is sandboxed from Android APIs |

## Architecture

```
Python (ft.Service)
  -> _invoke_method("show_notification", args)
    -> Flet protocol (Python <-> Dart)
      -> FletService subclass in Dart
        -> flutter_local_notifications plugin
          -> Android NotificationManager
```

## Extension

The extension is published as `flet-android-notifications` on PyPI (v0.2.0+). No local extension directory needed.

**Service auto-registration**: Just instantiate `FletAndroidNotifications()`. Do NOT add to `page.overlay` or `page.services`. It auto-registers via `Service.init()`.

### 0.2.0 changes (scheduled notifications)

0.1.0 only supported `show_notification()` (immediate). 0.2.0 adds:

| Method | Purpose |
|--------|---------|
| `schedule_notification()` | Schedule via AlarmManager/`zonedSchedule()`. Fires even if app is killed or device restarts. |
| `request_exact_alarm_permission()` | Android 14+ requires explicit consent for exact alarms. |
| `cancel(notification_id)` | Cancel a specific scheduled notification. |
| `cancel_all()` | Cancel all active notifications. |

**`schedule_notification()` key parameters:**
- `scheduled_time: datetime` — naive = local time, aware = converted to UTC internally
- `schedule_mode: str` — one of `"alarm_clock"`, `"exact"`, `"exact_allow_while_idle"`, `"inexact"`, `"inexact_allow_while_idle"` (default). Exact modes require `SCHEDULE_EXACT_ALARM` permission.
- `match_date_time_components: Optional[str]` — for recurring: `"time"` (daily), `"day_of_week_and_time"` (weekly), `"day_of_month_and_time"` (monthly), `"date_and_time"` (yearly), or `None` (one-shot, default).

**Architecture change**: On Android, `_reschedule_for_task()` now calls `schedule_notification()` directly instead of saving to DB + polling. The OS delivers notifications via AlarmManager. The 60-second polling loop only runs on desktop (plyer).

**Notification ID scheme**: `task_id * 10 + slot_index` where slot 0-4 maps to each reminder time (1h, 6h, 12h, 24h, custom). This allows canceling all reminders for a task without tracking state.

**Required permissions** (pyproject.toml):
```toml
[tool.flet.android.permission]
"android.permission.POST_NOTIFICATIONS" = true
"android.permission.SCHEDULE_EXACT_ALARM" = true
"android.permission.RECEIVE_BOOT_COMPLETED" = true
```

`RECEIVE_BOOT_COMPLETED` is needed so `flutter_local_notifications` can re-register alarms after device reboot.

**Required BroadcastReceivers** (AndroidManifest.xml):

`schedule_notification()` relies on two BroadcastReceivers that must be declared inside the `<application>` tag. Without them, scheduled alarms are silently lost when the app is killed or the device restarts.

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

**IMPORTANT**: `flet build apk` regenerates `AndroidManifest.xml` from the template every time. After each clean build, re-add these receivers to `build/flutter/android/app/src/main/AndroidManifest.xml` before the final APK build step, or keep the modified manifest and only run `flet build apk` when template changes are needed.

**cleanup() must NOT cancel alarms**: The `cleanup()` method must not call `cancel_all()` on Android. AlarmManager alarms need to persist through app close so due reminders fire while the app is not running. `_reschedule_all_tasks()` re-syncs on next startup.

## Flet extension API cheat sheet

| Concept | Python | Dart |
|---------|--------|------|
| Non-visual service | `ft.Service` | `FletService` subclass |
| Register type | `@ft.control("type_name")` | `createService(Control control)` |
| Call Dart from Python | `await self._invoke_method("name", args)` | `control.addInvokeMethodListener(callback)` |
| Call Python from Dart | `on_event` handler | `control.triggerEvent("name", data)` |

## Dart-side patterns

**Completer pattern is mandatory**: `FletService.init()` is synchronous but plugin init is async. Without a Completer, `request_permissions` can race against init and `resolvePlatformSpecificImplementation` returns null silently.

**Debounce tap callback**: On Samsung OneUI, `onDidReceiveNotificationResponse` fires immediately when a notification is shown while in foreground. Ignore callbacks within 3 seconds of show.

**Explicit channel creation**: Call `createNotificationChannel()` after init. Don't rely on implicit creation during `show()` — silently fails on some OEMs.

**Inline permission check**: Check `areNotificationsEnabled()` before every `show()`. On Android 13+, `_plugin.show()` succeeds without error even when permission is missing — the OS silently drops the notification. Request permission right there if needed.

**Return real results**: Don't hardcode `return "ok"`. Return `"ok"` / `"error:not_initialized"` / `"error:no_permission"` / `"error:show_failed:..."` so Python can detect failures.

## Historical fixes

### `exclude` in pyproject.toml silently killed the Flutter plugin

A stale `[tool.flet.app] exclude = ["flet_android_notifications"]` told `flet build` to skip the Flutter extension registration. The Python package was still bundled (pip installs into `libpythonsitepackages.so`, which `exclude` doesn't affect), so Python code ran without errors. But the Dart bridge had nothing on the other end — calls silently vanished.

**Lesson:** `exclude` in `[tool.flet.app]` affects Flutter extension registration, not Python bundling. If you exclude a package with a Flutter plugin, the Python side works but native side is silently disconnected.

### `test_notification()` bypassed permission request

On Android 13+ (API 33), `POST_NOTIFICATIONS` is a runtime permission. Without it, the OS silently drops notifications — `show_notification()` returns `"ok"` but nothing appears. Fixed by adding `request_permission()` call before sending in `test_notification()`.

## Migration pitfalls

### Extension inside source_dir gets raw-copied
Place extension at project root (sibling of source_dir), not inside it. `exclude` in pyproject.toml does NOT pass `--exclude` to serious_python.

### `flet build` only reads pyproject.toml from CWD
No directory traversal. If pyproject.toml is in the parent dir, all `[tool.flet.*]` settings are ignored. Use `requirements.txt` in source_dir.

### Commas in version specs break serious_python on Windows
`dart run serious_python:main ... -r "pkg>=x.y,<z.0"` fails. Use `requirements.txt` (pip reads it directly).

### archive 4.0.7 flat extraction bug
`serious_python` extracts `app.zip` to flat files with backslash names on Android. Fixed by `_fix_flat_extraction()` in `main.py` that detects and restructures on first launch.

### Desugaring required
`flutter_local_notifications` v19+ needs core library desugaring in `build.gradle.kts`:
- `isCoreLibraryDesugaringEnabled = true` in `compileOptions{}`
- `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")` in `dependencies{}`

### Native C deps unavailable for Android
`cryptography`, `argon2-cffi` don't have Android wheels on Flet's PyPI. Exclude from Android requirements.txt.

## Build procedure

```bash
# flet-android-notifications is installed from PyPI automatically
cd trebnic && flet build apk
# Full uninstall first — -r preserves cached Python env which masks fixes
adb uninstall ai.stoica.trebnic
adb install build/apk/app-release.apk
```

## Debugging

```bash
adb logcat -s "TrebnicNotifications:*"
```

If Dart logs show `_plugin.show() completed successfully` but no notification appears, it's an OS-level issue (DND, battery optimization, OEM restrictions, app notification settings).
