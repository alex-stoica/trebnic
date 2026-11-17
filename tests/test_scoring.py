from datetime import date, timedelta
import pytest
from api import TrebnicAPI
from database import db
from models.entities import Task
from services.scoring import progress, base_points, completion_points
from services.stats import stats_service


async def snapshot(services):
    await services.task.refresh_state_tasks()
    return progress(services.state.tasks, services.state.done_tasks)


async def test_initial_estimate_and_all_date_edit_paths(services):
    api = TrebnicAPI(services)
    task = await api.add_task("One hour", estimated_seconds=3600, due_date=date.today())
    await services.task.set_task_estimate(task, 7200)
    assert base_points(task) == 4
    for _ in range(7):
        await services.task.postpone_task(task)
    assert task.postponements == 7
    assert completion_points(task) == 2
    await api.log_time(task, 5400)
    await api.complete_task(task)
    p = await snapshot(services)
    assert p.score == 3.5
    assert p.xp == 3.5
    await api.complete_task(task)
    assert (await snapshot(services)).score == 3.5


async def test_unknown_tasks_and_first_scheduling_have_no_penalty(services):
    task = await TrebnicAPI(services).add_task("Unknown")
    await services.task.set_task_due_date(task, date.today())
    await services.task.postpone_task(task)
    assert task.postponements == 0
    await services.task.set_task_estimate(task, 1800)
    await services.task.set_task_due_date(task, task.due_date + timedelta(days=1))
    assert task.postponements == 1
    await services.task.set_task_due_date(task, None)
    assert task.postponements == 2
    await services.task.set_task_due_date(task, date.today())
    assert task.postponements == 2


async def test_failure_keeps_effort_excludes_completion_and_can_be_reopened(services):
    api = TrebnicAPI(services)
    task = await api.add_task("Try", estimated_seconds=3600, due_date=date.today())
    await api.log_time(task, 5400)
    await services.task.complete_task(task, failed=True)
    p = await snapshot(services)
    assert p.score == pytest.approx(-2.1)
    assert p.xp == 1.5
    assert p.level == 1
    stats = stats_service.calculate_overall_stats([], services.state.done_tasks, [])
    assert stats.total_tasks_completed == 0
    assert stats_service.calculate_completion_streak(services.state.done_tasks) == 0
    await services.task.uncomplete_task(task)
    assert (await snapshot(services)).score == 1.5
    await api.complete_task(task)
    assert (await snapshot(services)).score == 5.5


async def test_time_edit_delete_adjusts_points(services):
    task = await TrebnicAPI(services).add_task("Effort only")
    await TrebnicAPI(services).log_time(task, 1800)
    assert (await snapshot(services)).score == .5
    entry = (await services.time_entry.load_time_entries_for_task(task.id))[0]
    entry.start_time = entry.end_time - timedelta(hours=2)
    await services.time_entry.save_entry_with_recompute(entry)
    assert (await snapshot(services)).score == 2
    await services.time_entry.delete_entry_with_recompute(entry.id)
    assert (await snapshot(services)).score == 0


async def test_recurring_failure_and_duplicate_start_fresh(services):
    api = TrebnicAPI(services)
    task = await api.add_task("Daily", estimated_seconds=900, due_date=date.today())
    task.recurrent = True
    await services.task.persist_task(task)
    await services.task.postpone_task(task)
    next_task = await services.task.complete_task(task, failed=True)
    assert next_task and not next_task.is_failed and next_task.postponements == 0
    copy = await services.task.duplicate_task(task)
    assert not copy.is_failed and copy.postponements == 0 and copy.spent_seconds == 0
    assert (await db.load_task_by_id(task.id))["is_failed"] == 1


async def test_export_import_preserves_scoring(services):
    task = await TrebnicAPI(services).add_task("Export", estimated_seconds=3600, due_date=date.today())
    await services.task.postpone_task(task)
    await services.task.set_task_estimate(task, 7200)
    await services.task.complete_task(task, failed=True)
    data = await db.export_all()
    await db.import_all(data["projects"], data["tasks"], data["time_entries"], data["daily_notes"], data["settings"])
    row = await db.load_task_by_id(task.id)
    assert row["initial_estimated_seconds"] == 3600
    assert row["postponements"] == 1 and row["is_failed"] == 1
    assert (await snapshot(services)).score == pytest.approx(-3.6)


def test_levels_and_failure_do_not_reduce_xp():
    done = Task("Done", 3600, 44100, None, None)
    failed = Task("Failed", 0, 9000, None, None, is_failed=True)
    p = progress([], [done, failed])
    assert p.xp == 50 and p.level == 2 and p.fraction == 0
    assert p.score == 41


def test_starting_baseline_keeps_old_work_without_awarding_retroactive_points():
    pending = Task("Example task", 2700, 0, None, None, id=1, points_time_baseline_seconds=2700)
    old = Task("Old", 3600, 3600, None, None, id=2,
               points_time_baseline_seconds=3600, points_excluded=True)
    p = progress([pending], [old])
    assert p.score == p.xp == 0 and p.level == 1
    pending.spent_seconds += 1800
    assert progress([pending], [old]).xp == .5
