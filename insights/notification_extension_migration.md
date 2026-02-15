# Notification extension migration — what worked and what didn't

## Goal
Replace broken pyjnius Android notification backend with a Flet extension (`flutter_local_notifications`).

## What failed

### 1. Extension inside source_dir gets raw-copied (not pip-installed)
**Problem**: Placed `flet_local_notifications/` extension package inside `trebnic/trebnic/` (the `source_dir`). The `[tool.flet.app] exclude = ["flet_local_notifications"]` setting does NOT pass `--exclude` to serious_python. The directory was raw-copied into `app.zip` with its `src/` layout, so Python found `flet_local_notifications/` but no `__init__.py` at the root — import failed silently.

**Evidence**: `app.zip` contained `flet_local_notifications/pyproject.toml`, `flet_local_notifications/src/flet_local_notifications/__init__.py` — wrong structure for Python import.

**Fix**: Move extension to project root (sibling of source_dir). Install via pip from requirements.txt.

### 2. dev_packages / pyproject.toml NOT READ when building from source_dir
**Problem**: `flet build apk` is run from `trebnic/trebnic/` (the source_dir). The `python_app_path` defaults to `.` (cwd). `load_pyproject_toml()` looks for `pyproject.toml` ONLY in `python_app_path` — no directory walk-up. Since `pyproject.toml` is at `trebnic/` (project root, one level up), it's NEVER found.

**Result**: All `[tool.flet.*]` settings are ignored: `dev_packages`, `exclude`, `org`, `product`, permissions. The build falls back to `requirements.txt` in the source_dir.

**Key insight**: `flet build` does NOT search parent directories for pyproject.toml. It only checks the exact directory passed as `python_app_path` (defaults to cwd).

**Why it seemed to work**: The build found `requirements.txt` in the source_dir and used that for dependencies. The template defaults (`module = "main"`, no exclude) happened to work.

### 3. Building from project root fails — comma in version specs breaks serious_python on Windows
**Problem**: When running `flet build apk` from the project root (where pyproject.toml IS found), dependencies are passed as individual `-r "pkg>=x.y,<z.0"` args to `dart run serious_python:main`. The comma in version specs like `>=0.19.0,<1.0.0` causes serious_python to fail with "The system cannot find the file specified." on Windows.

**Evidence**: Reproduced manually:
- `dart run serious_python:main package ... -r "flet>=0.80.0"` → SUCCESS
- `dart run serious_python:main package ... -r "aiosqlite>=0.19.0,<1.0.0"` → FAIL
- `dart run serious_python:main package ... -r "aiosqlite>=0.19.0"` → SUCCESS

When using `-r -r -r requirements.txt` (the fallback path), pip reads the file directly and handles commas fine.

**Fix**: Keep dependencies in `requirements.txt` in the source_dir. Run `flet build` from the source_dir (which uses requirements.txt).

### 4. page.services.add() — black screen crash
**Problem**: Called `page.services.add(self._flet_notifications)` to register the service. `page.services` is a `list[Service]`, NOT a set — `add()` throws `AttributeError`, crashing the app at startup (black screen).

**Fix**: Don't manually add to page.services at all. `ft.Service` auto-registers via `Service.init()` → `context.page._services.register_service(self)`.

### 5. Android detection via env var is unreliable
**Problem**: Used `os.environ.get("ANDROID_ROOT")` and `os.path.exists("/system/build.prop")` to detect Android. Unclear if these work inside Flet's Python sandbox on Android (serious_python).

**Fix**: Don't gate the import on Android detection at all. Try importing `flet_local_notifications` unconditionally — it only exists when the extension is installed. On desktop, the import fails gracefully.

### 6. Desugaring patch required for flutter_local_notifications
**Problem**: `flutter_local_notifications` v19.0.0 requires core library desugaring. First Gradle build fails with "library desugaring to be enabled".

**Fix**: Patch `build/flutter/android/app/build.gradle.kts`:
- In `compileOptions{}`: add `isCoreLibraryDesugaringEnabled = true`
- In `dependencies{}`: add `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")`
Then rebuild — the template hash is unchanged so the patch survives.

### 7. cryptography/argon2-cffi unavailable for Android
**Problem**: `cryptography>=46.0.3` is not available for Android on Flet's PyPI. Only v43.0.1 exists. Including it in requirements.txt causes `ERROR: No matching distribution found`.

**Fix**: Exclude native C library dependencies from the Android requirements.txt. These features (encryption) won't work on Android anyway.

### 8. archive 4.0.7 flat extraction bug — "No module named 'services'" on Android
**Problem**: After building and installing on Android, the app crashes with `ModuleNotFoundError: No module named 'services'`. The `services/`, `models/`, `ui/` subdirectories don't exist on the device. Instead, `os.listdir()` returns flat files with backslash names like `'services\\auth.py'` and `'models\\entities.py'`.

**Root cause**: The `archive` Dart package v4.0.7 (used by `serious_python` for extracting `app.zip` on Android) has a bug in `extractArchiveToDisk()`. It skips directory entries at line 111 (`entry.isDirectory && !entry.isSymbolicLink` → `continue`), then uses `OutputFileStream` for files which calls `File.createSync(recursive: true)`. Despite this, the extraction creates flat files with backslash separators instead of proper subdirectories. The zip file itself has correct forward-slash paths (verified with Python's `zipfile.namelist()`).

**Evidence**:
- `os.listdir()` returns entries like `'services\\auth.py'` (flat file with backslash in name)
- `os.path.exists(os.path.join(app_dir, 'services'))` → `False`
- `os.path.isfile(os.path.join(app_dir, 'main.py'))` → `True` (root-level files are fine)
- The zip has 132 entries; on device, 112 flat files (all non-directory entries)

**Diagnosis method**: Added `subprocess.run(["log", "-t", "TREBNIC", msg])` calls in main.py to write to Android logcat. Key: use `subprocess.run()` instead of `os.system()` to avoid shell quoting issues with Python list repr.

**Fix**: Added `_fix_flat_extraction()` in `main.py` that runs before any imports on Android:
1. Checks if any entry in `os.listdir(app_dir)` contains `\\`
2. For each flat file with backslashes: splits the name, creates proper subdirectories with `os.makedirs()`, and moves the file with `shutil.move()`
3. Only runs once — after fix, the directory structure is correct and subsequent launches skip it

**Note**: The desugaring patch in `build.gradle.kts` does NOT survive when site-packages/hash are cleaned (causes template regeneration). Must re-apply after any clean rebuild.

## What works (final working solution)

### Extension discovery pipeline
1. Extension package at project root: `flet_local_notifications/` with `src/flutter/` Dart code
2. `requirements.txt` in source_dir includes: `flet-local-notifications @ file:///absolute/path/to/flet_local_notifications`
3. `flet build apk` from source_dir → uses requirements.txt → pip installs extension
4. serious_python discovers `flutter/` namespace in site-packages → copies to `flutter-packages-temp/`
5. `register_flutter_extensions()` moves to `flutter-packages/` and adds to pubspec.yaml
6. Template regenerated with `import 'package:flet_local_notifications/...'` in main.dart
7. Gradle builds with desugaring patch → APK includes Dart extension code

### Service auto-registration
- Python: `FletLocalNotifications()` instantiated → `Service.init()` → auto-registers
- Dart: `ServiceBinding` iterates extensions → `Extension.createService()` returns `NotificationsService`
- Do NOT use `page.services.append()` or `page.overlay.append()` or `page.update()`

## Current file layout
```
trebnic/                           # project root
├── pyproject.toml                 # has [tool.flet.dev_packages] (NOT read during build — see issue #2)
├── flet_local_notifications/      # full extension (pyproject.toml + src/ + flutter/)
└── trebnic/                       # source_dir (build runs from here)
    ├── requirements.txt           # includes flet-local-notifications @ file:///...
    └── services/
        └── notification_service.py
```

## Build commands (Windows)
```bash
cd trebnic/trebnic

# First build (will fail at Gradle — needs desugaring):
PYTHONUTF8=1 poetry run flet build apk -v

# Patch desugaring (one-time, survives rebuilds):
# Edit build/flutter/android/app/build.gradle.kts
# - compileOptions { isCoreLibraryDesugaringEnabled = true }
# - dependencies { coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4") }

# Rebuild:
PYTHONUTF8=1 poetry run flet build apk -v

# Install:
D:\Android\Sdk\platform-tools\adb.exe uninstall com.flet.trebnic
D:\Android\Sdk\platform-tools\adb.exe install build\apk\app-release.apk
```

## Key takeaways

1. **`flet build` only reads pyproject.toml from CWD** (no directory traversal)
2. **Windows + commas in version specs** breaks `serious_python` when deps are passed as `-r` args
3. **`requirements.txt` is the reliable path** on Windows — pip reads the file directly
4. **Service auto-registers** — never add to page.services/overlay manually
5. **Desugaring patch is required** for `flutter_local_notifications` v19
6. **Native C deps (cryptography, argon2)** must be excluded from Android builds
7. **archive 4.0.7 flat extraction bug** — app.zip extracted to flat files with `\` names on Android. Work around in main.py by detecting and renaming
8. **Desugaring patch is lost on clean rebuild** — must re-apply after `rm -rf build/site-packages build/.hash`
9. **Debug Android Python with `subprocess.run(["log", "-t", "TAG", msg])`** — avoids shell quoting issues that `os.system("log ...")` causes with Python repr output
