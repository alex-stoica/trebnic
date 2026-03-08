# flet-stt integration in trebnic (flet 0.80)

## What worked

- `page.services.append(stt)` for registering the FletStt service control
- Direct async handler `on_click=self._on_mic_tap` instead of `on_click=lambda e: page.run_task(method)`
- `on_device=False` needed on Samsung devices (on-device models may not be installed)
- `multiline=True, min_lines=1, max_lines=6` on the input TextField for dictation-friendly expansion

## What failed and why

### Attempt 1-2: `page.services.append` + `page.run_task(method)` as on_click
- Button produced zero response: no icon change, no error, no logcat output
- Root cause: `page.run_task(coroutine_function)` as an on_click handler silently fails for STT-related buttons
- Misleading because `page.run_task` works fine for `_on_send` on the same page

### Attempt 3: no registration (just create FletStt)
- Same result: button does nothing
- Without `page.services` or `page.overlay`, `_invoke_method` can't reach the Dart side

### Attempt 4: `page.overlay.append(stt)` + direct on_click
- Button WORKED (icon changed, STT started)
- But caused red half-screen visual artifact - the service rendered visibly in the overlay
- `visible=False` on the stt control did NOT fix the red screen

### Attempt 5 (fix): `page.services.append(stt)` + direct on_click
- Both button and UI work correctly
- The real blocker was `page.run_task` wrapping, not the registration method

## Key differences from flet-stt demo

The demo (`flet-stt-demo/main.py`) uses:
- `page.overlay.append(stt)` - works in simple single-page apps
- `on_click=toggle_listen` - direct async handler (no run_task)

In trebnic (complex multi-page app on flet 0.80):
- `page.overlay.append` causes visual artifacts (red half-screen)
- `page.services.append` is the correct registration for services
- Direct async on_click is required; `page.run_task` wrapper silently breaks

## Version warning

The flet-stt demo learnings (`flet-stt/insights/flet-build-learnings.md`) say "Do NOT add to page.overlay"
and "auto-registers, no need to add anywhere". This is for flet 0.82. On flet 0.80, you MUST explicitly
register with `page.services.append()`. The behavior differs across versions.

## Debugging tips

- Silent failures are the norm: wrong registration = no error, no log, nothing
- If the async on_click handler never starts executing, suspect `page.run_task` wrapping
- `adb logcat -s python:*` for Python-side logs
- Add a sync `print()` directly in the lambda to verify the click event itself fires
