# Color picker evaluation

Evaluated `flet-color-pickers` 0.81.0 as a replacement for the hand-rolled color picker in project dialogs.

## Pickers tested

### BlockPicker
- Renders a fixed grid of color swatches with no scrolling
- Has an ugly glow/shadow on the bottom-left corner that can't be disabled
- Colors are cramped in a non-scrollable panel — unusable with 17+ colors
- No configuration options to fix either issue

### MaterialPicker
- Shows the full Material Design palette (primary + shades)
- Visually overwhelming and completely out of place in a dark-themed dialog
- Way too many colors — the opposite of a curated project color list

### Other pickers (not tested visually)
- **ColorPicker**: full HSV palette + sliders + hex input — overkill for picking from a preset list
- **HueRingPicker**: circular hue ring — same problem, designed for arbitrary color selection
- **SlidePicker**: RGB/HSV channel sliders — precise but verbose, wrong UX for this use case

## Verdict

All `flet-color-pickers` widgets are designed for free-form color selection, not picking from a curated list. The hand-rolled `ListView` with color circles and names fits the app's dark theme perfectly and scrolls properly. Kept the original and improved it with single-click selection (tap a color → immediately applied, no confirm button needed).
