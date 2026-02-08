# 📝 Tech Note: Flet Mobile APK Build Issues

## 🚩 The Problem
After migrating from `sqlite3` to `aiosqlite` for async database operations, the app worked on PC but crashed on Android with `ModuleNotFoundError: No module named 'aiosqlite'`.

## ❌ What DIDN'T Work & Why

| Attempt | Why It Failed |
| :--- | :--- |
| **Adding to `pyproject.toml` only** | Flet mobile builds use `pip` directly with `requirements.txt`, NOT Poetry/pyproject.toml |
| **`requirements.txt` in project root** | Must be in the **same directory** as `main.py` (the Flet entry point) |
| **Running `flet build apk` from project root** | Flet looks for `main.py` in current directory; got "main.py not found" error |
| **Including pandas in requirements** | `pandas>=2.3.3` doesn't exist for Android arm64; only 2.0.3 and 2.2.3 available |
| **`adb install -r` (replace)** | Old app data/cache persisted; module still not found despite being in new APK |
| **Running flet build without `PYTHONUTF8=1`** | Rich library crashed with `UnicodeEncodeError: 'charmap' codec can't encode character '\u25cf'` |

## ✅ What Actually Worked

### 1. Set UTF-8 Mode for Windows Console
```bash
PYTHONUTF8=1 flet build apk
```
Without this, the Rich library (used by Flet CLI) crashes on Windows with Unicode errors.

### 2. Create `requirements.txt` Next to `main.py`
```
# trebnic/trebnic/requirements.txt (same folder as main.py)
flet>=0.80.0
aiosqlite>=0.19.0,<1.0.0
```
> **Note:** This was updated from `flet>=0.28.3,<0.29.0` after migration to Flet 0.80.

### 3. Run Build FROM the App Source Directory
```bash
cd trebnic/trebnic    # Where main.py lives
PYTHONUTF8=1 flet build apk
```

### 4. Remove Unused/Incompatible Dependencies
```bash
# Check if package is actually used
grep -r "import pandas" *.py
# If no results → remove from requirements.txt
```

### 5. FULL UNINSTALL Before Reinstall (Critical!)
```bash
# This is NOT enough:
adb install -r build/apk/app-release.apk  # ❌ Old cached data persists

# Do this instead:
adb uninstall com.flet.trebnic            # ✅ Full uninstall first
adb install build/apk/app-release.apk     # ✅ Clean install
```

## 🔍 Root Cause Analysis

### Why `-r` (Replace) Wasn't Enough
Android caches the app's extracted Python environment in `/data/user/0/com.flet.trebnic/files/flet/app/`. When using `adb install -r`, this cache persists from the previous installation. The old (broken) Python environment is reused instead of the new one with aiosqlite.

A full uninstall clears this cache, forcing the app to extract fresh files on first launch.

### Two Separate Dependency Systems
```
┌─────────────────────────────────────────────────────────┐
│  PC Development          │  Mobile Build               │
├─────────────────────────────────────────────────────────┤
│  pyproject.toml          │  requirements.txt           │
│  Poetry / pip            │  pip (inside Flet packager) │
│  Any Python package      │  Only pure Python or        │
│                          │  packages with Android      │
│                          │  wheels                     │
└─────────────────────────────────────────────────────────┘
```

## 🧠 Key Insights

1. **Full Uninstall Required:** When debugging mobile builds, ALWAYS do `adb uninstall <package>` before reinstalling. The `-r` flag preserves cached data that can mask fixes.

2. **requirements.txt Location:** Must be in the **exact same directory** as your `main.py` entry point.

3. **PYTHONUTF8=1:** Mandatory on Windows to avoid Rich library Unicode crashes.

4. **Verify Packages in Build:** Check `build/site-packages/arm64-v8a/` to confirm your dependencies were actually bundled.

5. **aiosqlite Works:** Pure Python packages like aiosqlite work perfectly on Android. The issue is usually build/install process, not the package itself.

6. **Minimal Dependencies:** Only include what you actually use. Check with `grep` before adding to requirements.

## 💡 Quick Reference: Complete Build & Deploy

```bash
# 1. Navigate to app source directory
cd trebnic/trebnic

# 2. Build APK (with UTF-8 mode for Windows)
PYTHONUTF8=1 flet build apk

# 3. Verify aiosqlite was bundled
ls build/site-packages/arm64-v8a/ | grep aiosqlite

# 4. FULL uninstall old app
D:/Android/Sdk/platform-tools/adb.exe uninstall com.flet.trebnic

# 5. Clean install
D:/Android/Sdk/platform-tools/adb.exe install build/apk/app-release.apk
```

## 📁 Correct Project Structure

```
trebnic/
├── pyproject.toml              # PC dependencies (Poetry) - NOT used for mobile
└── trebnic/
    ├── main.py                 # Flet entry point
    ├── requirements.txt        # Mobile dependencies - MUST be here
    ├── app.py
    ├── config.py
    ├── database.py
    └── build/
        ├── apk/
        │   └── app-release.apk
        └── site-packages/      # Verify your deps are here
            └── arm64-v8a/
                ├── aiosqlite/  # ✅ Should exist
                └── flet/
```
