# Circular slider in APK builds

## Key insight: APK uses PyPI package, not local source

`flet build apk` reads dependencies from `pyproject.toml` — **not** `requirements.txt` when pyproject.toml exists.
For Flet user extensions, both Python and Dart/Flutter code come from the installed pip package, not local editable installs.

### Using `tool.flet.dev_packages` for local source builds

```toml
[tool.flet.dev_packages]
flet-circular-slider = "C:\\Users\\alexs\\Desktop\\flet-circular-slider"
```

This rewrites the dependency to a `file://` URL. Also disables hash-based cache, forcing re-install every build.
Remove it once the package is published to PyPI to speed up builds.

## Silent failures in page.run_task()

When code inside `page.run_task(async_fn)` throws, Flet catches it silently. No error dialog, no crash, no log.
**Always wrap risky code in try/except with logger.error() when it runs inside run_task().**

## The inner_text lag problem

Updating `inner_text` from Python on every `on_change` during dragging creates a Python<->Flutter round-trip per frame.
The slider handle moves smoothly (pure Flutter) but the text lags visibly. Text formatting must happen on the Dart side.

## The overlay/touch-blocking problem

An `ft.Container` over a `FletCircularSlider` in an `ft.Stack` blocks touch events.
`ignore_interactions=True` on the Container should fix this (maps to Flutter's `IgnorePointer`).

## Build template regeneration

See `notification-guide.md` (desugaring section) for the `build.gradle.kts` fix needed after template regeneration.
Also verify `android:label="Trebnic"` in AndroidManifest.xml.
