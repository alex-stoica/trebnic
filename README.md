# Trebnic development

From the repository root: `poetry install`, then
`poetry run flet run trebnic/main.py`.

## Android

Enable USB debugging; `adb devices` must show an authorized device.
On Windows, set `PYTHONIOENCODING=utf-8`. With Flutter on PATH:

```sh
poetry run flet build apk
poetry run flet-android-notifications-patch --project-root build/flutter
cd build/flutter
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Continue after a missing-desugaring failure only; fix other build errors first.
Reapply patches after regeneration. Export data before upgrading older builds;
import afterward. New builds use persistent storage. Don't uninstall.
