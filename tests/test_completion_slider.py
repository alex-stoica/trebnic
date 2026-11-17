from unittest.mock import Mock, AsyncMock

from api import TrebnicAPI
from database import db
from ui.handlers.task_action_handler import TaskActionHandler


def handler(services):
    h = TaskActionHandler.__new__(TaskActionHandler)
    h._page = Mock()
    h._service = services.task
    h._time_entry_svc = services.time_entry
    h._refresh_ui = Mock()
    h._refresh_ui_async = None
    h._snack = Mock()
    h._timer_ctrl = Mock()
    h._timer_ctrl.timer_svc.running = False
    return h


async def test_quarter_hour_completion_records_actual_time(services, monkeypatch):
    task = await TrebnicAPI(services).add_task("Work", estimated_seconds=3600)
    h = handler(services)
    h._show_completion_time(task)
    dialog = h._page.show_dialog.call_args.args[0]
    monkeypatch.setattr(type(dialog), "update", lambda self: None)
    slider = dialog.content.content.controls[2]
    assert (slider.max - slider.min) / slider.divisions == 15
    assert slider.max == 240
    assert slider.value == 15  # Never substitute the estimate for actual work.
    slider.value = 45
    dialog.actions[2].on_click(None)
    fn, minutes = h._page.run_task.call_args.args
    await fn(minutes)
    entries = await services.time_entry.load_time_entries_for_task(task.id)
    assert len(entries) == 1
    assert (entries[0].end_time - entries[0].start_time).total_seconds() == 2700
    assert (await db.load_task_by_id(task.id))["is_done"]


async def test_skip_completes_without_fabricating_time(services, monkeypatch):
    task = await TrebnicAPI(services).add_task("Skip")
    h = handler(services)
    h._show_completion_time(task)
    dialog = h._page.show_dialog.call_args.args[0]
    monkeypatch.setattr(type(dialog), "update", lambda self: None)
    dialog.actions[1].on_click(None)
    fn, minutes = h._page.run_task.call_args.args
    await fn(minutes)
    assert not await services.time_entry.load_time_entries_for_task(task.id)
    assert (await db.load_task_by_id(task.id))["is_done"]


async def test_existing_time_bypasses_slider(services):
    api = TrebnicAPI(services)
    task = await api.add_task("Tracked")
    await api.log_time(task, 600)
    h = handler(services)
    h._show_completion_time = Mock()
    h._do_complete_async = AsyncMock()
    h._on_complete(task)
    await h._page.run_task.call_args.args[0]()
    h._show_completion_time.assert_not_called()
    h._do_complete_async.assert_awaited_once_with(task)


async def test_recurring_task_also_requests_duration(services):
    task = await TrebnicAPI(services).add_task("Daily")
    task.recurrent = True
    h = handler(services)
    h._show_completion_time = Mock()
    h._do_complete_async = AsyncMock()
    h._on_complete(task)
    await h._page.run_task.call_args.args[0]()
    h._show_completion_time.assert_called_once_with(task)
    h._do_complete_async.assert_not_awaited()


async def test_retry_does_not_duplicate_saved_time(services, monkeypatch):
    task = await TrebnicAPI(services).add_task("Retry")
    h = handler(services)
    h._do_complete_async = AsyncMock(side_effect=[RuntimeError("save failed"), None])
    h._show_completion_time(task)
    dialog = h._page.show_dialog.call_args.args[0]
    monkeypatch.setattr(type(dialog), "update", lambda self: None)
    dialog.actions[2].on_click(None)
    fn, minutes = h._page.run_task.call_args.args
    await fn(minutes)
    await fn(minutes)
    assert len(await services.time_entry.load_time_entries_for_task(task.id)) == 1
