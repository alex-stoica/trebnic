"""Notification helpers and extension integration tests."""
import asyncio
import json
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from i18n import t
from models.entities import Task
from services.notification_service import FletAndroidNotifications, NotificationService, db


@pytest.fixture
def svc() -> NotificationService:
    NotificationService.reset_instance()
    return NotificationService()


def _make_task(due: date, title: str = "Buy milk", task_id: int = 42) -> Task:
    return Task(
        title=title,
        spent_seconds=0,
        estimated_seconds=900,
        project_id=None,
        due_date=due,
        id=task_id,
    )


def test_task_nudge_payload_shape(svc: NotificationService) -> None:
    target = date(2026, 5, 2)
    task = _make_task(due=target, task_id=7)
    payload = svc._task_nudge_payload(task, target)
    assert payload == {"kind": "task_nudge", "task_id": 7, "target_date": "2026-05-02"}


def test_task_nudge_actions_shape(svc: NotificationService) -> None:
    actions = svc._task_nudge_actions()
    ids = [a["id"] for a in actions]
    assert ids == ["task_done", "task_postpone_1d", "task_start"]
    assert actions[0]["shows_user_interface"] is False
    assert actions[1]["shows_user_interface"] is False
    assert actions[2]["shows_user_interface"] is True
    assert actions[2]["title"] == t("notif_action_start")
    for a in actions:
        assert a["cancel_notification"] is True
        assert a["title"]


def test_task_nudge_text_due_today(svc: NotificationService) -> None:
    target = date(2026, 5, 2)
    task = _make_task(due=target, title="Submit report")
    title, body = svc._task_nudge_text(task, target)
    assert title == "Submit report"
    assert body == t("task_nudge_due_today_body")


def test_task_nudge_text_overdue(svc: NotificationService) -> None:
    target = date(2026, 5, 2)
    overdue = date(2026, 4, 28)
    task = _make_task(due=overdue, title="File taxes")
    title, body = svc._task_nudge_text(task, target)
    assert title == "File taxes"
    assert overdue.strftime("%b %d") in body


def test_task_nudge_summary_count(svc: NotificationService) -> None:
    target = date(2026, 5, 2)
    candidates = [_make_task(due=target, title=f"t{i}", task_id=i) for i in range(5)]
    title, body, _style = svc._task_nudge_summary(candidates)
    assert "5" in title
    assert body == t("task_nudges_summary_body")


def test_locked_task_nudge_text_hides_details(svc: NotificationService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_is_app_locked", lambda: True)
    target = date(2026, 5, 2)
    task = _make_task(due=target, title="Private task")
    title, body = svc._task_nudge_text(task, target)
    assert title == t("task_reminder")
    assert body == t("unlock_to_see_details")


def test_locked_task_nudge_summary_uses_count(svc: NotificationService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_is_app_locked", lambda: True)
    target = date(2026, 5, 2)
    candidates = [_make_task(due=target, title=f"t{i}", task_id=i) for i in range(3)]
    title, body, style = svc._task_nudge_summary(candidates)
    assert title == t("task_nudge_count_many").replace("{count}", "3")
    assert body == t("unlock_to_see_details")
    assert style is None


def test_next_trigger_time_today_when_target_after_now(svc: NotificationService) -> None:
    now = datetime.now()
    target = (now + timedelta(hours=1)).time().replace(microsecond=0)
    trigger = svc._next_trigger_time(target)
    assert trigger.date() == now.date()


def test_next_trigger_time_tomorrow_when_target_before_now(svc: NotificationService) -> None:
    now = datetime.now()
    target = (now - timedelta(hours=1)).time().replace(microsecond=0)
    trigger = svc._next_trigger_time(target)
    assert trigger.date() == (now + timedelta(days=1)).date()


@pytest.mark.asyncio
async def test_notification_reschedule_requests_are_coalesced(
    svc: NotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_schedule_all() -> None:
        nonlocal calls
        calls += 1

    def schedule_async(fn):
        return asyncio.create_task(fn())

    monkeypatch.setattr(svc, "_schedule_all_digests", fake_schedule_all)
    svc._schedule_async = schedule_async
    svc._running = True
    svc._reschedule_debounce_seconds = 0.01

    for _ in range(5):
        svc.request_reschedule("test")

    await asyncio.sleep(0.05)
    assert calls == 1


@pytest.mark.asyncio
async def test_notification_reschedule_reruns_when_dirty_during_rebuild(
    svc: NotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_schedule_all() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            svc.request_reschedule("during_rebuild")

    def schedule_async(fn):
        return asyncio.create_task(fn())

    monkeypatch.setattr(svc, "_schedule_all_digests", fake_schedule_all)
    svc._schedule_async = schedule_async
    svc._running = True
    svc._reschedule_debounce_seconds = 0.01

    svc.request_reschedule("first", urgent=True)

    await asyncio.sleep(0.05)
    assert calls == 2


def test_notification_resume_reschedule_only_when_stale(
    svc: NotificationService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued = 0

    def fake_request(reason: str = "change", *, urgent: bool = False) -> None:
        nonlocal queued
        queued += 1

    monkeypatch.setattr(svc, "request_reschedule", fake_request)
    svc._running = True
    svc._last_reschedule_at = datetime.now()

    assert svc.request_reschedule_if_stale("resume") is False
    assert queued == 0

    svc._last_reschedule_at = datetime.now() - timedelta(minutes=20)
    assert svc.request_reschedule_if_stale("resume") is True
    assert queued == 1


@pytest.fixture
def bridge(svc, monkeypatch):
    invoke = AsyncMock(return_value="ok")
    monkeypatch.setattr(FletAndroidNotifications, "_invoke_method", invoke)
    svc._flet_notifications = FletAndroidNotifications()
    return invoke


@pytest.mark.asyncio
@pytest.mark.parametrize("encrypted,unlocked", [(False, False), (False, True), (True, False), (True, True)])
async def test_auth_initialization_controls_notification_privacy(svc, monkeypatch, encrypted, unlocked):
    import app
    from services.notification_service import registry

    monkeypatch.setattr(registry, "get", lambda _: SimpleNamespace(is_available=True, is_unlocked=False))
    monkeypatch.setattr(app, "notification_service", svc)
    reschedule = Mock()
    monkeypatch.setattr(svc, "request_reschedule", reschedule)

    async def initialize():
        assert svc._is_app_locked()

    auth = SimpleNamespace(
        initialize=AsyncMock(side_effect=initialize),
        is_encryption_enabled=encrypted, is_unlocked=unlocked,
        needs_unlock=encrypted and not unlocked,
        set_unlock_callback=Mock(), set_lock_callback=Mock(), show_unlock_dialog=Mock(),
    )
    await app.TrebnicApp._init_auth(SimpleNamespace(auth_ctrl=auth))
    assert svc._is_app_locked() == (encrypted and not unlocked)
    reschedule.assert_called_once_with("auth_initialized", urgent=True)
    auth.is_encryption_enabled = True
    auth.is_unlocked = False
    assert svc._is_app_locked()
    auth.is_unlocked = True
    assert not svc._is_app_locked()


@pytest.mark.asyncio
@pytest.mark.parametrize("day", ["2026-10-24", "2026-10-25", "2027-03-27", "2027-03-28"])
async def test_scheduled_nudge_preserves_instant_and_actions(svc, bridge, day):
    trigger = datetime.fromisoformat(day + "T09:00:00").replace(tzinfo=ZoneInfo("Europe/Bucharest"))
    task = _make_task(trigger.date(), task_id=7)
    assert await svc._schedule_extension_notification(
        10000, task.title, "Due today", trigger, task.id,
        actions=svc._task_nudge_actions(),
        payload=svc._task_nudge_payload(task, trigger.date()),
    )
    args = bridge.call_args.kwargs["arguments"]
    assert args["scheduled_epoch_ms"] == int(trigger.timestamp() * 1000)
    assert args["time_zone"] == "Europe/Bucharest"
    assert args["match_date_time_components"] is None
    assert json.loads(args["payload"]) == {
        "kind": "task_nudge", "task_id": 7, "target_date": day,
    }
    assert [a["id"] for a in args["actions"]] == ["task_done", "task_postpone_1d", "task_start"]


@pytest.mark.asyncio
async def test_immediate_digest_reaches_extension(svc, bridge):
    assert await svc._deliver_extension_notification(
        "Trebnic", "One overdue task", notification_id=42,
        actions=[{"id": "open_tasks", "title": "Open"}],
    )
    assert bridge.call_args.kwargs["method_name"] == "show_notification"
    args = bridge.call_args.kwargs["arguments"]
    assert args["id"] == 42
    assert args["style"]["big_text"] == "One overdue task"
    assert args["actions"][0]["id"] == "open_tasks"


@pytest.mark.asyncio
async def test_native_failure_is_not_reported_as_delivery(svc, bridge):
    bridge.return_value = "error:permission denied"
    assert not await svc._deliver_extension_notification("Trebnic", "Test")


@pytest.mark.asyncio
async def test_disabling_notifications_cancels_the_entire_horizon(svc, bridge, monkeypatch):
    monkeypatch.setattr(svc, "_is_notifications_enabled", lambda: False)
    await svc._schedule_all_digests()
    calls = bridge.call_args_list
    assert all(c.kwargs["method_name"] == "cancel" for c in calls)
    cancelled = {c.kwargs["arguments"]["id"] for c in calls}
    expected = {
        base + day * 1000
        for base in (9000, 9001, 9002, 10000, 10001, 10002, 10099, 20000, 20001, 20002, 20099)
        for day in range(7)
    }
    assert cancelled == expected


@pytest.mark.asyncio
async def test_digest_and_task_alarms_never_replace_each_other(svc, bridge, monkeypatch):
    state = SimpleNamespace()
    for name in ("daily_digest", "evening_preview", "overdue_nudge", "task_nudge"):
        setattr(state, name + "_time", time(9))
        setattr(state, ("task_nudges" if name == "task_nudge" else name) + "_enabled", True)
    monkeypatch.setattr(db, "load_tasks_filtered", AsyncMock(return_value=[{"id": 1}]))
    for name in ("_build_morning_digest", "_build_evening_preview", "_build_overdue_nudge"):
        monkeypatch.setattr(svc, name, AsyncMock(return_value=("Digest", "Tasks", None)))
    monkeypatch.setattr(svc, "_load_task_nudge_candidates", AsyncMock(return_value=[
        _make_task(date(2026, 9, 25), task_id=i) for i in range(4)
    ]))
    monkeypatch.setattr(svc, "_is_app_locked", lambda: False)
    await svc._schedule_android_digests(state)
    calls = bridge.call_args_list
    assert len(calls) == 49
    assert all(c.kwargs["method_name"] == "schedule_notification" for c in calls)
    assert len({c.kwargs["arguments"]["id"] for c in calls}) == 49
