# Syncing desktop DB to Android device

## Problem

Tasks created via `TrebnicAPI` on desktop write to the local `trebnic.db`. The Android app has its own separate database in its private storage. Need to get desktop data onto the device.

## Failed approach: `/sdcard/` import

Tried adding a startup hook in `main.py` to copy `/sdcard/trebnic.db` into the app's CWD.

```python
# DON'T DO THIS - permission denied on Android 11+
shutil.copy2("/sdcard/trebnic.db", os.path.join(os.getcwd(), "trebnic.db"))
```

**Why it fails:** Android 11+ (API 30) enforces scoped storage. Apps cannot read `/sdcard/` without `MANAGE_EXTERNAL_STORAGE` permission, which requires special Play Store justification and is inappropriate for a task manager.

Accessible paths **without** permissions:
- Internal: `/data/data/<package>/files/` (only via `run-as` on debuggable builds)
- External app-specific: `/storage/emulated/0/Android/data/<package>/files/` (app can access, but needs to exist first)

Neither is easily writable via `adb push` on a release build.

## Working approach: bundle DB into APK

The Flet build system (`flet build apk`) packages everything in the Python app directory. Place `trebnic.db` next to `main.py` before building:

```bash
# 1. Copy desktop DB into the app source dir
cp trebnic.db trebnic/trebnic.db

# 2. Build APK (DB gets packaged as an asset)
poetry run flet build apk

# 3. Remove the DB from source tree (don't commit it)
rm trebnic/trebnic.db

# 4. Full uninstall + install (fresh extraction includes the DB)
adb uninstall ai.stoica.trebnic
adb install build/apk/app-release.apk
```

**Why it works:** serious_python extracts all bundled files (including the DB) to the app's internal files directory. The Python process CWD is that directory. `aiosqlite.connect("trebnic.db")` finds the pre-existing file and uses it instead of creating a new one.

**Important:** Must do full `adb uninstall` before `adb install`. Using `adb install -r` preserves the cached Python env from the previous install, so the old DB survives and the new bundled one is ignored.

## Key learnings

1. **Android scoped storage** (11+): apps cannot access `/sdcard/` without dangerous permissions
2. **Release builds aren't debuggable**: `adb shell run-as <package>` fails, so no file injection
3. **Flet bundles everything** in the Python app dir — use this to ship pre-seeded data
4. **Full uninstall is required** to get fresh extracted files on the device
