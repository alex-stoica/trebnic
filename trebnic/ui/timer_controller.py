import flet as ft
import asyncio
import logging
from datetime import datetime
from typing import Optional

from config import COLORS
from models.entities import Task, TimeEntry, AppState
from services.timer import TimerService
from services.logic import TaskService
from ui.helpers import format_timer_display, SnackService
from ui.components import TimerWidget
from events import event_bus, AppEvent


logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30


class TimerController:
    """Controller for timer-related operations, extracted from TrebnicApp."""

    def __init__(
        self,
        page: ft.Page,
        timer_svc: TimerService,
        service: TaskService,
        snack: SnackService,
        timer_widget: TimerWidget,
    ) -> None:
        self.page = page
        self.timer_svc = timer_svc
        self.service = service
        self.snack = snack
        self.timer_widget = timer_widget
        self._timer_task: Optional[asyncio.Task] = None
        self._stop_event: asyncio.Event = asyncio.Event()  # Proper async synchronization
        self._last_heartbeat_seconds: int = 0

    def _reset_stop_flag(self) -> None:
        """Reset the stop event for a new timer session."""
        self._stop_event.clear()

    def _signal_stop(self) -> None:
        """Signal the timer loop to stop (async-safe)."""
        self._stop_event.set()

    def _save_time_entry_sync(self, entry: TimeEntry) -> int:
        """Save a time entry synchronously (for TimerService callback)."""
        return self.service.run_sync(self.service.save_time_entry(entry))

    def _persist_task_sync(self, task: Task) -> None:
        """Persist a task synchronously (for TimerService callback)."""
        self.service.run_sync(self.service.persist_task(task))

    async def _save_heartbeat_async(self) -> None:
        """Save current timer state to DB for crash recovery.

        Saves a checkpoint of the time entry with current end_time. If the app
        crashes, only time since the last heartbeat is lost. The entry is
        considered "complete" in DB but continues in memory.

        Note: Task spent_seconds is NOT updated here to avoid double-counting
        when stop() adds the full elapsed time.

        This method is async to avoid blocking the UI tick loop.
        """
        if not self.timer_svc.running or self.timer_svc.current_entry is None:
            return

        try:
            entry = self.timer_svc.current_entry
            entry.end_time = datetime.now()
            await self.service.save_time_entry(entry)
            # Clear end_time in memory so timer continues as "running"
            entry.end_time = None
            self._last_heartbeat_seconds = self.timer_svc.seconds
            logger.debug(f"Heartbeat saved at {self.timer_svc.seconds}s")
        except Exception as e:
            # Log heartbeat failures instead of silently swallowing
            logger.warning(f"Failed to save timer heartbeat: {e}")

    def _create_tick_loop(self):
        """Create the async tick loop coroutine for timer updates.

        Includes heartbeat saves every HEARTBEAT_INTERVAL_SECONDS to minimize
        data loss on unexpected app termination.
        Uses asyncio.Event for proper async-safe stop signaling.

        Performance optimization: Updates only the TimerWidget control instead
        of calling page.update() which would refresh the entire page layout.
        This significantly reduces UI stuttering in complex layouts.
        """
        async def tick_loop():
            try:
                while self.timer_svc.running and not self._stop_event.is_set():
                    await asyncio.sleep(1.0)

                    if self._stop_event.is_set():
                        break

                    if self.timer_svc.running:
                        self.timer_svc.tick()
                        self.timer_widget.update_time(self.timer_svc.seconds)

                        # Heartbeat: save to DB periodically for crash recovery
                        if self.timer_svc.seconds - self._last_heartbeat_seconds >= HEARTBEAT_INTERVAL_SECONDS:
                            await self._save_heartbeat_async()

                        try:
                            # Only update the timer widget, not the entire page
                            # This prevents UI stuttering in complex layouts
                            self.timer_widget.update()
                        except Exception:
                            break
            except asyncio.CancelledError:
                pass

        return tick_loop

    def start_timer(self, task: Task) -> None:
        """Start the timer for a task."""
        if self.timer_svc.running:
            self.snack.show("Stop current timer first", COLORS["danger"])
            return

        self.timer_svc.start(task, self._persist_task_sync, self._save_time_entry_sync)
        self.timer_widget.start(task.title)
        event_bus.emit(AppEvent.TIMER_STARTED, task)

        # Reset for new timer session
        self._last_heartbeat_seconds = 0
        self._reset_stop_flag()

        # Use page.run_task to run on Flet's event loop
        self._timer_task = self.page.run_task(self._create_tick_loop())
        self.snack.show(f"Timer started for '{task.title}'")

    def on_timer_stop(self, e: ft.ControlEvent) -> None:
        """Handle timer stop button click."""
        self.stop_timer()

    def stop_timer(self) -> None:
        """Stop the current timer."""
        if not self.timer_svc.running:
            return

        # Signal the async loop to stop (thread-safe)
        self._signal_stop()

        # Cancel the timer task if it exists
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = None

        task, elapsed = self.timer_svc.stop()
        if task and elapsed > 0:
            self.snack.show(
                f"Added {format_timer_display(elapsed)} to '{task.title}'"
            )
            event_bus.emit(AppEvent.REFRESH_UI)
            event_bus.emit(AppEvent.TIMER_STOPPED, {"task": task, "elapsed": elapsed})

        self.timer_widget.stop()
        self.page.update()

    def recover_timer(self, state: AppState) -> None:
        """Recover a running timer from app restart.

        Checks if there's a recovered timer entry in the state and resumes it.
        """
        if state.recovered_timer_entry is None:
            return

        entry = state.recovered_timer_entry
        task = state.get_task_by_id(entry.task_id)

        if task is None:
            # Task was deleted, complete the orphaned entry
            entry.end_time = datetime.now()
            self._save_time_entry_sync(entry)
            state.recovered_timer_entry = None
            return

        # Calculate elapsed seconds since the timer started
        elapsed = int((datetime.now() - entry.start_time).total_seconds())

        # Resume the timer with the existing entry
        self.timer_svc.active_task = task
        self.timer_svc.seconds = elapsed
        self.timer_svc.running = True
        self.timer_svc._persist_fn = self._persist_task_sync
        self.timer_svc._save_entry_fn = self._save_time_entry_sync
        self.timer_svc.current_entry = entry
        self.timer_svc.start_time = entry.start_time

        # Update widget
        self.timer_widget.start(task.title)
        self.timer_widget.update_time(elapsed)

        # Set heartbeat tracking to current elapsed time for recovered timer
        self._last_heartbeat_seconds = elapsed

        # Reset stop flag for timer session
        self._reset_stop_flag()

        self._timer_task = self.page.run_task(self._create_tick_loop())
        self.snack.show(f"Timer recovered for '{task.title}' ({format_timer_display(elapsed)} elapsed)")

        # Clear the recovered entry from state
        state.recovered_timer_entry = None

    def cleanup(self) -> None:
        """Clean up timer resources and save running entry to prevent data loss."""
        # Signal the async loop to stop first (thread-safe)
        self._signal_stop()

        # Cancel the timer task
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

        # Save running time entry before cleanup to prevent data loss
        if self.timer_svc.running and self.timer_svc.current_entry is not None:
            # Complete the entry with current time
            self.timer_svc.current_entry.end_time = datetime.now()
            try:
                self._save_time_entry_sync(self.timer_svc.current_entry)
                # Also update task's spent time
                if self.timer_svc.active_task and self.timer_svc.seconds > 0:
                    self.timer_svc.active_task.spent_seconds += self.timer_svc.seconds
                    self._persist_task_sync(self.timer_svc.active_task)
            except Exception:
                pass  # Best effort save on cleanup

        # Reset timer service state
        self.timer_svc.running = False
        self.timer_svc.active_task = None
        self.timer_svc.current_entry = None
        self.timer_svc.seconds = 0

        self._timer_task = None
        self._stop_event.clear()
        self._last_heartbeat_seconds = 0
