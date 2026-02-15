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

## Extension structure

```
flet_local_notifications/
├── pyproject.toml
└── src/
    ├── flet_local_notifications/
    │   ├── __init__.py
    │   └── flet_local_notifications.py   # Python ft.Service subclass
    └── flutter/
        └── flet_local_notifications/
            ├── pubspec.yaml              # depends on flutter_local_notifications ^19.0.0
            └── lib/
                ├── flet_local_notifications.dart
                └── src/
                    ├── extension.dart             # class MUST be named "Extension"
                    └── notifications_service.dart
```

**Extension pyproject.toml critical rules**:
- Do NOT add `[tool.setuptools.packages.find]` — it overrides namespace discovery
- No `__init__.py` in `flutter/` dirs
- `[tool.setuptools.package-data]` must include `"flutter.flet_local_notifications" = ["**/*"]`

**Service auto-registration**: Just instantiate `FletLocalNotifications()`. Do NOT add to `page.overlay` or `page.services`. It auto-registers via `Service.init()`.

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

## Migration pitfalls

### Extension inside source_dir gets raw-copied
Place extension at project root (sibling of source_dir), not inside it. `exclude` in pyproject.toml does NOT pass `--exclude` to serious_python.

### `flet build` only reads pyproject.toml from CWD
No directory traversal. If pyproject.toml is in the parent dir, all `[tool.flet.*]` settings are ignored. Use `requirements.txt` in source_dir.

### Commas in version specs break serious_python on Windows
`dart run serious_python:main ... -r "pkg>=x.y,<z.0"` fails. Use `requirements.txt` (pip reads it directly).

### Stale `build/lib/` in extension (CRITICAL)
`flet build apk` packages Dart code from `build/lib/` (if it exists) instead of `src/`. Edits to `src/` have zero effect on the APK.

**Fix**: Delete `flet_local_notifications/build/` before building. Use `pip install -e` (editable).

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
# Ensure extension source is current
rm -rf flet_local_notifications/build/
pip install -e flet_local_notifications/
cp -r flet_local_notifications/src/flutter/flet_local_notifications/* \
      trebnic/build/flutter-packages/flet_local_notifications/

# Build and install
cd trebnic && flet build apk
adb install -r build/apk/app-release.apk
```

## Debugging

```bash
adb logcat -s "TrebnicNotifications:*"
```

If Dart logs show `_plugin.show() completed successfully` but no notification appears, it's an OS-level issue (DND, battery optimization, OEM restrictions, app notification settings).
