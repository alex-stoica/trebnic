# Android notifications in Flet - what we tried

## The goal
Get "Test notification" button to show a notification on Android (Samsung phone).

## Initial state
- Button showed "only available on mobile" on both desktop AND Android
- Backend detected as `PLYER_FALLBACK` or `NONE` on Android

## Attempts and results

### 1. Fix the desktop check logic
**Change:** Only block when `backend == NONE`, not when `PLYER_FALLBACK`
**Result:** Now shows "Notifications are not available on this device" - backend is `NONE`

### 2. Use Flet's "built-in" notifications
**Assumption:** Flet 0.21+ has `ft.Notification` and `page.send_notification()`
**Reality:** These don't exist in Flet 0.28. Checked with:
```python
python -c "import flet as ft; print([x for x in dir(ft) if 'notif' in x.lower()])"
# Output: []
```
**Result:** Failed - API doesn't exist

### 3. Use android_notify package
**Setup:**
- Added to `pyproject.toml`:
```toml
[tool.flet.android]
dependencies = ["pyjnius", "android-notify==1.60.8.dev0"]
```
- Added POST_NOTIFICATIONS permission

**Problem:** Running `flet build apk` from `trebnic/trebnic/` doesn't read `pyproject.toml` from parent directory

**Fix attempt:** Created `trebnic/trebnic/pyproject.toml` with Android settings

**Result:** Build error: `Unable to load extension: No module named 'dateutil'`

### 4. Add python-dateutil dependency
**Change:** Added `python-dateutil>=2.8.0` to `requirements.txt`
**Result:** Same error persists

### 5. Switch to plyer (simpler package)
**Changes:**
- Removed android-notify from pyproject.toml
- Added `plyer>=2.1.0` to requirements.txt
- Updated notification service to use PLYER as primary backend

**Result:** Same `dateutil` error - seems unrelated to our changes, possibly cached or from flet tooling

## Key learnings

| Topic | Learning |
|-------|----------|
| **Dependency systems** | Mobile builds use `requirements.txt`, NOT `pyproject.toml` for Python deps |
| **Android deps** | `pyproject.toml` `[tool.flet.android]` section is for native Android deps (pyjnius, etc.) |
| **Build location** | Must run `flet build apk` from directory containing `main.py` |
| **Cache issues** | Full uninstall (`adb uninstall <pkg>`) required to clear cached Python env |
| **Flet 0.28** | Does NOT have built-in notification support - no `ft.Notification` class |
| **android_notify** | Requires pyjnius + dateutil - complex dependency chain, build issues |
| **plyer** | Should work but may have its own issues on Android |

## The dateutil error
```
Unable to load extension: No module named 'dateutil'
```
This error persists even after removing android-notify. Possible causes:
- Cached build artifacts in `build/` directory
- Dependency of plyer or flet itself
- Flet build tooling issue

## What to try next
1. Clean build directory: `rm -rf build/` then rebuild
2. Check if plyer requires dateutil: `pip show plyer` and check dependencies
3. Try without any notification package - just to verify build works
4. Consider Firebase Cloud Messaging or OneSignal as alternatives (requires native integration)

## Current state of notification_service.py
- `NotificationBackend` enum: `PLYER`, `ANDROID_NATIVE`, `NONE`
- Backend detection prioritizes `PLYER_AVAILABLE`
- plyer added to requirements.txt
- android-notify removed

## Files modified
- `trebnic/trebnic/requirements.txt` - added plyer
- `trebnic/trebnic/pyproject.toml` - created for Android settings
- `trebnic/services/notification_service.py` - refactored backends
- `trebnic/ui/pages/profile_view.py` - fixed desktop check
- `trebnic/i18n.py` - added translation keys
