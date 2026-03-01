"""Tests for TrebnicAPI facade."""
from datetime import date, datetime, timedelta

import pytest

from api import TrebnicAPI
from config import RecurrenceFrequency
from core import ServiceContainer
from database import db
from events import AppEvent, event_bus
from models.entities import DailyNote, Task, TimeEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class EventCollector:
    """Subscribe to events and record them for assertions."""

    def __init__(self, *events: AppEvent):
        self.received: list[tuple[AppEvent, object]] = []
        self._subs = []
        for ev in events:
            sub = event_bus.subscribe(ev, lambda data, _ev=ev: self.received.append((_ev, data)))
            self._subs.append(sub)

    def count(self, event: AppEvent) -> int:
        return sum(1 for ev, _ in self.received if ev == event)

    def cleanup(self):
        for sub in self._subs:
            sub.unsubscribe()


@pytest.fixture
def api(services: ServiceContainer) -> TrebnicAPI:
    return TrebnicAPI(services)


# ===========================================================================
# add_task
# ===========================================================================

class TestAddTask:
    async def test_creates_task_with_defaults(self, api: TrebnicAPI):
        task = await api.add_task("Buy milk")
        assert task.id is not None
        assert task.title == "Buy milk"
        assert task.estimated_seconds == 900
        assert task.spent_seconds == 0

    async def test_task_appears_in_state(self, api: TrebnicAPI):
        task = await api.add_task("Read book")
        assert task in api.state.tasks
        assert task not in api.state.done_tasks

    async def test_emits_task_created(self, api: TrebnicAPI):
        collector = EventCollector(AppEvent.TASK_CREATED)
        await api.add_task("Test event")
        assert collector.count(AppEvent.TASK_CREATED) == 1
        collector.cleanup()

    async def test_custom_parameters(self, api: TrebnicAPI):
        task = await api.add_task(
            "Deploy app",
            estimated_seconds=7200,
            due_date=date(2026, 3, 1),
        )
        assert task.estimated_seconds == 7200
        assert task.due_date == date(2026, 3, 1)

    async def test_multiple_tasks_get_unique_ids(self, api: TrebnicAPI):
        t1 = await api.add_task("First")
        t2 = await api.add_task("Second")
        assert t1.id != t2.id


# ===========================================================================
# complete_task
# ===========================================================================

class TestCompleteTask:
    async def test_complete_moves_to_done(self, api: TrebnicAPI):
        task = await api.add_task("Finish report")
        await api.complete_task(task)
        assert task not in api.state.tasks
        assert task in api.state.done_tasks

    async def test_complete_emits_event(self, api: TrebnicAPI):
        collector = EventCollector(AppEvent.TASK_COMPLETED)
        task = await api.add_task("Ship feature")
        await api.complete_task(task)
        assert collector.count(AppEvent.TASK_COMPLETED) == 1
        collector.cleanup()

    async def test_complete_with_duration_creates_time_entry(self, api: TrebnicAPI, services: ServiceContainer):
        task = await api.add_task("Code review")
        ended = datetime(2026, 2, 24, 17, 0, 0)
        await api.complete_task(task, duration_seconds=1800, ended_at=ended)

        entries = await services.time_entry.load_time_entries_for_task(task.id)
        assert len(entries) == 1
        assert entries[0].duration_seconds == 1800
        assert entries[0].end_time == ended

    async def test_complete_with_duration_updates_spent(self, api: TrebnicAPI):
        task = await api.add_task("Design")
        await api.complete_task(task, duration_seconds=3600)
        assert task.spent_seconds == 3600

    async def test_complete_without_duration_no_time_entry(self, api: TrebnicAPI, services: ServiceContainer):
        task = await api.add_task("Quick fix")
        await api.complete_task(task)
        entries = await services.time_entry.load_time_entries_for_task(task.id)
        assert len(entries) == 0


# ===========================================================================
# add_completed_task
# ===========================================================================

class TestAddCompletedTask:
    async def test_creates_done_task(self, api: TrebnicAPI):
        task = await api.add_completed_task("Past work", duration_seconds=3600)
        assert task in api.state.done_tasks
        assert task not in api.state.tasks

    async def test_sets_spent_seconds(self, api: TrebnicAPI):
        task = await api.add_completed_task("Meeting", duration_seconds=5400)
        assert task.spent_seconds == 5400

    async def test_creates_backdated_time_entry(self, api: TrebnicAPI, services: ServiceContainer):
        completed = datetime(2026, 2, 20, 14, 0, 0)
        task = await api.add_completed_task("Old task", duration_seconds=1800, completed_at=completed)

        entries = await services.time_entry.load_time_entries_for_task(task.id)
        assert len(entries) == 1
        assert entries[0].end_time == completed
        assert entries[0].start_time == completed - timedelta(seconds=1800)

    async def test_estimated_defaults_to_duration(self, api: TrebnicAPI):
        task = await api.add_completed_task("Estimate test", duration_seconds=2700)
        assert task.estimated_seconds == 2700

    async def test_custom_estimated(self, api: TrebnicAPI):
        task = await api.add_completed_task("Custom est", duration_seconds=1800, estimated_seconds=3600)
        assert task.estimated_seconds == 3600

    async def test_emits_created_and_completed(self, api: TrebnicAPI):
        collector = EventCollector(AppEvent.TASK_CREATED, AppEvent.TASK_COMPLETED)
        await api.add_completed_task("Both events", duration_seconds=600)
        assert collector.count(AppEvent.TASK_CREATED) == 1
        assert collector.count(AppEvent.TASK_COMPLETED) == 1
        collector.cleanup()

    async def test_due_date_set_to_completed_date(self, api: TrebnicAPI):
        completed = datetime(2026, 1, 15, 10, 0, 0)
        task = await api.add_completed_task("Dated", duration_seconds=300, completed_at=completed)
        assert task.due_date == date(2026, 1, 15)


# ===========================================================================
# delete_task
# ===========================================================================

class TestDeleteTask:
    async def test_delete_removes_from_state(self, api: TrebnicAPI):
        task = await api.add_task("Throwaway")
        await api.delete_task(task)
        assert task not in api.state.tasks
        assert task not in api.state.done_tasks

    async def test_delete_emits_event(self, api: TrebnicAPI):
        collector = EventCollector(AppEvent.TASK_DELETED)
        task = await api.add_task("Gone")
        await api.delete_task(task)
        assert collector.count(AppEvent.TASK_DELETED) == 1
        collector.cleanup()

    async def test_delete_done_task(self, api: TrebnicAPI):
        task = await api.add_task("Will complete then delete")
        await api.complete_task(task)
        assert task in api.state.done_tasks
        await api.delete_task(task)
        assert task not in api.state.done_tasks

    async def test_delete_persists_to_db(self, api: TrebnicAPI, services: ServiceContainer):
        task = await api.add_task("Check DB")
        task_id = task.id
        await api.delete_task(task)
        # Verify task is gone from DB by reloading
        pending, done = await services.task.get_filtered_tasks()
        all_ids = [t.id for t in pending + done]
        assert task_id not in all_ids


# ===========================================================================
# projects
# ===========================================================================

class TestProjects:
    async def test_lists_seed_projects(self, api: TrebnicAPI):
        names = {p.name for p in api.projects}
        # Bootstrap seeds 3 default projects
        assert len(api.projects) >= 3
        assert "Personal" in names or len(names) >= 3

    async def test_project_has_fields(self, api: TrebnicAPI):
        project = api.projects[0]
        assert project.id is not None
        assert project.name
        assert project.icon
        assert project.color


# ===========================================================================
# get_tasks
# ===========================================================================

class TestGetTasks:
    async def test_get_all_pending(self, api: TrebnicAPI):
        await api.add_task("Task A")
        await api.add_task("Task B")
        await api.add_task("Task C")
        tasks = await api.get_tasks()
        titles = [t.title for t in tasks]
        assert "Task A" in titles
        assert "Task B" in titles
        assert "Task C" in titles

    async def test_filter_by_project(self, api: TrebnicAPI):
        p1 = api.projects[0]
        p2 = api.projects[1]
        await api.add_task("In P1", project_id=p1.id)
        await api.add_task("In P2", project_id=p2.id)
        tasks = await api.get_tasks(project_id=p1.id)
        assert all(t.project_id == p1.id for t in tasks)
        assert any(t.title == "In P1" for t in tasks)
        assert not any(t.title == "In P2" for t in tasks)

    async def test_excludes_done(self, api: TrebnicAPI):
        task = await api.add_task("Will complete")
        await api.complete_task(task)
        tasks = await api.get_tasks()
        assert not any(t.title == "Will complete" for t in tasks)

    async def test_get_done_tasks(self, api: TrebnicAPI):
        task = await api.add_task("Done one")
        await api.complete_task(task)
        done = await api.get_done_tasks()
        assert any(t.title == "Done one" for t in done)

    async def test_get_done_respects_project_filter(self, api: TrebnicAPI):
        p1 = api.projects[0]
        p2 = api.projects[1]
        t1 = await api.add_task("Done P1", project_id=p1.id)
        t2 = await api.add_task("Done P2", project_id=p2.id)
        await api.complete_task(t1)
        await api.complete_task(t2)
        done = await api.get_done_tasks(project_id=p1.id)
        assert any(t.title == "Done P1" for t in done)
        assert not any(t.title == "Done P2" for t in done)


# ===========================================================================
# recurrence
# ===========================================================================

class TestRecurrence:
    async def test_set_weekly_recurrence(self, api: TrebnicAPI):
        task = await api.add_task("Weekly standup")
        await api.set_recurrence(task, RecurrenceFrequency.WEEKS)
        assert task.recurrent is True
        assert task.recurrence_frequency == RecurrenceFrequency.WEEKS
        assert task.recurrence_interval == 1

    async def test_set_recurrence_calculates_due_date(self, api: TrebnicAPI):
        task = await api.add_task("Recurring")
        await api.set_recurrence(task, RecurrenceFrequency.DAYS)
        # Due date should be set to today (yesterday + 1 day)
        assert task.due_date is not None
        assert task.due_date >= date.today()

    async def test_set_recurrence_with_weekdays(self, api: TrebnicAPI):
        task = await api.add_task("Weekdays only")
        await api.set_recurrence(task, RecurrenceFrequency.WEEKS, weekdays=[0, 1, 2, 3, 4])
        assert task.recurrence_weekdays == [0, 1, 2, 3, 4]
        assert task.due_date is not None
        assert task.due_date.weekday() in [0, 1, 2, 3, 4]

    async def test_set_recurrence_with_until(self, api: TrebnicAPI):
        task = await api.add_task("Limited recurrence")
        until = date(2026, 6, 1)
        await api.set_recurrence(task, RecurrenceFrequency.DAYS, until=until)
        assert task.recurrence_end_type == "on_date"
        assert task.recurrence_end_date == until

    async def test_clear_recurrence(self, api: TrebnicAPI):
        task = await api.add_task("Was recurring")
        await api.set_recurrence(task, RecurrenceFrequency.DAYS)
        assert task.recurrent is True
        await api.clear_recurrence(task)
        assert task.recurrent is False
        assert task.recurrence_end_type == "never"

    async def test_completing_recurring_creates_next(self, api: TrebnicAPI):
        task = await api.add_task("Repeat me")
        await api.set_recurrence(task, RecurrenceFrequency.DAYS)
        original_due = task.due_date
        next_task = await api.complete_task(task)
        assert next_task is not None
        assert next_task.recurrent is True
        assert next_task.due_date > original_due

    async def test_set_recurrence_persists(self, api: TrebnicAPI):
        task = await api.add_task("Persisted recurrence")
        await api.set_recurrence(
            task, RecurrenceFrequency.MONTHS, interval=2, from_completion=True,
        )
        # Reload from DB
        rows = await db.load_tasks_filtered(is_done=False)
        reloaded = [Task.from_dict(r) for r in rows if r["id"] == task.id]
        assert len(reloaded) == 1
        assert reloaded[0].recurrent is True
        assert reloaded[0].recurrence_frequency == RecurrenceFrequency.MONTHS
        assert reloaded[0].recurrence_interval == 2
        assert reloaded[0].recurrence_from_completion is True


# ===========================================================================
# rename_task
# ===========================================================================

class TestRenameTask:
    async def test_rename_updates_title(self, api: TrebnicAPI):
        task = await api.add_task("Old name")
        await api.rename_task(task, "New name")
        assert task.title == "New name"

    async def test_rename_persists_to_db(self, api: TrebnicAPI):
        task = await api.add_task("Before rename")
        await api.rename_task(task, "After rename")
        rows = await db.load_tasks_filtered(is_done=False)
        reloaded = [Task.from_dict(r) for r in rows if r["id"] == task.id]
        assert len(reloaded) == 1
        assert reloaded[0].title == "After rename"

    async def test_rename_emits_event(self, api: TrebnicAPI):
        collector = EventCollector(AppEvent.TASK_RENAMED)
        task = await api.add_task("Rename me")
        await api.rename_task(task, "Renamed")
        assert collector.count(AppEvent.TASK_RENAMED) == 1
        collector.cleanup()


# ===========================================================================
# postpone_task
# ===========================================================================

class TestPostponeTask:
    async def test_postpone_adds_one_day(self, api: TrebnicAPI):
        task = await api.add_task("Postpone me", due_date=date.today())
        await api.postpone_task(task)
        assert task.due_date == date.today() + timedelta(days=1)

    async def test_postpone_returns_new_date(self, api: TrebnicAPI):
        task = await api.add_task("Return check", due_date=date(2026, 3, 10))
        result = await api.postpone_task(task)
        assert result == date(2026, 3, 11)

    async def test_postpone_no_due_date_uses_today(self, api: TrebnicAPI):
        task = await api.add_task("No date")
        assert task.due_date is None
        await api.postpone_task(task)
        assert task.due_date == date.today() + timedelta(days=1)

    async def test_postpone_emits_event(self, api: TrebnicAPI):
        collector = EventCollector(AppEvent.TASK_POSTPONED)
        task = await api.add_task("Event check", due_date=date.today())
        await api.postpone_task(task)
        assert collector.count(AppEvent.TASK_POSTPONED) == 1
        collector.cleanup()


# ===========================================================================
# get_time_entries
# ===========================================================================

class TestGetTimeEntries:
    async def test_returns_entries_for_task(self, api: TrebnicAPI):
        task = await api.add_task("Tracked task")
        await api.complete_task(task, duration_seconds=1800)
        entries = await api.get_time_entries(task.id)
        assert len(entries) == 1
        assert entries[0].duration_seconds == 1800

    async def test_empty_when_no_entries(self, api: TrebnicAPI):
        task = await api.add_task("No tracking")
        entries = await api.get_time_entries(task.id)
        assert entries == []

    async def test_multiple_entries(self, api: TrebnicAPI, services: ServiceContainer):
        task = await api.add_task("Multi entry")
        now = datetime(2026, 2, 25, 12, 0, 0)
        for i in range(2):
            entry = TimeEntry(
                task_id=task.id,
                start_time=now + timedelta(hours=i),
                end_time=now + timedelta(hours=i, minutes=30),
            )
            await services.time_entry.save_time_entry(entry)
        entries = await api.get_time_entries(task.id)
        assert len(entries) == 2


# ===========================================================================
# get_tasks / get_done_tasks with due date filters
# ===========================================================================

class TestGetTasksFiltered:
    async def test_due_before_filters(self, api: TrebnicAPI):
        await api.add_task("Early", due_date=date(2026, 3, 1))
        await api.add_task("Late", due_date=date(2026, 3, 15))
        tasks = await api.get_tasks(due_before=date(2026, 3, 5))
        titles = [t.title for t in tasks]
        assert "Early" in titles
        assert "Late" not in titles

    async def test_due_after_filters(self, api: TrebnicAPI):
        await api.add_task("Early", due_date=date(2026, 3, 1))
        await api.add_task("Late", due_date=date(2026, 3, 15))
        tasks = await api.get_tasks(due_after=date(2026, 3, 5))
        titles = [t.title for t in tasks]
        assert "Late" in titles
        assert "Early" not in titles

    async def test_combined_filters(self, api: TrebnicAPI):
        await api.add_task("Before", due_date=date(2026, 3, 1))
        await api.add_task("Between", due_date=date(2026, 3, 10))
        await api.add_task("After", due_date=date(2026, 3, 20))
        tasks = await api.get_tasks(due_after=date(2026, 3, 5), due_before=date(2026, 3, 15))
        titles = [t.title for t in tasks]
        assert "Between" in titles
        assert "Before" not in titles
        assert "After" not in titles

    async def test_done_tasks_due_before(self, api: TrebnicAPI):
        t1 = await api.add_task("Done early", due_date=date(2026, 3, 1))
        t2 = await api.add_task("Done late", due_date=date(2026, 3, 15))
        await api.complete_task(t1)
        await api.complete_task(t2)
        done = await api.get_done_tasks(due_before=date(2026, 3, 5))
        titles = [t.title for t in done]
        assert "Done early" in titles
        assert "Done late" not in titles


# ===========================================================================
# export_data
# ===========================================================================

class TestExportData:
    async def test_export_empty_db(self, api: TrebnicAPI):
        await db.clear_all()
        data = await api.export_data()
        assert data["version"] == 1
        assert "exported_at" in data
        assert data["projects"] == []
        assert data["tasks"] == []
        assert data["time_entries"] == []

    async def test_export_includes_projects(self, api: TrebnicAPI):
        data = await api.export_data()
        assert len(data["projects"]) >= 3
        p = data["projects"][0]
        assert "id" in p and "name" in p and "icon" in p and "color" in p

    async def test_export_includes_pending_tasks(self, api: TrebnicAPI):
        await api.add_task("Exported task", due_date=date(2026, 4, 1), estimated_seconds=1800)
        data = await api.export_data()
        exported = [t for t in data["tasks"] if t["title"] == "Exported task"]
        assert len(exported) == 1
        t = exported[0]
        assert t["id"] is not None
        assert t["estimated_seconds"] == 1800
        assert t["is_done"] == 0

    async def test_export_includes_done_tasks(self, api: TrebnicAPI):
        task = await api.add_task("Will be done")
        await api.complete_task(task)
        data = await api.export_data()
        done = [t for t in data["tasks"] if t["title"] == "Will be done"]
        assert len(done) == 1
        assert done[0]["is_done"] == 1

    async def test_export_includes_time_entries(self, api: TrebnicAPI):
        task = await api.add_task("Tracked")
        ended = datetime(2026, 3, 1, 12, 0, 0)
        await api.complete_task(task, duration_seconds=600, ended_at=ended)
        data = await api.export_data()
        entries = [e for e in data["time_entries"] if e["task_id"] == task.id]
        assert len(entries) == 1
        assert entries[0]["id"] is not None

    async def test_export_includes_daily_notes(self, api: TrebnicAPI):
        await db.save_daily_note(date(2026, 3, 5), "Productive day")
        data = await api.export_data()
        notes = [n for n in data["daily_notes"] if n["content"] == "Productive day"]
        assert len(notes) == 1
        assert notes[0]["date"] == "2026-03-05"

    async def test_export_includes_settings(self, api: TrebnicAPI):
        await db.set_setting("language", "ro")
        data = await api.export_data()
        assert data["settings"]["language"] == "ro"

    async def test_export_excludes_sensitive_settings(self, api: TrebnicAPI):
        await db.set_setting("encryption_key_hash", "secret123")
        await db.set_setting("resend_api_key", "re_xxx")
        data = await api.export_data()
        assert "encryption_key_hash" not in data["settings"]
        assert "resend_api_key" not in data["settings"]

    async def test_export_includes_recurrence_fields(self, api: TrebnicAPI):
        task = await api.add_task("Recurring export")
        await api.set_recurrence(task, RecurrenceFrequency.DAYS, interval=3, from_completion=True)
        data = await api.export_data()
        rec = [t for t in data["tasks"] if t["title"] == "Recurring export"]
        assert len(rec) == 1
        assert rec[0]["recurrent"] == 1
        assert rec[0]["recurrence_interval"] == 3
        assert rec[0]["recurrence_frequency"] == "days"
        assert rec[0]["recurrence_from_completion"] == 1

    async def test_export_includes_notes(self, api: TrebnicAPI):
        task = await api.add_task("With notes")
        task.notes = "Important details"
        await self._persist_task(api, task)
        data = await api.export_data()
        match = [t for t in data["tasks"] if t["title"] == "With notes"]
        assert len(match) == 1
        assert match[0]["notes"] == "Important details"

    @staticmethod
    async def _persist_task(api: TrebnicAPI, task: Task) -> None:
        await api._svc.task.persist_task(task)


# ===========================================================================
# import_data
# ===========================================================================

class TestImportData:
    async def _seed_and_export(self, api: TrebnicAPI) -> dict:
        """Create a representative dataset and export it."""
        p = api.projects[0]
        t1 = await api.add_task("Pending task", project_id=p.id, due_date=date(2026, 4, 1))
        t2 = await api.add_task("Done task", due_date=date(2026, 3, 20))
        await api.complete_task(t2, duration_seconds=1200, ended_at=datetime(2026, 3, 20, 17, 0))
        t3 = await api.add_task("Recurring")
        await api.set_recurrence(t3, RecurrenceFrequency.WEEKS, interval=2)
        await db.save_daily_note(date(2026, 3, 15), "Good day")
        await db.set_setting("language", "ro")
        await db.set_setting("default_estimated_minutes", 30)
        return await api.export_data()

    async def test_import_round_trip(self, api: TrebnicAPI):
        export1 = await self._seed_and_export(api)
        await api.import_data(export1)
        export2 = await api.export_data()
        # Compare everything except exported_at timestamp
        export1.pop("exported_at")
        export2.pop("exported_at")
        assert export1 == export2

    async def test_import_replaces_existing_data(self, api: TrebnicAPI):
        await api.add_task("Old task that should vanish")
        data = await api.export_data()
        # Clear the tasks from the export to import empty
        data["tasks"] = []
        data["time_entries"] = []
        await api.import_data(data)
        all_tasks = await api.get_tasks()
        done_tasks = await api.get_done_tasks()
        assert not any(t.title == "Old task that should vanish" for t in all_tasks + done_tasks)

    async def test_import_restores_tasks_with_ids(self, api: TrebnicAPI):
        export = await self._seed_and_export(api)
        original_ids = {t["id"] for t in export["tasks"]}
        await api.import_data(export)
        all_rows = await db.load_tasks()
        restored_ids = {r["id"] for r in all_rows}
        assert original_ids == restored_ids

    async def test_import_restores_time_entries(self, api: TrebnicAPI):
        export = await self._seed_and_export(api)
        await api.import_data(export)
        all_entries = await db.load_time_entries()
        assert len(all_entries) == len(export["time_entries"])
        for orig in export["time_entries"]:
            match = [e for e in all_entries if e["id"] == orig["id"]]
            assert len(match) == 1
            assert match[0]["task_id"] == orig["task_id"]

    async def test_import_restores_projects(self, api: TrebnicAPI):
        export = await self._seed_and_export(api)
        await api.import_data(export)
        loaded = await db.load_projects()
        assert len(loaded) == len(export["projects"])
        loaded_ids = {p["id"] for p in loaded}
        export_ids = {p["id"] for p in export["projects"]}
        assert loaded_ids == export_ids

    async def test_import_restores_daily_notes(self, api: TrebnicAPI):
        export = await self._seed_and_export(api)
        await api.import_data(export)
        notes = await db.get_all_daily_notes(limit=100)
        assert len(notes) == len(export["daily_notes"])

    async def test_import_restores_settings(self, api: TrebnicAPI):
        export = await self._seed_and_export(api)
        await api.import_data(export)
        lang = await db.get_setting("language")
        assert lang == "ro"
        est = await db.get_setting("default_estimated_minutes")
        assert est == 30

    async def test_import_updates_state(self, api: TrebnicAPI):
        export = await self._seed_and_export(api)
        # Wipe state to verify reload
        api.state.tasks.clear()
        api.state.done_tasks.clear()
        api.state.projects.clear()
        await api.import_data(export)
        assert len(api.state.projects) == len(export["projects"])
        total_tasks = len(api.state.tasks) + len(api.state.done_tasks)
        assert total_tasks == len(export["tasks"])

    async def test_import_emits_data_reset(self, api: TrebnicAPI):
        collector = EventCollector(AppEvent.DATA_RESET)
        export = await self._seed_and_export(api)
        await api.import_data(export)
        assert collector.count(AppEvent.DATA_RESET) == 1
        collector.cleanup()

    async def test_import_returns_summary(self, api: TrebnicAPI):
        export = await self._seed_and_export(api)
        summary = await api.import_data(export)
        assert summary["projects"] == len(export["projects"])
        assert summary["tasks"] == len(export["tasks"])
        assert summary["time_entries"] == len(export["time_entries"])
        assert summary["daily_notes"] == len(export["daily_notes"])

    async def test_import_rejects_invalid_version(self, api: TrebnicAPI):
        with pytest.raises(ValueError, match="Unsupported export version"):
            await api.import_data({"version": 99, "projects": [], "tasks": [], "time_entries": []})

    async def test_import_rejects_orphan_time_entries(self, api: TrebnicAPI):
        data = {
            "version": 1,
            "projects": [],
            "tasks": [{"id": 1, "title": "T1", "spent_seconds": 0, "estimated_seconds": 0}],
            "time_entries": [{"id": 1, "task_id": 999, "start_time": "2026-01-01T00:00:00", "end_time": None}],
        }
        with pytest.raises(ValueError, match="unknown task_id"):
            await api.import_data(data)

    async def test_import_rejects_orphan_project_refs(self, api: TrebnicAPI):
        data = {
            "version": 1,
            "projects": [],
            "tasks": [{"id": 1, "title": "T1", "project_id": "nonexistent", "spent_seconds": 0}],
            "time_entries": [],
        }
        with pytest.raises(ValueError, match="unknown project_id"):
            await api.import_data(data)

    async def test_import_empty_data(self, api: TrebnicAPI):
        data = {"version": 1, "projects": [], "tasks": [], "time_entries": [], "daily_notes": [], "settings": {}}
        summary = await api.import_data(data)
        assert summary["tasks"] == 0
        assert summary["projects"] == 0
        all_tasks = await api.get_tasks()
        assert len(all_tasks) == 0

    async def test_import_handles_null_optional_fields(self, api: TrebnicAPI):
        data = {
            "version": 1,
            "projects": [{"id": "p1", "name": "Proj", "icon": "", "color": "#fff"}],
            "tasks": [{
                "id": 1, "title": "Nullable", "spent_seconds": 0, "estimated_seconds": 900,
                "project_id": "p1", "due_date": None, "is_done": 0, "recurrent": 0,
                "recurrence_end_date": None, "notes": "",
            }],
            "time_entries": [{
                "id": 1, "task_id": 1, "start_time": "2026-03-01T10:00:00", "end_time": None,
            }],
            "daily_notes": [],
            "settings": {},
        }
        summary = await api.import_data(data)
        assert summary["tasks"] == 1
        tasks = await api.get_tasks()
        t = [t for t in tasks if t.title == "Nullable"]
        assert len(t) == 1
        assert t[0].due_date is None
