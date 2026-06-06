import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from config import MIN_TIMER_SECONDS
from database import DatabaseError
from events import event_bus, AppEvent
from models.entities import Task, TimeEntry

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30


class TimerService:
    """Active timer service that manages its own tick loop.

    Framework-agnostic: uses injected scheduler for async operations.
    The service owns its lifecycle - start/stop control the tick loop internally.
    """

    def __init__(self) -> None:
        # Dependencies (injected to avoid coupling to Flet)
        self._time_entry_svc = None
        self._task_svc = None
        self._schedule_async: Optional[Callable[..., asyncio.Task]] = None

        # State
        self.active_task: Optional[Task] = None
        self.current_entry: Optional[TimeEntry] = None
        self.seconds: int = 0
        self.running: bool = False
        self.start_time: Optional[datetime] = None

        # Async control
        self._stop_event: asyncio.Event = asyncio.Event()
        self._last_heartbeat_seconds: int = 0

    def inject_dependencies(
        self,
        time_entry_service,
        task_service,
        async_scheduler: Callable[..., asyncio.Task],
    ) -> None:
        """Inject dependencies after construction.

        Args:
            time_entry_service: Service for persisting time entries
            task_service: Service for persisting tasks
            async_scheduler: Function to schedule async work (e.g., page.run_task)
        """
        self._time_entry_svc = time_entry_service
        self._task_svc = task_service
        self._schedule_async = async_scheduler

    def start(self, task: Task) -> None:
        """Start the timer for a task."""
        if self.running:
            return

        if self._schedule_async is None:
            raise RuntimeError("TimerService dependencies not injected")

        self.active_task = task
        self.seconds = 0
        self.running = True
        self.start_time = datetime.now()
        self._stop_event.clear()
        self._last_heartbeat_seconds = 0

        if task.id is not None:
            self.current_entry = TimeEntry(task_id=task.id, start_time=self.start_time)

        # Schedule async initialization + loop (flet 0.80.x requires function, not coroutine object)
        self._schedule_async(self._initialize_and_run)

        event_bus.emit(AppEvent.TIMER_STARTED, task)

    async def _initialize_and_run(self) -> None:
        """Save initial entry then start tick loop."""
        if self.current_entry and self._time_entry_svc:
            self.current_entry.id = await self._time_entry_svc.save_time_entry(self.current_entry)
        await self._tick_loop()

    async def _tick_loop(self) -> None:
        """Main tick loop - runs independently of UI."""
        task_title = self.active_task.title if self.active_task else "unknown"
        logger.info(f"Timer loop started for '{task_title}'")

        try:
            while self.running and not self._stop_event.is_set():
                await asyncio.sleep(1.0)

                if self._stop_event.is_set() or not self.running:
                    break

                self.seconds += 1

                # Emit tick event for UI subscribers
                event_bus.emit(AppEvent.TIMER_TICK, self.seconds)

                # Heartbeat for crash recovery
                if self.seconds - self._last_heartbeat_seconds >= HEARTBEAT_INTERVAL_SECONDS:
                    await self._save_heartbeat()
                    self._last_heartbeat_seconds = self.seconds

        except asyncio.CancelledError:
            logger.info("Timer loop cancelled")
        except (DatabaseError, RuntimeError, OSError) as e:
            logger.error(f"Error in timer loop: {e}")
            self.running = False

    async def _save_heartbeat(self) -> None:
        """Persist liveness for crash recovery.

        Writes heartbeat_at and leaves end_time NULL, so the entry stays "running":
        recovery can still find it (end_time IS NULL) and it is excluded from the
        canonical spent_seconds sum until the timer is actually stopped.
        """
        if not self.current_entry or not self._time_entry_svc:
            return
        try:
            self.current_entry.heartbeat_at = datetime.now()
            await self._time_entry_svc.save_time_entry(self.current_entry)
            logger.debug(f"Heartbeat saved at {self.seconds}s")
        except (DatabaseError, OSError) as e:
            logger.warning(f"Failed to save heartbeat: {e}")

    def stop(self) -> None:
        """Stop the timer."""
        if not self.running:
            return

        self.running = False
        self._stop_event.set()

        # Capture state before clearing. End the entry at wall-clock now; its
        # duration (and the task's spent) is derived canonically from start->end.
        task = self.active_task
        entry = self.current_entry
        end = datetime.now()
        elapsed = int((end - self.start_time).total_seconds()) if self.start_time else self.seconds
        should_save = elapsed >= MIN_TIMER_SECONDS

        # Clear state immediately
        self.active_task = None
        self.seconds = 0
        self.start_time = None
        self.current_entry = None

        # Schedule async finalization (wrap in closure - run_task requires function, not coroutine object)
        if self._schedule_async:
            async def _do_finalize():
                await self._finalize_stop(task, entry, end, elapsed, should_save)
            self._schedule_async(_do_finalize)

    async def _finalize_stop(
        self,
        task: Optional[Task],
        entry: Optional[TimeEntry],
        end: datetime,
        elapsed: int,
        should_save: bool,
    ) -> None:
        """Finalize timer stop - close the entry (canonical recompute) or discard it."""
        try:
            if should_save and entry:
                entry.end_time = end
                entry.heartbeat_at = None
                _, affected = await self._time_entry_svc.save_entry_with_recompute(entry)
                if self._task_svc is not None:
                    self._task_svc.apply_spent(affected)
                event_bus.emit(AppEvent.TIMER_STOPPED, {"task": task, "elapsed": elapsed})
                event_bus.emit(AppEvent.REFRESH_UI)
            else:
                if entry and entry.id is not None:
                    await self._time_entry_svc.delete_time_entry(entry.id)
                event_bus.emit(AppEvent.TIMER_STOPPED, None)
        except (DatabaseError, OSError) as e:
            logger.error(f"Error finalizing timer stop: {e}")
            # Always emit stop event so UI cleans up
            event_bus.emit(AppEvent.TIMER_STOPPED, None)

    @staticmethod
    def banked_recovery_seconds(entry: TimeEntry) -> int:
        """Conservative elapsed for a recovered entry: heartbeat_at - start_time.

        Never counts an offline gap (phone off/asleep), since we only trust time we
        actually observed via the ~30s heartbeat.
        """
        bank_end = entry.heartbeat_at or entry.start_time
        return max(0, int((bank_end - entry.start_time).total_seconds()))

    async def reap_orphaned_entries(self, keep_id: Optional[int] = None) -> None:
        """Finalize stale running entries left by repeated crashes (excluding keep_id).

        Each is banked at its last heartbeat if that exceeds the minimum, else
        discarded — same policy as a normal stop — so no phantom 'running' rows
        linger in a task's timeline. keep_id is the entry being actively recovered.
        """
        if self._time_entry_svc is None:
            return
        rows = await self._time_entry_svc.load_orphaned_running(keep_id)
        affected: dict = {}
        for r in rows:
            try:
                start = datetime.fromisoformat(r["start_time"])
                hb = r.get("heartbeat_at")
                bank_end = datetime.fromisoformat(hb) if hb else start
            except (ValueError, TypeError):
                # A malformed timestamp on one row must not abort cleanup of the rest.
                continue
            if int((bank_end - start).total_seconds()) >= MIN_TIMER_SECONDS:
                entry = TimeEntry(id=r["id"], task_id=r["task_id"], start_time=start, end_time=bank_end)
                _, aff = await self._time_entry_svc.save_entry_with_recompute(entry)
            else:
                aff = await self._time_entry_svc.delete_entry_with_recompute(r["id"])
            affected.update(aff)
        if affected and self._task_svc is not None:
            self._task_svc.apply_spent(affected)

    def recover(self, entry: TimeEntry, task: Task) -> None:
        """Recover a running timer from app restart.

        The pre-crash portion is banked conservatively at the last heartbeat (so an
        offline gap is never counted), then a fresh running entry resumes from now.
        This keeps spent canonical: the gap simply becomes a break between entries.
        """
        if self.running or self._schedule_async is None:
            return

        async def _do_recover():
            await self._recover_async(entry, task)
        self._schedule_async(_do_recover)

    async def _recover_async(self, entry: TimeEntry, task: Task) -> None:
        # Bank the observed pre-crash portion (or discard if below threshold).
        banked = self.banked_recovery_seconds(entry)
        if entry.id is not None:
            if banked >= MIN_TIMER_SECONDS:
                entry.end_time = entry.heartbeat_at or entry.start_time
                entry.heartbeat_at = None
                _, affected = await self._time_entry_svc.save_entry_with_recompute(entry)
                if self._task_svc is not None:
                    self._task_svc.apply_spent(affected)
            else:
                await self._time_entry_svc.delete_time_entry(entry.id)

        # Resume as a fresh running entry from now.
        self.active_task = task
        self.start_time = datetime.now()
        self.seconds = 0
        self.running = True
        self._stop_event.clear()
        self._last_heartbeat_seconds = 0
        self.current_entry = TimeEntry(task_id=task.id, start_time=self.start_time)
        if task.id is not None:
            self.current_entry.id = await self._time_entry_svc.save_time_entry(self.current_entry)

        event_bus.emit(AppEvent.TIMER_STARTED, task)
        event_bus.emit(AppEvent.TIMER_TICK, 0)
        await self._tick_loop()

    def sync_from_wall_clock(self) -> None:
        """Recalculate elapsed seconds from wall clock after app resume."""
        if not self.running or not self.start_time:
            return
        new_seconds = int((datetime.now() - self.start_time).total_seconds())
        if new_seconds > self.seconds:
            logger.info(f"Timer sync: {self.seconds}s -> {new_seconds}s (recovered {new_seconds - self.seconds}s)")
            self.seconds = new_seconds
            event_bus.emit(AppEvent.TIMER_TICK, self.seconds)

    def cleanup(self) -> None:
        """Clean up timer resources."""
        self._stop_event.set()
        self.running = False

    def get_current_entry(self) -> Optional[TimeEntry]:
        """Get the current running time entry."""
        return self.current_entry
