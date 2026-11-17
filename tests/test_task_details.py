from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock

import pytest
from api import TrebnicAPI
from database import db, DatabaseError
from models.entities import Task, AppState
from ui.dialogs.task_details import TaskDetailsPanel
from ui.components.task_tile import TaskTile
from i18n import set_language


def changes(**overrides):
    return dict(title="Clarified", estimated_seconds=2700, due_date=date.today(),
                project_id=None, notes="Context\nNext step", recurrent=False,
                frequency="weeks", interval=1, weekdays=[], from_completion=False,
                until=None, **overrides)


def test_calendar_keeps_the_local_selected_day():
    page = Mock()
    panel = TaskDetailsPanel(page, AppState(), Mock(), Task("Interview", 0, 3600, None, None), Mock())
    panel.pick_date(None)
    picker = page.show_dialog.call_args.args[0]
    local_midnight = datetime(2026, 11, 16, tzinfo=datetime.now().astimezone().tzinfo)
    picker.on_change(Mock(control=Mock(value=local_midnight.astimezone(timezone.utc))))
    assert panel.due == date(2026, 11, 16)


async def test_capture_unknown_then_edit_preserves_time_and_completion(services):
    api = TrebnicAPI(services)
    task = await api.add_task("Idea")
    assert task.due_date is None and task.estimated_seconds == 0
    await api.log_time(task, 1200)
    await api.complete_task(task)
    await services.task.update_task_details(task, **changes())
    row = await db.load_task_by_id(task.id)
    assert row["is_done"] and row["spent_seconds"] == 1200
    assert row["notes"] == "Context\nNext step" and row["estimated_seconds"] == 2700
    edited = changes()
    edited.update(notes="", estimated_seconds=0, due_date=None)
    await services.task.update_task_details(task, **edited)
    row = await db.load_task_by_id(task.id)
    assert row["notes"] == "" and row["estimated_seconds"] == 0
    assert row["is_done"] and row["spent_seconds"] == 1200


async def test_editor_recurrence_survives_completion(services):
    api = TrebnicAPI(services)
    task = await api.add_task("Repeat")
    edit = changes()
    edit.update(recurrent=True, frequency="days", interval=2, due_date=None,
                until=date.today()+timedelta(days=30))
    await services.task.update_task_details(task, **edit)
    next_task = await api.complete_task(task)
    assert next_task.due_date == task.due_date + timedelta(days=2)
    assert next_task.notes == task.notes


@pytest.mark.parametrize("invalid", [{"title":" "},{"estimated_seconds":-1},
    {"estimated_seconds":True},{"project_id":"missing"},
    {"recurrent":True,"interval":0}, {"recurrent":True,"until":date(2000,1,1)}])
async def test_invalid_details_do_not_mutate(services, invalid):
    task = await TrebnicAPI(services).add_task("Original")
    before = task.to_dict()
    edit = changes()
    edit.update(invalid)
    with pytest.raises(ValueError):
        await services.task.update_task_details(task, **edit)
    assert task.to_dict() == before
    assert (await db.load_task_by_id(task.id))["title"] == "Original"


async def test_failed_write_keeps_original_metadata(services, monkeypatch):
    task = await TrebnicAPI(services).add_task("Original")
    before = task.to_dict()
    monkeypatch.setattr(services.task, "persist_task", AsyncMock(side_effect=DatabaseError("failed")))
    with pytest.raises(DatabaseError):
        await services.task.update_task_details(task, **changes())
    assert task.to_dict() == before


@pytest.mark.parametrize("language", ["en", "ro"])
def test_mobile_pending_and_done_show_time_and_unknown_estimate(language):
    set_language(language)
    try:
        state = AppState(is_mobile=True)
        task = Task("Idea",1200,0,None,None,id=1)
        for done in [False, True]:
            tile = TaskTile(task, done, state).build()
            summary = tile.content.controls[1].controls[-1] if done else tile.content.controls[-1]
            assert "20 min" in summary.value
            assert ("Neestimat" if language == "ro" else "Not estimated") in summary.value
    finally:
        set_language("en")


async def test_panel_saves_empty_estimate_and_notes(services):
    task = await TrebnicAPI(services).add_task("Idea", estimated_seconds=900)
    page = Mock(height=800)
    panel = TaskDetailsPanel(page, services.state, services.task, task, Mock())
    panel.open()
    panel.estimate.value = ""
    panel.notes.value = "Test note"
    await panel.save(None)
    assert not panel.error.visible
    assert task.estimated_seconds == 0 and task.notes == "Test note"
    page.pop_dialog.assert_called_once()
