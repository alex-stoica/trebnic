import flet as ft
import asyncio
from typing import Optional

from config import COLORS
from models.entities import Task, TimeEntry
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

    def cleanup(self) -> None:
        """Clean up timer resources."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = None
        self._stop_event = None
