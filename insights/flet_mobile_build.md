# Flet mobile APK build

## Key rules

1. **`pyproject.toml` drives dependencies** - Flet reads `[project].dependencies` from `pyproject.toml` when it exists. The `requirements.txt` next to `main.py` is a legacy fallback (kept in sync manually but not used during build when `pyproject.toml` is present)
2. **Run `flet build apk` from the project root** (`trebnic/`) where `pyproject.toml` lives, so `product = "Trebnic"` is picked up. Running from `trebnic/trebnic/` skips `pyproject.toml` and defaults the app name to lowercase
3. **`PYTHONIOENCODING=utf-8`** on Windows - Rich library crashes without it (`UnicodeEncodeError` on bullet chars)
4. **Only pure Python or Android-wheeled packages** - native C extensions without Android wheels won't work

## Build

```bash
cd trebnic
PYTHONIOENCODING=utf-8 poetry run flet build apk
```

Verify dependencies were bundled: check `build/site-packages/arm64-v8a/` for expected package directories.

## Deploy to phone

Two modes — pick based on whether you want to keep or reset the on-device database.

**Keep data** (code-only updates, no DB changes):
```bash
adb install -r build/apk/trebnic.apk
```
Preserves `/data/data/ai.stoica.trebnic/` — existing DB, settings, and files survive.

**Fresh start** (new seed data, schema changes, or clean slate):
```bash
adb uninstall ai.stoica.trebnic && adb install build/apk/trebnic.apk
```
Wipes all app data. On first launch `seed_default_data()` runs because the DB is empty.

To bundle a pre-seeded DB into the APK (for scripted task creation):
```bash
cp trebnic.db trebnic/trebnic.db
PYTHONIOENCODING=utf-8 poetry run flet build apk
rm trebnic/trebnic.db
adb uninstall ai.stoica.trebnic && adb install build/apk/trebnic.apk
```
Must full-uninstall — otherwise `adb install -r` keeps the old cached DB file.

## Build cache gotcha with new Flet extensions

`flet build` uses a hash-based cache (`build/.hash/`) to skip pip install when `requirements.txt` hasn't changed. If you add a new **Flet extension** (like `flet-circular-slider`) but the build cache already exists from a prior run, pip is skipped entirely. This means:

- The Python module never lands in `build/site-packages/`
- The Flutter/Dart widget never extracts to `build/flutter-packages/`
- The extension never gets added to `pubspec.yaml` or imported in `main.dart`
- At runtime you get **"Unknown control: flet_circular_slider"**

**Fix:** after adding a new Flet extension to `requirements.txt`, delete these before rebuilding:
```bash
rm -rf build/.hash/ build/flutter-packages/ build/site-packages/
```

This forces a fresh pip install, which triggers the full extension registration pipeline (extract Flutter dir → scan pubspec → generate imports).

**Verify** the extension registered correctly:
- `build/flutter-packages/<extension>/pubspec.yaml` exists
- `build/site-packages/arm64-v8a/<extension>/` exists
- `build/flutter/lib/main.dart` imports the extension

## Post-clean-build fixes (IMPORTANT)

`flet build apk` regenerates `build/flutter/android/` from scratch when the build shell is missing or after deleting `build/.hash/`. This **wipes custom edits** to `build.gradle.kts` and `AndroidManifest.xml`. After any clean build, you must re-apply these two fixes before the Gradle step succeeds:

### 1. Core library desugaring (`build.gradle.kts`)

`flutter_local_notifications` v19+ requires desugaring. Edit `build/flutter/android/app/build.gradle.kts`:

```kotlin
// In compileOptions{}, add:
isCoreLibraryDesugaringEnabled = true

// In dependencies{}, add:
coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
```

Without this, Gradle fails with: `Dependency ':flutter_local_notifications' requires core library desugaring to be enabled for :app`.

### 2. Broadcast receivers (`AndroidManifest.xml`)

AlarmManager scheduled notifications need receivers in `build/flutter/android/app/src/main/AndroidManifest.xml`, inside `<application>`:

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

Without these, scheduled notifications silently fail to fire.

### Symptom of missing fixes

If the APK builds but the app shows a **white screen**, check `adb logcat` for `Python bundle not found: libpythonbundle.so` — this can happen when the Gradle build silently fails partway. A full clean rebuild with the fixes above resolves it.
