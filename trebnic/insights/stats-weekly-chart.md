# Stats weekly chart implementation

## Overview

Implemented a weekly time chart in the stats view with dual bar layout and week navigation.

## Key learnings

### 1. Bar chart layout: stacked vs side-by-side

When users say "stacked bars", clarify whether they mean:
- **All components in one stack** (single bar with segments)
- **Some stacked, some side-by-side** (dual bars where one is composite)

In this case, the correct interpretation was:
- Left bar: Tracked time (standalone, blue)
- Right bar: Estimated done + Estimated pending (stacked, orange tones)

### 2. Week navigation with Monday start

```python
def _get_week_start(self, offset: int = 0) -> date:
    """Get the Monday of the week with given offset (0 = current week)."""
    today = date.today()
    days_since_monday = today.weekday()  # Monday = 0
    monday = today - timedelta(days=days_since_monday)
    return monday + timedelta(weeks=offset)
```

### 3. DailyStats changes for split estimates

Changed from single `estimated_seconds` to:
- `estimated_done_seconds`: Estimated time for completed tasks on that day
- `estimated_pending_seconds`: Estimated time for pending tasks on that day

This required updating:
- `DailyStats` dataclass
- `calculate_daily_stats()` method with new `start_date` parameter
- `export_to_json()` for the new fields
- UI chart building logic

### 4. Color choices for related data

When showing related data (both are "estimated"), use similar but distinguishable colors:
- Dark orange (`#e65100`) for estimated done
- Light orange (`#ffb74d`) for estimated pending

This creates visual grouping while maintaining distinction.

### 5. Scrollable lists with max height

For lists that might grow (projects), use a fixed max height with scroll:

```python
projects_list = ft.Container(
    content=ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO),
    height=280 if len(rows) > 4 else None,  # Only constrain if >4 items
)
```

### 6. Border radius on stacked bars

When stacking bars, handle border radius properly:
- Top bar: rounded top corners only
- Bottom bar: rounded bottom corners only
- Middle bars: no border radius

```python
# Top bar
border_radius=ft.border_radius.only(top_left=3, top_right=3)

# Bottom bar with conditional top radius
top_radius = 0 if has_item_above else 3
border_radius=ft.border_radius.only(
    top_left=top_radius, top_right=top_radius,
    bottom_left=3, bottom_right=3,
)
```

### 7. Estimation accuracy calculation

Accuracy should only consider completed tasks with both estimation AND tracked time:

```python
done_with_estimation = [t for t in done_tasks if t.estimated_seconds > 0]
done_with_both = [t for t in done_with_estimation if t.spent_seconds > 0]
```

This prevents skewing the metric with tasks that were completed but never tracked.

## Files modified

- `config.py`: Added `estimated_done` and `estimated_pending` colors
- `services/stats.py`: Split estimated fields, added `start_date` parameter, fixed accuracy
- `ui/pages/stats_view.py`: Weekly chart with navigation, dual bars, scrollable projects
- `app.py`: Projects sidebar always visible with scrolling, improved postpone notification
- `ui/navigation.py`: Removed projects toggle (always visible)

## Additional learnings

### 8. Stacked vs side-by-side bars - clarification

When user says "stacked", clarify the exact layout:
- **All stacked in one bar**: Single column with segments
- **Some stacked, some separate**: Dual bars where related items are grouped

Example: "Tracked separate, estimates stacked together" means:
```
|  T  | E.D |    <- T = Tracked (standalone)
|     | E.P |    <- E.D + E.P = stacked together
```

### 9. Color proximity for related data

When showing related data that should be perceived as a group, use colors from the same hue family:
- `#ef6c00` (medium-dark orange) for estimated done
- `#ff9800` (medium orange) for estimated pending

Avoid using green vs orange when items are conceptually related (both are "estimates").

### 10. Always-visible sidebar sections

Instead of collapsible sections with toggle arrows:
- Remove the toggle arrow
- Keep section always visible
- Add scrolling with fixed height when items exceed threshold

```python
self.projects_items = ft.Column(
    visible=True,
    scroll=ft.ScrollMode.AUTO if len(items) > 4 else None,
    height=160 if len(items) > 4 else None,
)
```

### 11. Contextual notifications

When an action moves content out of the current view, inform the user where to find it:
```python
if new_date > today and current_nav in (NavItem.TODAY, NavItem.INBOX):
    msg = f"'{task.title}' postponed to {date} (see Upcoming)"
```
