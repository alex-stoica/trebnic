# Notification extension migration — current status

## What was done this session

### 1. Fixed "No module named 'services'" crash on Android

**Root cause**: The `archive` Dart package v4.0.7 (used by `serious_python` to extract `app.zip` on Android at runtime) has a bug. It extracts zip files into **flat files with backslash names** instead of proper subdirectories. For example, `services/auth.py` in the zip becomes a single file named `services\auth.py` in the root directory. The `services/` directory is never created.

**Evidence** (from logcat diagnostics via `subprocess.run(["log", "-t", "TREBNIC", msg])`):
```
services: exists=False isdir=False isfile=False
models: exists=False isdir=False isfile=False
ui: exists=False isdir=False isfile=False
main.py: exists=True isdir=False isfile=True
[9] 'models\\entities.py'    ← flat file with backslash in name
[10] 'models\\__init__.py'
```

**Fix**: Added `_fix_flat_extraction()` in `main.py` that runs before any imports on Android. It detects entries with `\` in filenames, creates proper subdirectories with `os.makedirs()`, and moves files with `shutil.move()`.

### 2. Diagnosed the extraction bug

- Verified the zip file (`app.zip`) has **correct forward-slash paths** — no backslashes
- Read the archive 4.0.7 Dart source code (`extract_archive_to_disk.dart`)
- The code SHOULD work (uses `File.createSync(recursive: true)`) but doesn't on Android
- Archive 3.6.1 had `name = name.replaceAll('\\', '/')` in `ArchiveFile` constructor — 4.0.7 removed this
- Did NOT find the exact root cause in the Dart code; the Python workaround was applied instead

### 3. Fixed desugaring patch being lost

When `site-packages` and `.hash` directories are cleaned, the flet build template regenerates from scratch, wiping the desugaring patch in `build.gradle.kts`. Had to re-apply:
```kotlin
// In compileOptions:
isCoreLibraryDesugaringEnabled = true

// In dependencies:
coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
```

### 4. Changed flet extension dependency

Changed `flet_local_notifications/pyproject.toml` from `flet>=0.80.5` to `flet>=0.80.0` to prevent pulling a newer flet into site-packages than the template version (0.80.4). However, pip still resolves to 0.80.5 (latest on pypi.flet.dev).

### 5. Added Android logcat logging infrastructure

Added to `main.py`:
- `LogcatHandler` — a `logging.Handler` that forwards WARNING+ messages to logcat via `subprocess.run(["log", "-t", "TREBNIC_PY", msg])`
- `sys.excepthook` override to log unhandled exceptions to logcat
- All use `subprocess.run()` instead of `os.system()` to avoid shell quoting issues with Python repr output

## Current state

### What works
- APK builds successfully (66.9MB) with extension discovered in `main.dart` and `pubspec.yaml`
- Flat extraction fix works — app starts, lock screen appears, PIN entry works
- After PIN unlock, the app shows "Notification sent (flet extension)" when tapping "Test notification" in profile settings
- Python process stays alive (no `Py_Finalize()` in logcat)

### What doesn't work
1. **No actual Android notification appears** — "Notification sent (flet extension)" text confirms the Python→Dart method invocation path works, but the Flutter `flutter_local_notifications` plugin isn't showing a real OS notification
2. **White screen after PIN unlock** — the user reported the app goes white after entering the PIN (lock screen renders fine, post-unlock UI doesn't). This was being investigated when the session was interrupted

## Files modified this session

| File | Change |
|------|--------|
| `trebnic/main.py` | Added `_fix_flat_extraction()`, logcat logging, excepthook |
| `flet_local_notifications/pyproject.toml` | `flet>=0.80.5` → `flet>=0.80.0` |
| `insights/notification_extension_migration.md` | Added issues #8 (flat extraction), updated takeaways |
| `build/flutter/android/app/build.gradle.kts` | Re-applied desugaring patch (lost after clean rebuild) |

## Next steps

### 1. Fix "no real notification" — Dart extension likely needs Android channel setup

The `flutter_local_notifications` plugin requires:
- **Notification channel creation** on Android 8+. Check `notifications_service.dart` in the extension's Dart code — ensure `_plugin.initialize()` is called with `AndroidInitializationSettings` and a channel is created before `_plugin.show()`.
- **POST_NOTIFICATIONS permission** on Android 13+ (API 33). The Python side calls `request_permissions()`, but check if the Dart side actually requests it via Android's permission system.
- **Check Dart logcat output** — look for errors from `flutter_local_notifications` plugin. The Dart `NotificationsService._onMethod` in `notifications_service.dart` receives the `show_notification` call; verify it's calling `_plugin.show()` with correct `AndroidNotificationDetails`.

### 2. Debug the white screen after unlock

This is likely one of:
- **Missing `cryptography`/`argon2-cffi`**: The database has encrypted task titles/notes from desktop. On Android, `CRYPTO_AVAILABLE=False` so decryption returns garbage or fails silently → UI renders blank or crashes.
  - **Quick test**: Disable encryption on desktop, delete encrypted data, rebuild and test
  - **Proper fix**: Include `cryptography==43.0.1` (the Android-available version from pypi.flet.dev) in `requirements.txt`
- **UI component error**: Some Flet 0.80 API used in the task view might fail on Android. The logcat `LogcatHandler` should now capture WARNING+ Python logs.
- **Database path issue**: Check that `db.DB_PATH` resolves correctly on Android (should use `FLET_APP_STORAGE_DATA` env var).

### 3. Consider pinning `cryptography==43.0.1` for Android

Instead of excluding cryptography entirely, try:
```
cryptography==43.0.1
```
in `requirements.txt`. Version 43.0.1 IS available on Flet's PyPI for Android. This would restore encryption support on Android.

### 4. Build commands reminder

```bash
cd trebnic/trebnic

# Build (from source_dir — uses requirements.txt):
PYTHONUTF8=1 poetry run flet build apk -v

# If desugaring patch was lost (check build.gradle.kts first):
# Edit build/flutter/android/app/build.gradle.kts
# - compileOptions { isCoreLibraryDesugaringEnabled = true }
# - dependencies { coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4") }
# Then rebuild

# Install:
D:\Android\Sdk\platform-tools\adb.exe uninstall com.flet.trebnic
D:\Android\Sdk\platform-tools\adb.exe install build\apk\app-release.apk

# Capture logs after opening:
adb logcat -s "TREBNIC:*" "TREBNIC_PY:*" "flutter:*"
```

### 5. Investigate archive 4.0.7 bug properly (low priority)

The `_fix_flat_extraction()` workaround works but adds startup latency. A proper fix would be:
- Pin `archive: 3.6.1` in the build's `pubspec.yaml` dependency overrides
- Or file an issue on the `archive` Dart package repo
- Or patch `extractArchiveToDisk()` to create parent directories explicitly
