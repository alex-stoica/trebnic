import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from config import MIN_TIMER_SECONDS
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

        # Schedule async initialization + loop
        self._schedule_async(self._initialize_and_run())

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
        except Exception as e:
            logger.error(f"Error in timer loop: {e}")
            self.running = False

    async def _save_heartbeat(self) -> None:
        """Save current state to DB for crash recovery."""
        if not self.current_entry or not self._time_entry_svc:
            return
        try:
            self.current_entry.end_time = datetime.now()
            await self._time_entry_svc.save_time_entry(self.current_entry)
            self.current_entry.end_time = None
            logger.debug(f"Heartbeat saved at {self.seconds}s")
        except Exception as e:
            logger.warning(f"Failed to save heartbeat: {e}")

    def stop(self) -> None:
        """Stop the timer."""
        if not self.running:
            return

        self.running = False
        self._stop_event.set()

        # Capture state before clearing
        task = self.active_task
        elapsed = self.seconds
        should_save = elapsed >= MIN_TIMER_SECONDS
        entry = self.current_entry
        entry_id_to_delete = entry.id if entry and not should_save else None

        # Clear state immediately
        self.active_task = None
        self.seconds = 0
        self.start_time = None
        self.current_entry = None

        # Schedule async finalization
        if self._schedule_async:
            self._schedule_async(
                self._finalize_stop(task, elapsed, should_save, entry, entry_id_to_delete)
            )

    async def _finalize_stop(
        self,
        task: Optional[Task],
        elapsed: int,
        should_save: bool,
        entry: Optional[TimeEntry],
        entry_id_to_delete: Optional[int],
    ) -> None:
        """Finalize timer stop - save or delete entry."""
        if should_save:
            if entry:
                entry.end_time = datetime.now()
                await self._time_entry_svc.save_time_entry(entry)

            if task:
                task.spent_seconds += elapsed
                await self._task_svc.persist_task(task)

            event_bus.emit(AppEvent.TIMER_STOPPED, {"task": task, "elapsed": elapsed})
            event_bus.emit(AppEvent.REFRESH_UI)
        else:
            if entry_id_to_delete:
                await self._time_entry_svc.delete_time_entry(entry_id_to_delete)
            event_bus.emit(AppEvent.TIMER_STOPPED, None)

    def recover(self, entry: TimeEntry, task: Task) -> None:
        """Recover a running timer from app restart."""
        if self.running or self._schedule_async is None:
            return

        elapsed = int((datetime.now() - entry.start_time).total_seconds())

        self.active_task = task
        self.seconds = elapsed
        self.running = True
        self.current_entry = entry
        self.start_time = entry.start_time
        self._stop_event.clear()
        self._last_heartbeat_seconds = elapsed

        self._schedule_async(self._tick_loop())

        event_bus.emit(AppEvent.TIMER_STARTED, task)
        event_bus.emit(AppEvent.TIMER_TICK, elapsed)

    def cleanup(self) -> None:
        """Clean up timer resources."""
        self._stop_event.set()
        self.running = False

    def get_current_entry(self) -> Optional[TimeEntry]:
        """Get the current running time entry."""
        return self.current_entry
