from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from api import TrebnicAPI
from config import INACTIVITY_NOTIFICATION_ID
from database import db
from events import AppEvent, event_bus
from models.entities import TimeEntry
from registry import registry
from services.chatgpt_bridge import ChatGPTBridge
from services.notification_service import NotificationBackend, NotificationService


def make_service(services, monkeypatch):
    NotificationService.reset_instance()
    svc = NotificationService()
    svc._get_state = lambda: services.state
    monkeypatch.setattr(svc, "_backend", NotificationBackend.FLET_EXTENSION)
    monkeypatch.setattr(svc, "_is_app_locked", lambda: False)
    monkeypatch.setattr(svc, "_schedule_extension_notification", AsyncMock(return_value=True))
    monkeypatch.setattr(svc, "_cancel_extension_notification", AsyncMock())
    return svc


async def test_connect_closes_only_after_success():
    bridge = ChatGPTBridge.__new__(ChatGPTBridge)
    bridge.page = Mock()
    bridge.url, bridge.token, bridge.status = "", "", "Disconnected"
    bridge.start = AsyncMock()
    bridge.show()
    dialog = bridge.page.show_dialog.call_args.args[0]
    await dialog.actions[1].on_click(None)
    bridge.page.pop_dialog.assert_called_once()
    bridge.page.pop_dialog.reset_mock()
    bridge.start.side_effect = ValueError("unavailable")
    await dialog.actions[1].on_click(None)
    bridge.page.pop_dialog.assert_not_called()
    assert "Could not connect" in dialog.content.controls[-1].value


def test_ten_hours_from_digest_without_crossing_into_tomorrow():
    state = SimpleNamespace(daily_digest_enabled=True, daily_digest_time=time(8))
    target = date(2026, 11, 22)
    assert NotificationService._inactivity_trigger(state, target) == datetime(2026, 11, 22, 18)
    state.daily_digest_enabled = False
    assert NotificationService._inactivity_trigger(state, target) is None
    state.daily_digest_enabled = True
    state.daily_digest_time = time(20)
    assert NotificationService._inactivity_trigger(state, target) is None


async def test_separate_alarms_and_activity_cancels_today(services, monkeypatch):
    svc = make_service(services, monkeypatch)
    api = TrebnicAPI(services)
    today = date.today()
    first = await api.add_task("First", due_date=today)
    second = await api.add_task("Second", due_date=today)
    await api.add_task("Tomorrow", due_date=today + timedelta(days=1))
    monkeypatch.setattr(svc, "_inactivity_trigger", lambda state, target:
                        datetime.combine(target, time.max))
    await svc._schedule_inactivity_reminders(services.state)
    calls = svc._schedule_extension_notification.call_args_list
    assert len(calls) == 3
    assert len({call.kwargs["notification_id"] for call in calls}) == 3
    for call in calls:
        assert call.kwargs["notification_id"] >= INACTIVITY_NOTIFICATION_ID
        assert [a["id"] for a in call.kwargs["actions"]] == [
            "task_complete_with_time", "task_postpone_1d", "task_cancel"]
        assert all(a["shows_user_interface"] for a in call.kwargs["actions"])
    old_ids = await db.get_setting("inactivity_alarm_ids", [])
    await api.log_time(first, 60)
    assert await db.has_task_activity_on(today)
    await svc._cancel_inactivity_reminders()
    assert {c.args[0] for c in svc._cancel_extension_notification.call_args_list} == set(old_ids)
    svc._schedule_extension_notification.reset_mock()
    await svc._schedule_inactivity_reminders(services.state)
    assert svc._schedule_extension_notification.await_count == 1
    assert svc._schedule_extension_notification.call_args.kwargs["title"] == "Tomorrow"
    assert second.id not in [t.id for t in await svc._inactivity_tasks(today)]


async def test_old_or_other_task_activity_does_not_suppress_today(services, monkeypatch):
    svc = make_service(services, monkeypatch)
    api = TrebnicAPI(services)
    task = await api.add_task("Today", due_date=date.today())
    other = await api.add_task("Unscheduled")
    await api.log_time(other, 60)
    await api.log_time(task, 60, ended_at=datetime.now() - timedelta(days=1))
    assert not await db.has_task_activity_on(date.today())
    assert [t.id for t in await svc._inactivity_tasks(date.today())] == [task.id]
    await api.complete_task(task)
    assert await db.has_task_activity_on(date.today())
    assert await svc._inactivity_tasks(date.today()) == []


async def test_active_timer_suppresses_before_first_time_write(services, monkeypatch):
    svc = make_service(services, monkeypatch)
    task = await TrebnicAPI(services).add_task("Today", due_date=date.today())
    monkeypatch.setattr(registry, "get", lambda key: SimpleNamespace(running=True, active_task=task))
    assert not await db.has_task_activity_on(date.today())
    assert await svc._inactivity_tasks(date.today()) == []


async def test_cross_midnight_work_counts_but_failed_task_does_not(services):
    api = TrebnicAPI(services)
    task = await api.add_task("Today", due_date=date.today())
    await services.task.complete_task(task, failed=True)
    assert not await db.has_task_activity_on(date.today())
    start = datetime.combine(date.today(), time.min)
    entry = TimeEntry(task_id=task.id, start_time=start - timedelta(minutes=5),
                      end_time=start + timedelta(seconds=1))
    await services.time_entry.save_entry_with_recompute(entry)
    assert await db.has_task_activity_on(date.today())


async def test_desktop_reminder_once_and_empty_day_silent(services, monkeypatch):
    svc = make_service(services, monkeypatch)
    api = TrebnicAPI(services)
    await api.add_task("Today", due_date=date.today())
    services.state.daily_digest_enabled = True
    services.state.daily_digest_time = time(8)
    monkeypatch.setattr(svc, "_is_in_quiet_hours", lambda: False)
    deliver = AsyncMock()
    monkeypatch.setattr(svc, "_deliver_immediate", deliver)
    await svc._fire_inactivity_reminder(services.state, datetime.combine(date.today(), time(17, 59)))
    deliver.assert_not_awaited()
    now = datetime.combine(date.today(), time(18))
    await svc._fire_inactivity_reminder(services.state, now)
    await svc._fire_inactivity_reminder(services.state, now + timedelta(minutes=1))
    deliver.assert_awaited_once()
    assert deliver.call_args.kwargs["title"] == "Today"
    await svc._fire_inactivity_reminder(services.state, now + timedelta(days=1))
    assert deliver.await_count == 1


async def test_timer_and_manual_progress_request_reschedule(services, monkeypatch):
    svc = make_service(services, monkeypatch)
    request = Mock()
    monkeypatch.setattr(svc, "request_reschedule", request)
    svc._subscribe_to_events()
    api = TrebnicAPI(services)
    task = await api.add_task("Today", due_date=date.today())
    request.reset_mock()
    event_bus.emit(AppEvent.TIMER_STARTED, task)
    request.assert_called_once()
    request.reset_mock()
    await api.log_time(task, 60)
    request.assert_called_once()
    svc._unsubscribe_from_events()


@pytest.mark.parametrize("action,event", [
    ("task_complete_with_time", AppEvent.TASK_COMPLETE_WITH_TIME_REQUESTED),
    ("task_cancel", AppEvent.TASK_FAIL_REQUESTED),
])
async def test_action_opens_dialog_without_completing(services, monkeypatch, action, event):
    import app
    api = TrebnicAPI(services)
    task = await api.add_task("Today", due_date=date.today())
    emitted = Mock()
    monkeypatch.setattr(app.event_bus, "emit", emitted)
    monkeypatch.setattr(app.notification_service, "_is_app_locked", lambda: False)
    view = SimpleNamespace(page=Mock(), nav_manager=Mock(), service=services.task,
                           state=services.state, snack=Mock())
    app.TrebnicApp._on_notification_tapped(view, {
        "action_id": action, "task_id": task.id})
    await view.page.run_task.call_args.args[0]()
    emitted.assert_called_once_with(event,
                                   services.state.get_task_by_id(task.id))
    assert not (await db.load_task_by_id(task.id))["is_done"]
