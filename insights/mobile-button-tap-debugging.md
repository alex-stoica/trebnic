# Mobile button tap not firing - note editor refine button

## Problem

The refine send button in the note editor did nothing on mobile. Three attempts to fix it failed before identifying the root cause. The chat view had an identical button that worked fine.

## What didn't work (attempts 1-2)

- Changing callback patterns (lambda vs direct async handler vs `page.run_task`)
- Removing the ProgressRing spinner
- These were red herrings because the chat view used the same patterns and worked

## What was actually wrong

Structural differences between the broken note editor input row and the working chat view input row:

| Property | Chat (works) | Note editor (broken) |
|----------|-------------|---------------------|
| `dense` | not set | `True` |
| `min_lines` | `1` | `2` |
| `content_padding` | explicit `Padding.symmetric(horizontal=12, vertical=8)` | not set |
| Row `vertical_alignment` | default (STRETCH) | `CrossAxisAlignment.CENTER` |
| mic `icon_size` | default (24) | `20` |
| Parent container | input row outside scroll | refine row inside `scroll=AUTO` Column |

The combination of `dense=True`, smaller touch targets (`icon_size=20`), `CrossAxisAlignment.CENTER` (which can shrink hit areas), and sitting inside a scrollable container made taps unreliable on mobile.

## The silent failure trap

`_refine_async` had `if not instruction: return` with no user feedback. This made it impossible to tell whether:
- A) The button tap never fired (layout/touch issue)
- B) The handler fired but the TextField value was empty (keyboard not syncing)

Always add diagnostic feedback (snack/log) for early returns in handlers, at least during debugging.

## Fix

1. Added snack message for the empty-instruction early return
2. Matched every structural property to the working chat view input row: removed `dense`, changed `min_lines` to 1, added `content_padding`, removed `vertical_alignment` from Row, removed `icon_size` from mic button

## Lesson

When a control works in one view but not another, diff the structural properties (dense, padding, alignment, parent scroll, icon sizes) before trying callback pattern changes. The callback pattern is rarely the issue if the same pattern works elsewhere in the app.
