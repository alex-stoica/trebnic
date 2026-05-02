"""Pure-function unit tests for NotificationService task-nudge helpers.

These tests deliberately avoid the `services` fixture from conftest.py — that
fixture deadlocks on Windows (see insights/errors.md). All cases here exercise
helper methods that don't touch the database, registry, or page.
"""
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
    assert ids == ["task_done", "task_postpone_1d", "open_task"]
    for a in actions:
        assert a["shows_user_interface"] is True
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
