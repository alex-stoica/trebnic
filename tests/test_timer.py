import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
import pytest_asyncio

from api import TrebnicAPI
from database import DatabaseError
from events import AppEvent, event_bus
from models.entities import Task, TimeEntry
from services.timer import TimerService
from ui.timer_controller import TimerController


def task(id=1):
    return Task(f"Timer {id}", 0, 900, None, None, id=id)


class Clock(datetime):
    value = datetime.now() - timedelta(hours=2)

    @classmethod
    def now(cls):
        return cls.value


class Store:
    def __init__(self):
        self.rows = {}
        self.next_id = 1
        self.save_entered = asyncio.Event()
        self.save_release = asyncio.Event()
        self.save_release.set()
        self.finish_entered = asyncio.Event()
        self.finish_release = asyncio.Event()
        self.finish_release.set()
        self.fail_save = False
        self.fail_finish = False
        self.fail_heartbeat = False

    async def save_time_entry(self, entry):
        self.save_entered.set()
        await self.save_release.wait()
        if self.fail_save or (entry.id is not None and self.fail_heartbeat):
            raise DatabaseError("write failed")
        id = entry.id
        if id is None:
            id = self.next_id
            self.next_id += 1
        self.rows[id] = dict(entry.to_dict(), id=id)
        return id

    async def save_entry_with_recompute(self, entry):
        self.finish_entered.set()
        await self.finish_release.wait()
        if self.fail_finish:
            raise DatabaseError("finalize failed")
        self.rows[entry.id] = entry.to_dict()
        total = sum(int((datetime.fromisoformat(r["end_time"]) - datetime.fromisoformat(r["start_time"])).total_seconds())
                    for r in self.rows.values() if r["task_id"] == entry.task_id and r["end_time"])
        return entry.id, {entry.task_id: total}

    async def delete_time_entry(self, id):
        self.finish_entered.set()
        await self.finish_release.wait()
        self.rows.pop(id, None)

    async def delete_entry_with_recompute(self, id):
        await self.delete_time_entry(id)
        return {}

    async def load_orphaned_running(self, keep_id=None):
        return [dict(r) for id, r in self.rows.items() if id != keep_id and not r["end_time"]]


async def settle():
    for _ in range(30):
        await asyncio.sleep(0)


@pytest_asyncio.fixture
async def timer_env(monkeypatch):
    Clock.value = datetime.now() - timedelta(hours=2)
    monkeypatch.setattr("services.timer.datetime", Clock)
    event_bus.clear()
    store, cache, timer = Store(), Mock(), TimerService()
    jobs, events = [], []
    def schedule(fn):
        job = asyncio.create_task(fn())
        jobs.append(job)
        return job
    timer.inject_dependencies(store, cache, schedule)
    subs = [event_bus.subscribe(ev, lambda data, ev=ev: events.append((ev, data)))
            for ev in (AppEvent.TIMER_STARTED, AppEvent.TIMER_STOPPING, AppEvent.TIMER_STOPPED,
                       AppEvent.TIMER_TICK, AppEvent.TIMER_FAILED)]
    yield timer, store, cache, jobs, events
    store.save_release.set()
    store.finish_release.set()
    timer.cleanup()
    await asyncio.wait_for(timer.wait_closed(), 3)
    for job in jobs:
        assert job.done() and not job.cancelled()
        assert job.exception() is None
    for sub in subs:
        sub.unsubscribe()
    event_bus.clear()


async def test_stop_before_initialization(timer_env):
    timer, store, _, _, events = timer_env
    timer.start(task())
    timer.stop()
    await timer.wait_closed()
    assert not store.rows
    assert not timer.running
    assert sum(ev == AppEvent.TIMER_STOPPED for ev, _ in events) == 1


async def test_stop_while_insert_pending(timer_env):
    timer, store, _, _, _ = timer_env
    store.save_release.clear()
    timer.start(task())
    await store.save_entered.wait()
    timer.stop()
    store.save_release.set()
    await timer.wait_closed()
    assert not store.rows


async def test_restart_while_insert_pending_keeps_ids_separate(timer_env):
    timer, store, _, _, _ = timer_env
    store.save_release.clear()
    timer.start(task())
    await store.save_entered.wait()
    old_entry = timer.current_entry
    timer.stop()
    timer.start(task(2))
    new_entry = timer.current_entry
    store.save_release.set()
    await settle()
    assert old_entry.id != new_entry.id
    assert set(store.rows) == {new_entry.id}
    assert store.rows[new_entry.id]["task_id"] == 2


async def test_restart_has_only_one_ticking_loop(timer_env):
    timer, _, _, jobs, events = timer_env
    timer.start(task())
    await settle()
    timer.stop()
    timer.start(task(2))
    Clock.value += timedelta(seconds=1)
    await asyncio.sleep(1.1)
    ticks = [data for ev, data in events if ev == AppEvent.TIMER_TICK]
    assert ticks == [1]
    assert sum(not job.done() for job in jobs) == 1


async def test_delayed_stop_does_not_hide_new_timer(timer_env):
    timer, store, _, _, _ = timer_env
    widget, page, snack = Mock(), Mock(), Mock()
    ctrl = TimerController(page, timer, snack, widget)
    timer.start(task())
    await settle()
    store.finish_release.clear()
    timer.stop()
    await store.finish_entered.wait()
    assert widget.stop.call_count == 1
    timer.start(task(2))
    store.finish_release.set()
    await settle()
    assert timer.running and timer.active_task.id == 2
    assert widget.stop.call_count == 1
    ctrl.cleanup()


@pytest.mark.parametrize("seconds, saved", [(0, False), (0.9, False), (1, False), (20, False), (59, False), (59.9, False), (60, True), (60.9, True), (299.9, True), (300, True), (367, True)])
async def test_stop_threshold_and_exact_saved_duration(timer_env, seconds, saved):
    timer, store, cache, _, events = timer_env
    timer.start(task())
    await settle()
    Clock.value += timedelta(seconds=seconds)
    timer.sync_from_wall_clock()
    assert timer.seconds == int(seconds)
    timer.stop()
    await timer.wait_closed()
    assert bool(store.rows) == saved
    if saved:
        row = next(iter(store.rows.values()))
        duration = (datetime.fromisoformat(row["end_time"]) - datetime.fromisoformat(row["start_time"])).total_seconds()
        assert duration == int(seconds)
        cache.apply_spent.assert_called_with({1: int(seconds)})
        assert (AppEvent.TIMER_STOPPED, {"task": task(), "elapsed": int(seconds)}) in events
    else:
        assert (AppEvent.TIMER_STOPPED, None) in events
        cache.apply_spent.assert_not_called()


async def test_short_session_shows_explanation(timer_env):
    from i18n import t
    timer, _, _, _, _ = timer_env
    snack = Mock()
    controller = TimerController(Mock(), timer, snack, Mock())
    timer.start(task())
    await settle()
    Clock.value += timedelta(seconds=59)
    timer.stop()
    await timer.wait_closed()
    snack.show.assert_called_with(t("timer_discarded"))
    controller.cleanup()


async def test_initial_write_failure_clears_active_state(timer_env):
    timer, store, _, _, events = timer_env
    store.fail_save = True
    timer.start(task())
    await timer.wait_closed()
    assert not timer.running and timer.current_entry is None
    assert any(ev == AppEvent.TIMER_FAILED for ev, _ in events)
    assert not any(ev == AppEvent.TIMER_STOPPED for ev, _ in events)
    store.fail_save = False
    assert timer.start(task(2))


async def test_finalize_failure_is_not_reported_as_discard(timer_env):
    timer, store, _, _, events = timer_env
    timer.start(task())
    await settle()
    Clock.value += timedelta(seconds=360)
    store.fail_finish = True
    timer.stop()
    await timer.wait_closed()
    assert any(ev == AppEvent.TIMER_FAILED for ev, _ in events)
    assert not any(ev == AppEvent.TIMER_STOPPED for ev, _ in events)
    assert next(iter(store.rows.values()))["end_time"] is None


async def test_resume_updates_elapsed_and_heartbeat_without_busy_loop(timer_env):
    timer, store, _, _, events = timer_env
    timer.start(task())
    await settle()
    Clock.value += timedelta(seconds=125)
    timer.sync_from_wall_clock()
    await settle()
    assert timer.seconds == 125
    assert next(iter(store.rows.values()))["heartbeat_at"] == Clock.value.isoformat()
    count = len(events)
    await settle()
    assert len(events) == count


async def test_heartbeat_failure_retries_and_stop_still_saves(timer_env):
    timer, store, _, _, events = timer_env
    timer.start(task())
    await settle()
    store.fail_heartbeat = True
    Clock.value += timedelta(seconds=310)
    timer.sync_from_wall_clock()
    await settle()
    assert timer.running
    store.fail_heartbeat = False
    timer.sync_from_wall_clock()
    await settle()
    assert next(iter(store.rows.values()))["heartbeat_at"] is not None
    timer.stop()
    await timer.wait_closed()
    assert next(iter(store.rows.values()))["end_time"] is not None
    assert not any(ev == AppEvent.TIMER_FAILED for ev, _ in events)


async def test_stop_waits_for_inflight_heartbeat(timer_env):
    timer, store, _, _, _ = timer_env
    timer.start(task())
    await settle()
    store.save_entered.clear()
    store.save_release.clear()
    Clock.value += timedelta(seconds=310)
    timer.sync_from_wall_clock()
    await store.save_entered.wait()
    timer.stop()
    store.save_release.set()
    await timer.wait_closed()
    row = next(iter(store.rows.values()))
    assert row["end_time"] is not None and row["heartbeat_at"] is None


async def test_cleanup_drains_saved_session_and_prevents_restart(timer_env):
    timer, store, _, _, events = timer_env
    timer.start(task())
    await settle()
    Clock.value += timedelta(seconds=360)
    timer.cleanup()
    assert not timer.start(task(2))
    await timer.wait_closed()
    assert next(iter(store.rows.values()))["end_time"] is not None
    assert not any(ev == AppEvent.TIMER_STOPPED for ev, _ in events)


@pytest.mark.parametrize("banked", [0, 1, 20, 59, 60, 299, 360])
async def test_recovery_banks_only_heartbeat_and_reserves_start(timer_env, banked):
    timer, store, cache, _, _ = timer_env
    start = Clock.value - timedelta(hours=1)
    old = TimeEntry(task_id=1, start_time=start, heartbeat_at=start + timedelta(seconds=banked))
    old.id = await store.save_time_entry(old)
    assert timer.recover(old, task())
    assert not timer.start(task(2))
    assert not timer.recover(old, task())
    await settle()
    assert timer.seconds == 0
    assert timer.current_entry.id != old.id
    if banked >= 60:
        assert store.rows[old.id]["end_time"] == (start + timedelta(seconds=banked)).isoformat()
        cache.apply_spent.assert_called_with({1: banked})
    else:
        assert old.id not in store.rows


async def test_stop_during_recovery_does_not_restart(timer_env):
    timer, store, _, _, events = timer_env
    old = TimeEntry(task_id=1, start_time=Clock.value - timedelta(hours=1))
    old.id = await store.save_time_entry(old)
    store.finish_release.clear()
    timer.recover(old, task())
    await store.finish_entered.wait()
    timer.stop()
    store.finish_release.set()
    await timer.wait_closed()
    assert not timer.running and not store.rows
    assert sum(ev == AppEvent.TIMER_STARTED for ev, _ in events) == 1


async def test_orphan_reaping_never_removes_live_session(timer_env):
    timer, store, _, _, _ = timer_env
    timer.start(task())
    await settle()
    await timer.reap_orphaned_entries()
    assert set(store.rows) == {timer.current_entry.id}


async def test_unsaved_task_is_rejected(timer_env):
    timer, _, _, _, _ = timer_env
    with pytest.raises(ValueError):
        timer.start(task(None))
    assert not timer.running


async def test_real_database_tracks_and_recovers_canonical_totals(services, monkeypatch):
    Clock.value = datetime.now() - timedelta(hours=2)
    monkeypatch.setattr("services.timer.datetime", Clock)
    api = TrebnicAPI(services)
    item = await api.add_task("Timer database regression")
    timer = services.timer
    timer.inject_dependencies(services.time_entry, services.task, lambda fn: asyncio.create_task(fn()))
    timer.start(item)
    Clock.value += timedelta(seconds=361.8)
    timer.stop()
    await timer.wait_closed()
    entries = await services.time_entry.load_time_entries_for_task(item.id)
    assert len(entries) == 1 and not entries[0].is_running
    assert item.spent_seconds == 361
    old = TimeEntry(task_id=item.id, start_time=Clock.value - timedelta(seconds=600),
                    heartbeat_at=Clock.value - timedelta(seconds=280))
    old.id = await services.time_entry.save_time_entry(old)
    timer.recover(old, item)
    timer.stop()
    await timer.wait_closed()
    entries = await services.time_entry.load_time_entries_for_task(item.id)
    assert len(entries) == 2 and all(not e.is_running for e in entries)
    assert item.spent_seconds == 681
    timer.cleanup()


@pytest.mark.parametrize("kind", ["task", "project", "recurring"])
async def test_deletion_drains_pending_insert(services, kind):
    api = TrebnicAPI(services)
    item = await api.add_task("Delete timer regression")
    if kind == "project":
        from models.entities import Project
        project = Project("timer-test", "Timer test", "folder", "blue")
        await services.project.save_project(project)
        item.project_id = project.id
        await services.task.persist_task(item)
    if kind == "recurring":
        item.recurrent = True
        await services.task.persist_task(item)
    timer = services.timer
    timer.inject_dependencies(services.time_entry, services.task, lambda fn: asyncio.create_task(fn()))
    timer.start(item)
    if kind == "task":
        await services.task.delete_task(item)
    elif kind == "project":
        await services.project.delete_project(item.project_id)
    else:
        await services.task.delete_all_recurring_tasks(item)
    assert not timer.running
    assert not await services.time_entry.load_time_entries_for_task(item.id)
    assert not timer._jobs
    timer.cleanup()


async def test_threaded_scheduler_and_concurrent_start(timer_env):
    timer, store, cache, _, _ = timer_env
    loop = asyncio.get_running_loop()
    timer.inject_dependencies(store, cache, lambda fn: asyncio.run_coroutine_threadsafe(fn(), loop))
    results = await asyncio.gather(*(asyncio.to_thread(timer.start, task(id)) for id in range(1, 12)))
    assert sum(results) == 1
    Clock.value += timedelta(seconds=360)
    await asyncio.to_thread(timer.cleanup)
    await timer.wait_closed()
    assert len(store.rows) == 1
    assert next(iter(store.rows.values()))["end_time"] is not None


async def test_burst_of_stops_and_starts_has_no_orphans_or_duplicate_entries(timer_env):
    timer, store, cache, _, events = timer_env
    expected = 0
    for index in range(30):
        assert timer.start(task())
        seconds = 301 if index % 3 == 0 else 2
        Clock.value += timedelta(seconds=seconds)
        expected += seconds if seconds >= 60 else 0
        timer.stop()
        timer.stop()
        if index % 2:
            await asyncio.sleep(0)
    await timer.wait_closed()
    assert len(store.rows) == 10
    assert all(row["end_time"] is not None for row in store.rows.values())
    cache.apply_spent.assert_called_with({1: expected})
    assert sum(ev == AppEvent.TIMER_STOPPED for ev, _ in events) == 30
    assert not timer.running and not timer._sessions
