from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
import sqlite3

import pytest
import database as database_module
from database import db
from api import TrebnicAPI
from models.entities import Task
from services.notification_service import NotificationService, NotificationBackend
from tests.test_task_details import changes


async def test_reminder_survives_edits_export_and_next_occurrence(services):
    api = TrebnicAPI(services)
    task = await api.add_task("Example course")
    edit = changes()
    edit.update(due_date=date(2026, 11, 22), recurrent=True,
                reminder_time="19:00", reminder_weekdays=[1, 3, 5])
    await services.task.update_task_details(task, **edit)
    await api.log_time(task, 1800)
    row = await db.load_task_by_id(task.id)
    assert row["reminder_time"] == "19:00"
    assert row["reminder_weekdays"] == [1, 3, 5]
    backup = await db.export_all()
    await db.import_all(backup["projects"], backup["tasks"], backup["time_entries"],
                        backup["daily_notes"], backup["settings"])
    row = await db.load_task_by_id(task.id)
    assert row["spent_seconds"] == 1800
    assert row["reminder_weekdays"] == [1, 3, 5]
    next_task = await api.complete_task(task)
    assert next_task.reminder_time == "19:00"
    assert next_task.reminder_weekdays == [1, 3, 5]
    assert next_task.spent_seconds == 0
    assert NotificationService._custom_reminder_trigger(next_task, date(2026, 11, 19)) is None
    assert NotificationService._custom_reminder_trigger(next_task, date(2026, 11, 24)) == datetime(2026, 11, 24, 19)


def test_evening_and_weekday_schedule():
    task = Task("Example task", 0, 0, None, date(2026, 11, 16), reminder_time="19:00")
    trigger = NotificationService._custom_reminder_trigger
    assert trigger(task, date(2026, 11, 16)) == datetime(2026, 11, 16, 19)
    assert trigger(task, date(2026, 11, 15)) is None
    assert trigger(task, date(2026, 11, 17)) is None
    task.due_date = date(2026, 11, 22)
    task.reminder_weekdays = [1, 3, 5]
    assert trigger(task, date(2026, 11, 17)) == datetime(2026, 11, 17, 19)
    assert trigger(task, date(2026, 11, 18)) is None
    assert trigger(task, date(2026, 11, 24)) is None


async def test_custom_alarms_cancel_after_completion_or_disabling(services, monkeypatch):
    svc = NotificationService()
    monkeypatch.setattr(svc, "_backend", NotificationBackend.FLET_EXTENSION)
    schedule, cancel = AsyncMock(), AsyncMock()
    monkeypatch.setattr(svc, "_schedule_extension_notification", schedule)
    monkeypatch.setattr(svc, "_cancel_extension_notification", cancel)
    api = TrebnicAPI(services)
    task = await api.add_task("Example task")
    edit = changes()
    edit.update(due_date=date.today()+timedelta(days=1), reminder_time="19:00")
    await services.task.update_task_details(task, **edit)
    await svc._schedule_custom_reminders()
    assert schedule.await_count == 1
    notification_id = schedule.call_args.args[0]
    assert schedule.call_args.kwargs["schedule_mode"] == "exact_allow_while_idle"
    assert task.id == schedule.call_args.args[4]
    assert not await svc._load_task_nudge_candidates(task.due_date)
    await api.complete_task(task)
    await svc._cancel_custom_reminders()
    cancel.assert_awaited_once_with(notification_id)
    schedule.reset_mock()
    await svc._schedule_custom_reminders()
    schedule.assert_not_awaited()


async def test_upgrade_snapshots_old_database_without_losing_rows(services, tmp_path):
    await db.close()
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, spent_seconds INTEGER, estimated_seconds INTEGER, project_id TEXT, due_date TEXT, is_done INTEGER, recurrent INTEGER, recurrence_interval INTEGER, recurrence_frequency TEXT, recurrence_weekdays TEXT, notes TEXT)")
        conn.execute("INSERT INTO tasks VALUES (42,'Keep me',0,900,NULL,'2026-11-16',0,0,1,'weeks','[]','Keep note')")
    database_module.DB_PATH = path
    db._initialized = False
    await db.init_db()
    row = await db.load_task_by_id(42)
    assert row["title"] == "Keep me" and row["notes"] == "Keep note"
    assert row["reminder_time"] is None and row["reminder_weekdays"] == []
    with sqlite3.connect(tmp_path / "trebnic-before-reminders.db") as backup:
        assert backup.execute("SELECT title, notes FROM tasks").fetchone() == ("Keep me", "Keep note")


@pytest.mark.parametrize("value", ["25:00", "19:20:30", "abc"])
async def test_invalid_reminder_cannot_change_task(services, value):
    task = await TrebnicAPI(services).add_task("Keep me")
    before = task.to_dict()
    with pytest.raises(ValueError):
        await services.task.update_task_details(task, **changes(reminder_time=value))
    assert task.to_dict() == before


async def test_undated_reminders_group_without_deadlines_and_stop_when_done(services, monkeypatch):
    api = TrebnicAPI(services)
    books = []
    for title in ("Book one", "Book two"):
        book = await api.add_task(title, estimated_seconds=18000)
        edit = changes()
        edit.update(
            title=title, estimated_seconds=18000, due_date=None, recurrent=False,
            reminder_time="20:00", reminder_weekdays=[6])
        await services.task.update_task_details(book, **edit)
        books.append(book)
    trigger = NotificationService._custom_reminder_trigger
    assert trigger(books[0], date(2026, 11, 22)) == datetime(2026, 11, 22, 20)
    assert trigger(books[0], date(2026, 11, 23)) is None
    svc = NotificationService()
    schedule = AsyncMock()
    monkeypatch.setattr(svc, "_schedule_extension_notification", schedule)
    await svc._schedule_custom_reminders()
    assert 5 <= schedule.await_count <= 6
    for call in schedule.call_args_list:
        assert "Book one" in call.args[2] and "Book two" in call.args[2]
        assert call.kwargs["actions"] is None
    ids = await db.get_setting("custom_reminder_alarm_ids", [])
    assert len(ids) == len(set(ids)) == schedule.await_count
    await api.complete_task(books[0])
    assert trigger(books[0], date(2026, 11, 22)) is None
    schedule.reset_mock()
    await svc._schedule_custom_reminders()
    assert all("Book one" not in c.args[2] for c in schedule.call_args_list)
    row = await db.load_task_by_id(books[1].id)
    assert row["due_date"] is None and not row["recurrent"]
    assert row["estimated_seconds"] == 18000 and row["postponements"] == 0

    deliver = AsyncMock()
    monkeypatch.setattr(svc, "_deliver_immediate", deliver)
    monkeypatch.setattr(svc, "_is_in_quiet_hours", lambda: False)
    await svc._fire_custom_reminders(datetime(2026, 11, 22, 20, 1))
    await svc._fire_custom_reminders(datetime(2026, 11, 22, 20, 2))
    assert deliver.await_count == 1
    assert "Book two" in deliver.call_args.args[1]
    assert "Book one" not in deliver.call_args.args[1]


async def test_undated_reminder_requires_explicit_weekday(services):
    book = await TrebnicAPI(services).add_task("Book")
    with pytest.raises(ValueError, match="details_reminder_needs_date"):
        edit = changes()
        edit.update(due_date=None, recurrent=False, reminder_time="20:00", reminder_weekdays=[])
        await services.task.update_task_details(book, **edit)
