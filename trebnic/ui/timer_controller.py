import flet as ft
import asyncio
from datetime import datetime
from typing import Optional

from config import COLORS
from models.entities import Task, TimeEntry, AppState
from services.timer import TimerService
from services.logic import TaskService
from ui.helpers import format_timer_display, SnackService
from ui.components import TimerWidget
from events import event_bus, AppEvent


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
        self._stop_event: Optional[asyncio.Event] = None

    def _get_stop_event(self) -> asyncio.Event:
        """Get or create the stop event (lazy initialization for correct event loop)."""
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        return self._stop_event

    def _save_time_entry(self, entry: TimeEntry) -> int:
        """Save a time entry to the database."""
        return self.service.save_time_entry(entry)

    def start_timer(self, task: Task) -> None:
        """Start the timer for a task."""
        if self.timer_svc.running:
            self.snack.show("Stop current timer first", COLORS["danger"])
            return

        self.timer_svc.start(task, self.service.persist_task, self._save_time_entry)
        self.timer_widget.start(task.title)
        event_bus.emit(AppEvent.TIMER_STARTED, task)

        # Get/create stop event and reset for new timer session
        stop_event = self._get_stop_event()
        stop_event.clear()

        # Schedule async timer tick on Flet's event loop
        async def tick_loop():
            try:
                while self.timer_svc.running:
                    # Wait for 1 second or until stopped
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(),
                            timeout=1.0
                        )
                        # If we get here, stop was requested
                        break
                    except asyncio.TimeoutError:
                        # Normal timeout - do a tick
                        pass

                    if self.timer_svc.running:
                        self.timer_svc.tick()
                        self.timer_widget.update_time(self.timer_svc.seconds)
                        # Safe to call update() from async task on Flet's loop
                        try:
                            self.page.update()
                        except Exception:
                            break
            except asyncio.CancelledError:
                pass

        # Use page.run_task to run on Flet's event loop
        self._timer_task = self.page.run_task(tick_loop)
        self.snack.show(f"Timer started for '{task.title}'")

    def on_timer_stop(self, e: ft.ControlEvent) -> None:
        """Handle timer stop button click."""
        self.stop_timer()

    def stop_timer(self) -> None:
        """Stop the current timer."""
        if not self.timer_svc.running:
            return

        # Signal the async loop to stop
        if self._stop_event is not None:
            self._stop_event.set()

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
            self.service.save_time_entry(entry)
            state.recovered_timer_entry = None
            return

        # Calculate elapsed seconds since the timer started
        elapsed = int((datetime.now() - entry.start_time).total_seconds())

        # Resume the timer with the existing entry
        self.timer_svc.active_task = task
        self.timer_svc.seconds = elapsed
        self.timer_svc.running = True
        self.timer_svc._persist_fn = self.service.persist_task
        self.timer_svc._save_entry_fn = self._save_time_entry
        self.timer_svc.current_entry = entry
        self.timer_svc.start_time = entry.start_time

        # Update widget
        self.timer_widget.start(task.title)
        self.timer_widget.update_time(elapsed)

        # Get/create stop event and reset for timer session
        stop_event = self._get_stop_event()
        stop_event.clear()

        # Schedule async timer tick on Flet's event loop
        async def tick_loop():
            try:
                while self.timer_svc.running:
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(),
                            timeout=1.0
                        )
                        break
                    except asyncio.TimeoutError:
                        pass

                    if self.timer_svc.running:
                        self.timer_svc.tick()
                        self.timer_widget.update_time(self.timer_svc.seconds)
                        try:
                            self.page.update()
                        except Exception:
                            break
            except asyncio.CancelledError:
                pass

        self._timer_task = self.page.run_task(tick_loop)
        self.snack.show(f"Timer recovered for '{task.title}' ({format_timer_display(elapsed)} elapsed)")

        # Clear the recovered entry from state
        state.recovered_timer_entry = None

    def cleanup(self) -> None:
        """Clean up timer resources and save running entry to prevent data loss."""
        # Signal the async loop to stop first
        if self._stop_event is not None:
            self._stop_event.set()

        # Cancel the timer task
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

        # Save running time entry before cleanup to prevent data loss
        if self.timer_svc.running and self.timer_svc.current_entry is not None:
            # Complete the entry with current time
            self.timer_svc.current_entry.end_time = datetime.now()
            try:
                self.service.save_time_entry(self.timer_svc.current_entry)
                # Also update task's spent time
                if self.timer_svc.active_task and self.timer_svc.seconds > 0:
                    self.timer_svc.active_task.spent_seconds += self.timer_svc.seconds
                    self.service.persist_task(self.timer_svc.active_task)
            except Exception:
                pass  # Best effort save on cleanup

        # Reset timer service state
        self.timer_svc.running = False
        self.timer_svc.active_task = None
        self.timer_svc.current_entry = None
        self.timer_svc.seconds = 0

        self._timer_task = None
        self._stop_event = None
