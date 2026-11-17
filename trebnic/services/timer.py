import asyncio
import logging
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock
from typing import Callable, Optional

from config import MIN_TIMER_SECONDS
from database import DatabaseError
from events import event_bus, AppEvent
from models.entities import Task, TimeEntry

logger = logging.getLogger(__name__)
HEARTBEAT_INTERVAL_SECONDS = 30


@dataclass(eq=False)
class _Session:
    task: Task
    entry: TimeEntry
    recovered: Optional[TimeEntry] = None
    end: Optional[datetime] = None
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    loop: Optional[asyncio.AbstractEventLoop] = None
    heartbeat_seconds: int = 0
    job: object = None


class TimerService:
    """Own timer sessions and serialize their persistence."""

    def __init__(self) -> None:
        self._time_entry_svc = None
        self._task_svc = None
        self._schedule_async = None
        self.active_task: Optional[Task] = None
        self.current_entry: Optional[TimeEntry] = None
        self.seconds = 0
        self.running = False
        self.start_time: Optional[datetime] = None
        self._session: Optional[_Session] = None
        self._sessions: list[_Session] = []
        self._jobs = set()
        self._state_lock = RLock()
        self._storage_lock = asyncio.Lock()
        self._closed = False

    def inject_dependencies(self, time_entry_service, task_service,
                            async_scheduler: Callable) -> None:
        """Set storage, task cache, and async scheduler."""
        self._time_entry_svc = time_entry_service
        self._task_svc = task_service
        self._schedule_async = async_scheduler

    def _schedule(self, fn):
        job = self._schedule_async(fn)
        self._jobs.add(job)
        def done(future):
            with self._state_lock:
                self._jobs.discard(future)
        job.add_done_callback(done)
        return job

    def start(self, task: Task, *, recovered: Optional[TimeEntry] = None) -> bool:
        """Reserve a session before scheduling its writes."""
        with self._state_lock:
            if self.running or self._closed:
                return False
            if self._schedule_async is None or self._time_entry_svc is None:
                raise RuntimeError("TimerService dependencies not injected")
            if task.id is None:
                raise ValueError("Save the task before starting its timer")
            entry = TimeEntry(task_id=task.id, start_time=datetime.now())
            session = _Session(task, entry, recovered)
            self._session = session
            self._sessions.append(session)
            self.active_task, self.current_entry = task, entry
            self.start_time, self.seconds, self.running = entry.start_time, 0, True
            async def run():
                await self._run(session)
            try:
                session.job = self._schedule(run)
            except Exception:
                self._detach(session)
                self._sessions.remove(session)
                raise
            event_bus.emit(AppEvent.TIMER_STARTED, task)
            return True

    def _detach(self, session: _Session) -> None:
        if self._session is session:
            self._session = None
            self.active_task = self.current_entry = self.start_time = None
            self.seconds, self.running = 0, False

    def _elapsed(self, session: _Session) -> int:
        end = session.end or datetime.now()
        return max(0, int((end - session.entry.start_time).total_seconds()))

    async def _run(self, session: _Session) -> None:
        session.loop = asyncio.get_running_loop()
        try:
            async with self._storage_lock:
                if session.recovered is not None:
                    await self._reap_orphaned_entries(session.recovered.id)
                    await self._bank_entry(session.recovered)
                session.entry.id = await self._time_entry_svc.save_time_entry(session.entry)
            while session.end is None:
                try:
                    await asyncio.wait_for(session.wake.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
                session.wake.clear()
                with self._state_lock:
                    if session.end is not None or self._session is not session:
                        break
                    self.seconds = self._elapsed(session)
                    event_bus.emit(AppEvent.TIMER_TICK, self.seconds)
                    heartbeat = self.seconds - session.heartbeat_seconds >= HEARTBEAT_INTERVAL_SECONDS
                if heartbeat:
                    await self._save_heartbeat(session)
            async with self._storage_lock:
                await self._finalize_stop(session)
        except asyncio.CancelledError:
            with self._state_lock:
                self._detach(session)
            raise
        except (DatabaseError, OSError, RuntimeError, ValueError) as exc:
            logger.exception("Timer persistence failed")
            with self._state_lock:
                self._detach(session)
                if not self._closed:
                    event_bus.emit(AppEvent.TIMER_FAILED, str(exc))
        finally:
            with self._state_lock:
                self._sessions.remove(session)

    async def _save_heartbeat(self, session: _Session) -> None:
        async with self._storage_lock:
            if session.end is not None:
                return
            try:
                session.entry.heartbeat_at = datetime.now()
                await self._time_entry_svc.save_time_entry(session.entry)
                session.heartbeat_seconds = self._elapsed(session)
            except (DatabaseError, OSError):
                logger.warning("Timer heartbeat failed; will retry", exc_info=True)

    def stop(self) -> None:
        """Stop immediately; the session finishes its pending writes."""
        with self._state_lock:
            session = self._session
            if session is None:
                return
            session.end = session.entry.start_time + timedelta(seconds=self._elapsed(session))
            self._detach(session)
            if session.loop is not None:
                session.loop.call_soon_threadsafe(session.wake.set)
            event_bus.emit(AppEvent.TIMER_STOPPING)

    async def _finalize_stop(self, session: _Session) -> None:
        entry = session.entry
        elapsed = self._elapsed(session)
        data = None
        if elapsed >= MIN_TIMER_SECONDS:
            entry.end_time, entry.heartbeat_at = session.end, None
            _, affected = await self._time_entry_svc.save_entry_with_recompute(entry)
            self._apply_spent(affected)
            data = {"task": session.task, "elapsed": elapsed}
        elif entry.id is not None:
            await self._time_entry_svc.delete_time_entry(entry.id)
        with self._state_lock:
            if not self._closed:
                event_bus.emit(AppEvent.TIMER_STOPPED, data)
                event_bus.emit(AppEvent.REFRESH_UI)

    def _apply_spent(self, affected) -> None:
        if self._task_svc is not None:
            self._task_svc.apply_spent(affected)

    @staticmethod
    def banked_recovery_seconds(entry: TimeEntry) -> int:
        """Count only time observed before the last heartbeat."""
        return max(0, int(((entry.heartbeat_at or entry.start_time) - entry.start_time).total_seconds()))

    async def _bank_entry(self, entry: TimeEntry) -> None:
        if entry.id is None:
            return
        banked = self.banked_recovery_seconds(entry)
        if banked >= MIN_TIMER_SECONDS:
            entry.end_time = entry.start_time + timedelta(seconds=banked)
            entry.heartbeat_at = None
            _, affected = await self._time_entry_svc.save_entry_with_recompute(entry)
        else:
            affected = await self._time_entry_svc.delete_entry_with_recompute(entry.id)
        self._apply_spent(affected)

    async def _reap_orphaned_entries(self, keep_id=None) -> None:
        rows = await self._time_entry_svc.load_orphaned_running(keep_id)
        for row in rows:
            with self._state_lock:
                owned_ids = {s.entry.id for s in self._sessions}
                owned_ids.update(s.recovered.id for s in self._sessions if s.recovered)
            if row["id"] in owned_ids:
                continue
            try:
                entry = TimeEntry.from_dict(row)
                await self._bank_entry(entry)
            except (ValueError, TypeError):
                logger.warning("Skipping malformed timer entry %s", row["id"])

    async def reap_orphaned_entries(self, keep_id=None) -> None:
        """Bank abandoned rows without touching live sessions."""
        async with self._storage_lock:
            await self._reap_orphaned_entries(keep_id)

    def recover(self, entry: TimeEntry, task: Task) -> bool:
        """Bank pre-crash time and reserve a fresh session."""
        return self.start(task, recovered=entry)

    def sync_from_wall_clock(self) -> None:
        """Refresh elapsed time after resume."""
        with self._state_lock:
            if self._session is not None:
                self.seconds = self._elapsed(self._session)
                event_bus.emit(AppEvent.TIMER_TICK, self.seconds)
                if self._session.loop is not None:
                    self._session.loop.call_soon_threadsafe(self._session.wake.set)

    def cleanup(self) -> None:
        """Stop accepting timers and finish the active session."""
        with self._state_lock:
            self._closed = True
            self.stop()

    async def wait_closed(self) -> None:
        """Drain writes before closing storage."""
        with self._state_lock:
            jobs = list(self._jobs)
        await asyncio.gather(*(asyncio.wrap_future(j) if isinstance(j, Future) else j
                               for j in jobs))

    async def finish_matching(self, predicate) -> None:
        """Drain matching sessions before deleting their tasks."""
        with self._state_lock:
            sessions = [s for s in self._sessions if predicate(s.task)]
            if self._session in sessions:
                self.stop()
            jobs = [s.job for s in sessions]
        await asyncio.gather(*(asyncio.wrap_future(j) if isinstance(j, Future) else j
                               for j in jobs))

    def get_current_entry(self) -> Optional[TimeEntry]:
        """Return the active entry."""
        return self.current_entry
