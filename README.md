# Trebnic - build & deploy

## Development with hot-reload
Run from the project root (where `pyproject.toml` lives), not from inside the package:
```bash
poetry run flet run trebnic/main.py
```

## Prerequisites
- USB Debugging enabled on phone (Settings → Developer Options → USB Debugging)
- Phone connected via USB
- `PYTHONUTF8=1` set (Windows - prevents Rich library Unicode crashes)

## Build
Always build from the project root (where `pyproject.toml` lives), never from `trebnic/`:
```bash
PYTHONUTF8=1 poetry run flet build apk
```

## Check device is ready
```bash
D:\Android\Sdk\platform-tools\adb.exe devices
```
Should show device (not `unauthorized`)

## Install
Full uninstall first (cached Python env persists with `-r`, see `insights/flet_mobile_build.md`):
```bash
D:\Android\Sdk\platform-tools\adb.exe uninstall ai.stoica.trebnic
D:\Android\Sdk\platform-tools\adb.exe install build\apk\trebnic.apk
```
