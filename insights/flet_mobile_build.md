# Flet mobile APK build

## Key rules

1. **`requirements.txt` must be next to `main.py`** - Flet mobile builds use pip with `requirements.txt`, not Poetry/pyproject.toml
2. **Run `flet build apk` from `trebnic/trebnic/`** - the directory containing `main.py`
3. **`PYTHONUTF8=1`** on Windows - Rich library crashes without it (`UnicodeEncodeError` on bullet chars)
4. **Full uninstall before reinstall** - `adb install -r` preserves cached Python env at `/data/user/0/com.flet.trebnic/files/flet/app/`, masking fixes
5. **Only pure Python or Android-wheeled packages** - native C extensions without Android wheels won't work

## Two dependency systems

| | Desktop | Mobile |
|---|---|---|
| Config | `pyproject.toml` (Poetry) | `requirements.txt` (pip) |
| Packages | Any Python package | Pure Python or packages with Android wheels |

## Build and deploy

```bash
cd trebnic/trebnic
PYTHONUTF8=1 flet build apk
adb uninstall com.flet.trebnic
adb install build/apk/app-release.apk
```

Verify dependencies were bundled: check `build/site-packages/arm64-v8a/` for expected package directories.
