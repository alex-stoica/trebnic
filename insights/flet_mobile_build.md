# Flet mobile APK build

## Key rules

1. **`pyproject.toml` drives dependencies** - Flet reads `[project].dependencies` from `pyproject.toml` when it exists. The `requirements.txt` next to `main.py` is a legacy fallback (kept in sync manually but not used during build when `pyproject.toml` is present)
2. **Run `flet build apk` from the project root** (`trebnic/`) where `pyproject.toml` lives, so `product = "Trebnic"` is picked up. Running from `trebnic/trebnic/` skips `pyproject.toml` and defaults the app name to lowercase
3. **`PYTHONUTF8=1`** on Windows - Rich library crashes without it (`UnicodeEncodeError` on bullet chars)
4. **Full uninstall before reinstall** - `adb install -r` preserves cached Python env at `/data/user/0/ai.stoica.trebnic/files/flet/app/`, masking fixes
5. **Only pure Python or Android-wheeled packages** - native C extensions without Android wheels won't work

## Build and deploy

```bash
cd trebnic
PYTHONUTF8=1 poetry run flet build apk
adb uninstall ai.stoica.trebnic
adb install build/apk/app-release.apk
```

Verify dependencies were bundled: check `build/site-packages/arm64-v8a/` for expected package directories.

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

## Core library desugaring fix

See `notification-guide.md` (desugaring section) for the `build.gradle.kts` fix needed for `flutter_local_notifications` v19+.
