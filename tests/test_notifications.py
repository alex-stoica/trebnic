"""Pure-function unit tests for NotificationService task-nudge helpers.

These tests deliberately avoid the `services` fixture from conftest.py — that
fixture deadlocks on Windows (see insights/errors.md). All cases here exercise
helper methods that don't touch the database, registry, or page.
"""
import asyncio
from datetime import date, datetime, time, timedelta

import pytest

from i18n import t
from models.entities import Task
from services.notification_service import NotificationService


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
