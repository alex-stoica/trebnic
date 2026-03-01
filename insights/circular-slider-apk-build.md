# Circular slider in APK builds — lessons learned

## Key insight: APK uses PyPI package, not local source (unless dev_packages)

`flet build apk` reads dependencies from `pyproject.toml` (`project.dependencies` or
`tool.poetry.dependencies`) — **NOT** from `requirements.txt` when pyproject.toml exists.
For Flet user extensions (like flet-circular-slider), both the **Python** AND
**Dart/Flutter** code come from the installed pip package — NOT from local editable installs.

This means:
- Local Dart changes (in `src/flutter/`) are invisible to `flet build apk` by default
- Changing `requirements.txt` has NO effect — the build uses pyproject.toml
- The desktop `pip install -e .` only affects local Python imports, not the APK

### Using `tool.flet.dev_packages` for local source builds

To use a local package source during APK builds, add to `pyproject.toml`:

```toml
[tool.flet.dev_packages]
flet-circular-slider = "C:\\Users\\alexs\\Desktop\\flet-circular-slider"
```

This rewrites the dependency to `flet-circular-slider @ file://C:\Users\alexs\Desktop\...`
before passing to pip. The local source is built into a wheel, pip installs it, and
`serious_python` extracts the `flutter/` directory with the updated Dart code.

**Important:** `dev_packages` also disables the hash-based cache, forcing re-install every build.
Remove it once the package is published to PyPI to speed up builds.

## Version history on PyPI

| Version | Features |
|---------|----------|
| 0.1.0   | Basic slider (min, max, value, colors, events, inner_text NOT available) |
| 0.1.1   | Added `inner_text`, `inner_text_color` (Python + Dart). NO `divisions`. |
| 0.1.2   | Local only — added `divisions`, Dart `{duration}` formatting. NOT on PyPI. |
| 0.2.0   | Published to PyPI with all features (divisions, label_formatter, label_map). |
| 0.3.0   | Internal refactor, StatefulWidget on Dart side. |
| 0.4.0   | change_throttle_ms, label_formatter requires divisions, removed {duration} template. |

## ~~The `divisions` TypeError~~ — RESOLVED in 0.2.0

`FletCircularSlider(divisions=100)` used to throw `TypeError` on mobile because APK pulled 0.1.1
from PyPI (which lacked `divisions`). Fixed by publishing 0.2.0 to PyPI.

## Silent failures in page.run_task()

When code inside `page.run_task(async_fn)` throws an exception, Flet's event loop catches it
silently. The UI just does nothing — no error dialog, no crash, no log (unless you add explicit
try/except with logging). This makes debugging on mobile extremely hard.

**Always wrap risky code in try/except with logger.error() when it runs inside run_task().**

## The overlay/touch-blocking problem

Placing an `ft.Container` over a `FletCircularSlider` in an `ft.Stack` blocks touch events on
the slider. `ignore_interactions=True` on the Container should fix this (maps to Flutter's
`IgnorePointer`), but was never properly tested because the `divisions` TypeError prevented
the dialog from showing.

## The inner_text lag problem

Updating `inner_text` from Python on every `on_change` event during dragging creates a
Python↔Flutter round-trip per frame. The slider handle moves smoothly (pure Flutter) but the
text lags visibly. Text formatting must happen on the Dart side for smooth updates.

## Build template regeneration

See `notification-guide.md` (desugaring section) for the `build.gradle.kts` fix needed after template regeneration. Also verify `android:label="Trebnic"` in AndroidManifest.xml.
