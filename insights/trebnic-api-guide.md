# Trebnic API guide

## Setup

Run from project root. Every script follows this pattern:

```python
import asyncio, sys
sys.path.insert(0, "trebnic")
from datetime import date, datetime, timedelta
from core import bootstrap, shutdown
from api import TrebnicAPI
from config import RecurrenceFrequency

async def main():
    svc = await bootstrap()
    api = TrebnicAPI(svc)
    # ...
    await shutdown()

asyncio.run(main())
```

```bash
PYTHONUTF8=1 poetry run python my_script.py
```

## Projects

Seeded IDs: `"personal"`, `"work"`, `"sport"`. Access via `api.projects`.

## Tasks

```python
# Add (default: 15min estimate, no due date)
task = await api.add_task("Title", project_id="work", estimated_seconds=3600, due_date=date.today())

# Complete (optionally log time)
await api.complete_task(task, duration_seconds=1800)

# Log past work (creates done task + time entry)
await api.add_completed_task("Meeting", duration_seconds=3600, completed_at=datetime(...), project_id="work")

# Delete
await api.delete_task(task)

# Query
pending = await api.get_tasks(project_id="work")        # optional filter
done = await api.get_done_tasks(project_id="work", limit=50)
```

## Time: minutes to seconds

15m=900, 20m=1200, 25m=1500, 30m=1800, 45m=2700, 1h=3600, 1h30=5400, 1h45=6300, 2h=7200, 3h=10800

## Task management

```python
# Rename
await api.rename_task(task, "New title")

# Postpone (bumps due date by 1 day, returns new date)
new_date = await api.postpone_task(task)

# Set/clear due date
await api.set_due_date(task, date.today())
await api.set_due_date(task, None)

# Assign to project
await api.assign_project(task, "work")
await api.assign_project(task, None)  # unassign

# Get time entries for a task
entries = await api.get_time_entries(task.id)
```

## Projects

```python
# Create a project
project = await api.create_project("Side hustle", icon="🚀", color="#ff9800")

# List seeded + custom projects
all_projects = api.projects
```

## Daily notes

```python
# Save a note for a date
note = await api.save_daily_note(date.today(), "Markdown content here")

# Get recent notes
notes = await api.get_recent_notes(limit=30)
```

## Export/import

```python
# Full export (tasks, projects, time entries, notes, settings)
data = await api.export_data()

# Import (returns counts of imported items)
counts = await api.import_data(data)
```

## Recurrence

```python
await api.set_recurrence(task, RecurrenceFrequency.DAYS)                          # daily
await api.set_recurrence(task, RecurrenceFrequency.WEEKS, interval=2)             # biweekly
await api.set_recurrence(task, RecurrenceFrequency.WEEKS, weekdays=[0,1,2,3,4])   # weekdays (Mon=0)
await api.set_recurrence(task, RecurrenceFrequency.MONTHS, from_completion=True)  # monthly from completion
await api.set_recurrence(task, RecurrenceFrequency.DAYS, until=date(2026,6,1))    # with end date
await api.clear_recurrence(task)
```

## Deploy to mobile

Bundle the DB into the APK (see `android-db-sync.md` for why `/sdcard/` doesn't work):

```bash
cp trebnic.db trebnic/trebnic.db
poetry run flet build apk
rm trebnic/trebnic.db
adb uninstall ai.stoica.trebnic && adb install build/apk/app-release.apk
```

Must full-uninstall — `adb install -r` keeps the old cached DB.
