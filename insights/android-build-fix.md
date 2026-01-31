# Android build fix

**Goal**: Make the app work on Android

## Starting point
- **Error**: `ModuleNotFoundError: No module named 'flet'`
- **Likely origin**: Started when adding notification functionality (commits after `08ab2ea`)
- Notification feature required new libraries (plyer, pyjnius, android-notify, etc.)
- Gemini Pro 3 attempted fixes that introduced bad config (flet==0.80.4 doesn't exist)

## Investigation

### Git history analysis
- Last known working commit: `08ab2ea` ("Fixed android bug")
- 12 commits since then have modified config files

### Key differences: working vs broken

**Working state (08ab2ea):**
- Root `pyproject.toml`: `flet[build] (>=0.28.3,<0.29.0)`
- `trebnic/requirements.txt`: simple 2 lines (flet + aiosqlite)
- NO `trebnic/pyproject.toml`
- NO `trebnic/poetry.lock`

**Current broken state:**
- Root `pyproject.toml`: same flet version + many new deps
- `trebnic/pyproject.toml`: EXISTS with `flet = "^0.80.4"` (NON-EXISTENT VERSION!)
- `trebnic/requirements.txt`: has `flet==0.80.4` (WRONG!)
- `trebnic/poetry.lock`: EXISTS (confuses build?)

### Suspected root cause
`flet==0.80.4` does not exist. Current flet is ~0.28.x. This typo/hallucination causes "no module named flet".

### Key files to watch
- `pyproject.toml` (root)
- `trebnic/pyproject.toml` (should probably not exist)
- `trebnic/requirements.txt`

---

## Steps tried

| # | Action | Result |
|---|--------|--------|
| 1 | Deleted `trebnic/pyproject.toml` and `trebnic/poetry.lock` (spurious files) | - |
| 1 | Reset `trebnic/requirements.txt` to working version (flet>=0.28.3, aiosqlite) | **PROGRESS**: APK builds, installs. "No module flet" FIXED. New issue: white screen on mobile |
| 2 | `adb logcat -s python:*` | No output - unexpected, filter may be wrong |
| 2 | `adb logcat *:E` + grep | Too much noise, not useful |
| 2 | Analyzed mobile_log.txt | Python loads (`serious_python CPython loaded`) but NO traceback visible. App dies silently |
| 2 | Found: TWO package names in logs: `com.flet.trebnic` AND `ai.stoica.trebnic` - possibly old build conflict |
| 3 | Uninstalled `com.flet.trebnic` | Success |
| 3 | Uninstalled `ai.stoica.trebnic` | Failed (internal error) - uninstall manually on phone |
| 3 | `flet build apk` | FAILED: Gradle file lock on lint cache jar |
| 3 | `taskkill /F /IM java.exe` then rebuild | SUCCESS - APK builds |
| 3 | Installed and tested | White screen persists |
| 4 | Analyzed mobile_log3.txt | Python initializes (`Py_Initialize()`) but NO output after - silent failure |
| 4 | Added debug prints to main.py | PROGRESS: `flet has no attribute __version__` - flet imports but is different on mobile |
| 4 | Removed `__version__` check | No TREBNIC output in logcat - print() not reaching logs |
| 5 | Try logging module + stderr | No output - Python stdout/stderr not reaching logcat |
| 6 | Minimal main.py (just `ft.Text("TREBNIC WORKS!")`) | **CRITICAL**: Works on PC, WHITE SCREEN on mobile |
| 6 | This proves: issue is NOT our app code - it's Flet mobile runtime itself |

### Key finding
- Minimal 9-line Flet app works perfectly on desktop
- Same code = white screen on Android
- Desktop shows: `app() is deprecated since version 0.80.0` (desktop has 0.80.x)
- Mobile requirements.txt has `flet>=0.28.3,<0.29.0`
- **Possible cause**: Version mismatch between flet build tool (0.80.x) and requirements.txt (0.28.x)

| 7 | Updated requirements.txt to `flet>=0.80.0` to match build tool | Still white screen |
| 8 | Found root pyproject.toml still had `flet[build] (>=0.28.3,<0.29.0)` - updated to 0.80.0 | Part of fix |
| 8 | Commented out `[tool.flet.android] dependencies` (pyjnius, android-notify) | **THIS WAS THE FIX** |

---

## Solution

### Root cause
`[tool.flet.android] dependencies = ["pyjnius", "android-notify==1.60.8.dev0"]` in `pyproject.toml` was breaking the mobile build. These dependencies (added for notification functionality) prevented the app from running on Android.

### The fix
1. Updated `flet` version from `>=0.28.3,<0.29.0` to `>=0.80.0` in both:
   - `pyproject.toml` (root)
   - `trebnic/requirements.txt`
2. **Removed/commented out** the `[tool.flet.android] dependencies` section

### Why it broke
- `android-notify==1.60.8.dev0` is a dev version that likely doesn't exist or has compatibility issues
- `pyjnius` may have conflicts with how flet 0.80.x packages Android apps
- These deps caused silent failure - Python initialized but couldn't run the app code

### Lessons learned
- Always test after adding Android-specific dependencies
- Dev versions (`.dev0`) are unstable and shouldn't be used in production
- When mobile builds fail silently, strip to minimal test case first

---

## Build commands

```cmd
# Build APK
flet build apk

# Install on device
D:\Android\Sdk\platform-tools\adb.exe install -r build\apk\app-release.apk
```

### Gradle file lock fix
When gradle daemon holds files:
```cmd
taskkill /F /IM java.exe
rmdir /s /q build
rmdir /s /q %USERPROFILE%\.gradle\caches\transforms-*
flet build apk
```
