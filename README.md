# Trebnic - build & deploy

# Development with hot-reload
```python
flet run main.py
```

## Prerequisites
- USB Debugging enabled on phone (Settings → Developer Options → USB Debugging)
- Phone connected via USB

## Build
```bash 
flet build apk
```

## Check device is ready 
```bash
D:\Android\Sdk\platform-tools\adb.exe devices
```
✅ Should show device (not `unauthorized`)

## Install
```bash
D:\Android\Sdk\platform-tools\adb.exe install -r build\apk\app-release.apk
```