# Android notification fix

## Problem

Notifications were silently failing on Android. The UI reported "Notification sent" but nothing appeared. Zero Dart logging made it impossible to diagnose.

## What actually fixed it

### 1. Stale `build/lib/` in the Flet extension (the real blocker)

All Dart code changes were invisible for multiple builds because `flet build apk` was packaging old code from `flet_local_notifications/build/lib/` instead of `src/`. Editing source files had zero effect on the APK.

**Fix**: Delete `flet_local_notifications/build/` before building. Use `pip install -e` (editable) so the package points to `src/` directly. Also manually copy updated Dart files to `trebnic/build/flutter-packages/flet_local_notifications/` since the Flutter build depends on that directory.

**Build procedure**:
```bash
rm -rf flet_local_notifications/build/
pip install -e flet_local_notifications/
cp -r flet_local_notifications/src/flutter/flet_local_notifications/* \
      trebnic/build/flutter-packages/flet_local_notifications/
cd trebnic && flet build apk
```

### 2. Explicit notification channel creation

Android 8+ (API 26) requires notification channels. The old code relied on implicit creation during `show()`, which silently fails on some OEMs. Added `_createNotificationChannel()` after successful `_plugin.initialize()`.

### 3. Inline permission check before `show()`

Android 13+ (API 33) requires `POST_NOTIFICATIONS` runtime permission. Without it, `_plugin.show()` completes without error but the OS silently drops the notification. Added `areNotificationsEnabled()` check inside `_showNotification()` — if not enabled, calls `requestNotificationsPermission()` right there. This is the only reliable place to do it because it runs at the exact moment a notification would be delivered.

### 4. Result propagation instead of hardcoded `"ok"`

The old `_onMethod()` always returned `"ok"` regardless of what happened. Now `_showNotification()` returns structured strings (`"ok"`, `"error:not_initialized"`, `"error:no_permission"`, `"error:show_failed:..."`), and Python checks the result instead of assuming success.

### 5. Logging

Added `_log()` helper using `print()` (logcat in release) + `developer.log()` (DevTools in debug) with tag `TrebnicNotifications`. Every method logs entry, result, and errors with stack traces.

## Files changed

| File | What changed |
|------|-------------|
| `notifications_service.dart` | Logging, channel creation, permission check before show, result propagation, `check_permissions` method |
| `flet_local_notifications.py` | Typed `str` returns, `check_permissions()` method |
| `notification_service.py` | Check Dart result in `_deliver_extension_notification`, check status before requesting in `request_permission`, log `test_notification` result |

## Debugging

```bash
adb logcat -s "TrebnicNotifications:*"
```

If logs show `_plugin.show() completed successfully` but no notification appears, the issue is at OS level (DND, battery optimization, OEM restrictions, app notifications disabled in Android settings).
