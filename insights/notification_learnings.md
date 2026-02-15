# Notification learnings from notifications_flet

## The core problem

Trebnic's current notification service uses plyer (desktop) and pyjnius (Android). plyer works on Windows but **both plyer and pyjnius are dead ends on Android** because they depend on Kivy's `PythonActivity`, which doesn't exist in Flet. Flet is Flutter-based, not Kivy-based. Python has zero direct access to Android Java APIs in Flet.

The `notifications_flet` project on desktop proved the only viable path: a **custom Flet extension** that bridges Python to Dart to `flutter_local_notifications`.

## Architecture that works

```
Python (ft.Service subclass)
  -> _invoke_method("show_notification", args)
    -> Flet protocol (Python <-> Dart)
      -> FletService subclass in Dart
        -> flutter_local_notifications plugin
          -> Android NotificationManager
            -> real OS notification
```

## What trebnic needs to change

### 1. Add a Flet extension package inside the project

Create `flet_local_notifications/` as a sibling directory (or subdirectory) with this structure:

```
flet_local_notifications/
├── pyproject.toml
└── src/
    ├── flet_local_notifications/
    │   ├── __init__.py
    │   └── flet_local_notifications.py    # Python ft.Service subclass
    └── flutter/
        └── flet_local_notifications/
            ├── pubspec.yaml               # depends on flutter_local_notifications ^19.0.0
            └── lib/
                ├── flet_local_notifications.dart   # library export
                └── src/
                    ├── extension.dart               # FletExtension, class MUST be named "Extension"
                    └── notifications_service.dart   # FletService with actual notification logic
```

### 2. Extension pyproject.toml (critical details)

```toml
[project]
name = "flet-local-notifications"
version = "0.1.0"
dependencies = ["flet>=0.80.5"]

[tool.setuptools.package-data]
"flutter.flet_local_notifications" = ["**/*"]

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"
```

**CRITICAL**: Do NOT add `[tool.setuptools.packages.find]`. It overrides automatic namespace discovery and the `flutter/` directory (implicit namespace package) won't be found. No `__init__.py` in `flutter/` dirs either.

### 3. Root pyproject.toml changes

```toml
[tool.flet.android.permission]
"android.permission.POST_NOTIFICATIONS" = true    # already present

[tool.flet.app]
exclude = ["flet_local_notifications"]             # prevent source dir from being packaged into APK

[tool.flet.dev_packages]
flet-local-notifications = "flet_local_notifications"   # tells flet to pip install the extension
```

Remove `plyer` and `pyjnius` from dependencies (they're dead ends on Android).

### 4. Python service class

```python
@ft.control("flet_local_notifications")
class FletLocalNotifications(ft.Service):
    on_notification_tap: Optional[ft.ControlEventHandler] = None

    async def show_notification(self, notification_id: int, title: str, body: str):
        return await self._invoke_method(
            method_name="show_notification",
            arguments={"id": notification_id, "title": title, "body": body},
        )

    async def request_permissions(self):
        return await self._invoke_method(method_name="request_permissions")
```

Key rules:
- Subclass `ft.Service`, NOT `ft.LayoutControl`
- Use `@ft.control("flet_local_notifications")` decorator to register the type
- Call `_invoke_method()` to send commands to Dart
- Do NOT add to `page.overlay` - services auto-register via `Service.init()` -> `context.page._services`
- Just instantiate the service. That's it.

### 5. Dart extension class

```dart
class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "flet_local_notifications":
        return NotificationsService(control: control);
      default:
        return null;
    }
  }
}
```

The Dart library file must: `export "src/extension.dart" show Extension;` - class name MUST be exactly `Extension`.

### 6. Dart notification service (key patterns)

```dart
class NotificationsService extends FletService {
  final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  Completer<bool>? _initCompleter;      // prevents race conditions
  DateTime? _lastShowTime;               // debounce for foreground tap callback

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_onMethod);   // receive Python calls
    _ensureInitialized();
  }

  Future<bool> _ensureInitialized() async {
    if (_initCompleter != null) return _initCompleter!.future;
    _initCompleter = Completer<bool>();
    // ... initialize plugin with AndroidInitializationSettings('@mipmap/ic_launcher')
    // ... set onDidReceiveNotificationResponse with debounce check
    return _initCompleter!.future;
  }
}
```

**Completer pattern is mandatory**: `FletService.init()` is synchronous but plugin init is async. Without the Completer, `request_permissions` can be called before the plugin is ready, causing `resolvePlatformSpecificImplementation` to return null silently.

**Debounce is mandatory**: On Samsung OneUI, `onDidReceiveNotificationResponse` fires immediately when a notification is shown while the app is in foreground. Ignore callbacks within 3 seconds of show.

To send events back to Python: `control.triggerEvent("notification_tap", payload)`.

### 7. Flutter pubspec.yaml

```yaml
dependencies:
  flet: ^0.80.2
  flutter:
    sdk: flutter
  flutter_local_notifications: ^19.0.0    # NOT v20, it has breaking changes
```

## Flet extension discovery pipeline

How Flet finds and loads extension Dart code during APK build:

1. `pip install` the extension into site-packages (including `flutter/` namespace data)
2. `serious_python` copies `site-packages/flutter/*` to `build/flutter-packages-temp/`
3. Flet moves to `build/flutter-packages/`, scans for `pubspec.yaml` in each subdir
4. Adds as path dependency to `build/flutter/pubspec.yaml`, generates imports in `main.dart`
5. Template generates: `import 'package:xxx/xxx.dart' as xxx;` and `xxx.Extension()` in extensions list

## Flet 0.80 extension API cheat sheet

| Concept | Python | Dart |
|---------|--------|------|
| Non-visual service | `ft.Service` | `FletService` subclass |
| Visual control | `ft.LayoutControl` | Widget subclass |
| Register type | `@ft.control("type_name")` | `createService(Control control)` |
| Call Dart from Python | `await self._invoke_method("name", args)` | `control.addInvokeMethodListener(callback)` |
| Call Python from Dart | `on_event` handler | `control.triggerEvent("name", data)` |

## Build gotchas

### Core library desugaring (will break the build)
`flutter_local_notifications` v19+ needs Java 8 desugaring. After first `flet build apk` (which generates the template), patch `build/flutter/android/app/build.gradle.kts`:
- Add `isCoreLibraryDesugaringEnabled = true` inside `compileOptions {}`
- Add `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")` inside `dependencies {}`
- Then rebuild. Patch survives re-runs as long as pyproject.toml template inputs don't change.

### POST_NOTIFICATIONS needs runtime request
Declaring permission in pyproject.toml only adds it to AndroidManifest. Must call `requestNotificationsPermission()` at runtime in Dart code. Plugin MUST be initialized first or `resolvePlatformSpecificImplementation` returns null silently.

### Windows build command
```bash
PYTHONIOENCODING=utf-8 python -c "import sys; sys.argv = ['flet', 'build', 'apk', '-v']; from flet_cli.cli import main; main()"
```
Without `PYTHONIOENCODING=utf-8`, Rich library's spinner characters crash on Windows cp1252 console.

### `nul` file on Windows
Git Bash creates an actual FILE named `nul` if any command redirects to `nul`. This breaks `serious_python` with `PathNotFoundException`. Use `/dev/null` instead. Delete with `rm nul` if it exists.

### Junk files cause black screen
Temp JSON/PNG files in the project root get packaged by `serious_python` and can cause the Python runtime to fail silently (black screen). Keep root clean.

### pip cache purge
Don't purge pip cache during active Flet development. It forces re-download of everything and combined with `--no-cache-dir` flag that Flet adds, it breaks the build.

## What to do with trebnic's existing NotificationService

The current `notification_service.py` has good infrastructure (scheduler loop, quiet hours, event subscriptions, database storage, encryption awareness) but its delivery backends are wrong for Android. The integration plan:

1. **Keep** the scheduler, event subscriptions, quiet hours, encryption-aware delivery logic, and database-backed scheduling
2. **Replace** `NotificationBackend.PYJNIUS` and `NotificationBackend.PLYER` with a new `NotificationBackend.FLET_EXTENSION` backend
3. **Add** the `flet_local_notifications` extension package to the project
4. **Wire** the `FletLocalNotifications` service into `app_initializer.py` (just instantiate it, do NOT add to overlay)
5. **In `_deliver_notification`**, call `await notifications.show_notification(id, title, body)` instead of the plyer/pyjnius methods
6. **Remove** `plyer` and `pyjnius` dependencies from pyproject.toml
7. **Keep** plyer as optional desktop fallback if desired (it does work on Windows), but the extension is the only path for Android

## Dead ends (do not retry)

| Approach | Why it's dead |
|----------|---------------|
| `flet_notifications` package (Bbalduzz) | Abandoned, imports `flet.core.control.Control` which doesn't exist in 0.80+ |
| `plyer` on Android | Uses Pyjnius/Kivy's PythonActivity, doesn't exist in Flet |
| `android-notify` package | Same Pyjnius dependency, crashes on import |
| Raw Pyjnius with `org.kivy.android.PythonActivity` | Class doesn't exist in Flet, it uses Flutter activities |
| Any Kivy/PythonActivity/Pyjnius approach | Architectural impossibility - Flet's Python is sandboxed from Android APIs |
