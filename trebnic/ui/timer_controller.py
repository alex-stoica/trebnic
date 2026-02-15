import flet as ft
import logging
from datetime import datetime
from typing import List, Optional

from config import COLORS, MIN_TIMER_SECONDS
from i18n import t
from models.entities import Task, AppState
from services.notification_service import notification_service
from services.timer import TimerService
from ui.formatters.time_formatter import TimeFormatter
from ui.helpers import format_timer_display, SnackService
from ui.components import TimerWidget
from events import event_bus, AppEvent, Subscription


logger = logging.getLogger(__name__)


class TimerController:
    """Thin controller that bridges TimerService events to UI.

    The service owns the timer loop and emits events. This controller
    subscribes to those events and updates the UI accordingly.
    """

    def __init__(
        self,
        page: ft.Page,
        timer_svc: TimerService,
        snack: SnackService,
        timer_widget: TimerWidget,
    ) -> None:
        self.page = page
        self.timer_svc = timer_svc
        self.snack = snack
        self.timer_widget = timer_widget

        self._subscriptions: List[Subscription] = []
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TIMER_TICK, self._on_tick)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TIMER_STARTED, self._on_started)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TIMER_STOPPED, self._on_stopped)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TIMER_SYNC, self._on_sync)
        )

    def start_timer(self, task: Task) -> None:
        """Start the timer for a task."""
        if self.timer_svc.running:
            self.snack.show(t("stop_current_timer_first"), COLORS["danger"])
            return
        self.timer_svc.start(task)
        self.snack.show(t("timer_started_for").replace("{title}", task.title))

    def on_timer_stop(self, e: ft.ControlEvent) -> None:
        """Handle timer stop button click."""
        self.timer_svc.stop()

    def stop_timer(self) -> None:
        """Stop the current timer."""
        self.timer_svc.stop()

    def recover_timer(self, state: AppState) -> None:
        """Recover a running timer from app restart."""
        if state.recovered_timer_entry is None:
            return

        entry = state.recovered_timer_entry
        task = state.get_task_by_id(entry.task_id)

        if task is None:
            # Task was deleted, complete the orphaned entry async
            entry.end_time = datetime.now()

            async def save_orphaned_entry():
                await self.timer_svc._time_entry_svc.save_time_entry(entry)

            self.page.run_task(save_orphaned_entry)
            state.recovered_timer_entry = None
            return

        self.timer_svc.recover(entry, task)
        elapsed_str = format_timer_display(self.timer_svc.seconds)
        self.snack.show(
            t("timer_recovered").replace("{title}", task.title).replace("{time}", elapsed_str)
        )
        state.recovered_timer_entry = None

    def cleanup(self) -> None:
        """Clean up subscriptions and timer resources."""
        for sub in self._subscriptions:
            sub.unsubscribe()
        self._subscriptions.clear()
        self.timer_svc.cleanup()

    def _on_tick(self, seconds: int) -> None:
        """Handle timer tick event - update UI."""
        self.timer_widget.update_time(seconds)
        try:
            self.timer_widget.update()
        except RuntimeError:
            pass  # Widget disposed, service keeps running

    def _on_started(self, task: Task) -> None:
        """Handle timer started event - update UI."""
        self.timer_widget.start(task.title)
        try:
            self.timer_widget.update()
        except RuntimeError:
            pass

    def _on_sync(self, data: None) -> None:
        """Handle timer sync event - recalculate from wall clock."""
        self.timer_svc.sync_from_wall_clock()

    def _on_stopped(self, data: Optional[dict]) -> None:
        """Handle timer stopped event - update UI, show message, and notification."""
        self.timer_widget.stop()
        try:
            self.page.update()
        except RuntimeError:
            pass

        if data is None:
            min_minutes = MIN_TIMER_SECONDS // 60
            self.snack.show(
                t("timer_discarded").replace("{minutes}", str(min_minutes)),
                COLORS["danger"],
            )
        else:
            time_display = format_timer_display(data['elapsed'])
            self.snack.show(
                t("time_added_to_task").replace("{time}", time_display).replace("{title}", data['task'].title),
                COLORS["green"],
            )

            # Show timer completion notification
            task = data.get("task")
            elapsed = data.get("elapsed", 0)
            if task and elapsed > 0:
                async def _show_notification() -> None:
                    time_str = TimeFormatter.seconds_to_display(elapsed)
                    title = t("timer_complete")
                    body = t("tracked_time_on_task").replace("{time}", time_str).replace("{task}", task.title)
                    await notification_service.show_immediate(
                        title=title,
                        body=body,
                        task_id=task.id,
                        payload={"action": "open_stats", "elapsed_seconds": elapsed},
                    )
                self.page.run_task(_show_notification)
