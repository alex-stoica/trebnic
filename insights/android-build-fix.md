# Android build fix

## Root cause

`[tool.flet.android] dependencies = ["pyjnius", "android-notify==1.60.8.dev0"]` in `pyproject.toml` caused silent failure on Android. Python initialized but the app code never ran.

- `android-notify==1.60.8.dev0` is a dev version that doesn't resolve properly
- Removing it fixed the white screen; `pyjnius` was kept (needed for notifications)

## The fix

1. Updated flet from `>=0.28.3,<0.29.0` to `>=0.80.0` in `pyproject.toml` and `requirements.txt`
2. Removed `android-notify` from `[tool.flet.android] dependencies` (kept `pyjnius` only)

## Lessons learned

- Always test after adding Android-specific dependencies
- Dev versions (`.dev0`) are unstable - don't use in production
- When mobile builds fail silently, strip to a minimal `ft.Text("hello")` test case first
- Version mismatch between flet build tool and requirements.txt causes white screen

## Gradle file lock fix

When the Gradle daemon holds files and the build fails:
```cmd
taskkill /F /IM java.exe
rmdir /s /q build
flet build apk
```
