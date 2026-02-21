"""Task action handler - handles task-related events from the EventBus.

This handler owns all task-related event handling, moving the business logic
out of app.py and UIController. The flow becomes:
    TaskTile -> EventBus -> TaskActionHandler -> TaskService
"""
import flet as ft
import asyncio
import logging
from typing import List, Callable
from datetime import date as date_type

from config import COLORS, ANIMATION_DELAY, NavItem
from database import DatabaseError
from events import event_bus, AppEvent, Subscription
from models.entities import Task, AppState
from services.logic import TaskService
from services.time_entry_service import TimeEntryService
from ui.helpers import SnackService
from ui.dialogs import TaskDialogs
from ui.timer_controller import TimerController

logger = logging.getLogger(__name__)


class TaskActionHandler:
    """Handles task action events emitted by UI components.

    Centralizes task action handling that was previously scattered across
    app.py and UIController. Subscribes to TASK_*_REQUESTED events and
    dispatches to appropriate services/dialogs.
    """

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        service: TaskService,
        time_entry_service: TimeEntryService,
        task_dialogs: TaskDialogs,
        timer_ctrl: TimerController,
        snack: SnackService,
        refresh_ui: Callable[[], None],
    ) -> None:
        self._page = page
        self._state = state
        self._service = service
        self._time_entry_svc = time_entry_service
        self._task_dialogs = task_dialogs
        self._timer_ctrl = timer_ctrl
        self._snack = snack
        self._refresh_ui = refresh_ui
        self._subscriptions: List[Subscription] = []
        self._subscribe()

    def _subscribe(self) -> None:
        """Subscribe to task action events."""
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_COMPLETE_REQUESTED, self._on_complete)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_UNCOMPLETE_REQUESTED, self._on_uncomplete)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_DELETE_REQUESTED, self._on_delete)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_DUPLICATE_REQUESTED, self._on_duplicate)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_RENAME_REQUESTED, self._on_rename)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_ASSIGN_PROJECT_REQUESTED, self._on_assign_project)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_DATE_PICKER_REQUESTED, self._on_date_picker)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_START_TIMER_REQUESTED, self._on_start_timer)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_POSTPONE_REQUESTED, self._on_postpone)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_RECURRENCE_REQUESTED, self._on_recurrence)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_STATS_REQUESTED, self._on_stats)
        )
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TASK_NOTES_REQUESTED, self._on_notes)
        )

    def cleanup(self) -> None:
        """Unsubscribe from all events."""
        for subscription in self._subscriptions:
            subscription.unsubscribe()
        self._subscriptions.clear()

    # --- Event handlers ---

    def _on_complete(self, task: Task) -> None:
        """Handle task completion request.

        Shows duration dialog if no time entries exist, otherwise completes directly.
        """
        async def _complete() -> None:
            has_time_entries = False
            if task.id:
                entries = await self._time_entry_svc.load_time_entries_for_task(task.id)
                has_time_entries = len(entries) > 0

            if not has_time_entries and task.spent_seconds == 0:
                self._task_dialogs.duration_completion(task, self._do_complete)
            else:
                await self._do_complete_async(task)

        self._page.run_task(_complete)

    async def _do_complete_async(self, task: Task) -> None:
        """Actually complete the task after any duration entry."""
        new_task = await self._service.complete_task(task)
        event_bus.emit(AppEvent.TASK_COMPLETED, task)
        if new_task:
            self._snack.show(f"Next occurrence scheduled for {new_task.due_date.strftime('%b %d')}")
            event_bus.emit(AppEvent.TASK_CREATED, new_task)
        self._refresh_ui()

    def _do_complete(self, task: Task) -> None:
        """Sync wrapper for _do_complete_async - used by duration dialog callback."""
        async def _coro() -> None:
            await self._do_complete_async(task)
        self._page.run_task(_coro)

    def _on_uncomplete(self, task: Task) -> None:
        """Handle task uncomplete request."""
        async def _uncomplete() -> None:
            if await self._service.uncomplete_task(task):
                event_bus.emit(AppEvent.TASK_UNCOMPLETED, task)
                self._refresh_ui()

        self._page.run_task(_uncomplete)

    def _on_delete(self, task: Task) -> None:
        """Handle task delete request.

        For recurring tasks, shows a dialog to choose between deleting
        just this occurrence or all recurring instances.
        """
        if task.recurrent:
            self._task_dialogs.delete_recurrence(
                task,
                on_delete_this=self._do_delete_single_task,
                on_delete_all=self._do_delete_all_recurring,
            )
        else:
            self._do_delete_single_task(task)

    def _do_delete_single_task(self, task: Task) -> None:
        """Delete a single task instance."""
        async def _delete() -> None:
            title = task.title
            try:
                await self._service.delete_task(task)
            except DatabaseError as e:
                self._snack.show(f"Failed to delete task: {e}", COLORS["danger"])
                return

            await asyncio.sleep(ANIMATION_DELAY)
            self._snack.show(f"'{title}' deleted", COLORS["danger"], update=False)
            self._refresh_ui()
            event_bus.emit(AppEvent.TASK_DELETED, task)
            self._page.update()

        self._page.run_task(_delete)

    def _do_delete_all_recurring(self, task: Task) -> None:
        """Delete all recurring instances of a task."""
        async def _delete() -> None:
            title = task.title
            try:
                count = await self._service.delete_all_recurring_tasks(task)
            except DatabaseError as e:
                self._snack.show(f"Failed to delete tasks: {e}", COLORS["danger"])
                return

            await asyncio.sleep(ANIMATION_DELAY)
            msg = f"Deleted {count} '{title}' occurrence{'s' if count != 1 else ''}"
            self._snack.show(msg, COLORS["danger"], update=False)
            self._refresh_ui()
            event_bus.emit(AppEvent.TASK_DELETED, task)
            self._page.update()

        self._page.run_task(_delete)

    def _on_duplicate(self, task: Task) -> None:
        """Handle task duplicate request."""
        async def _duplicate() -> None:
            try:
                new_task = await self._service.duplicate_task(task)
            except DatabaseError as e:
                self._snack.show(f"Failed to duplicate task: {e}", COLORS["danger"])
                return

            await asyncio.sleep(ANIMATION_DELAY)
            self._snack.show(f"Task duplicated as '{new_task.title}'", update=False)
            self._refresh_ui()
            event_bus.emit(AppEvent.TASK_DUPLICATED, new_task)
            self._page.update()

        self._page.run_task(_duplicate)

    def _on_rename(self, task: Task) -> None:
        """Handle task rename request."""
        self._task_dialogs.rename(task)

    def _on_assign_project(self, task: Task) -> None:
        """Handle task assign project request."""
        self._task_dialogs.assign_project(task)

    def _on_date_picker(self, task: Task) -> None:
        """Handle task date picker request."""
        self._task_dialogs.date_picker(task)

    def _on_start_timer(self, task: Task) -> None:
        """Handle task start timer request."""
        self._timer_ctrl.start_timer(task)

    def _on_postpone(self, task: Task) -> None:
        """Handle task postpone request."""
        today = date_type.today()

        async def _postpone() -> None:
            try:
                new_date = await self._service.postpone_task(task)
            except DatabaseError as e:
                self._snack.show(f"Failed to postpone task: {e}", COLORS["danger"])
                return

            await asyncio.sleep(ANIMATION_DELAY)
            # Add context about where to find the task when postponing from Today/Inbox
            current_nav = self._state.selected_nav
            if new_date > today and current_nav in (NavItem.TODAY, NavItem.INBOX):
                msg = f"'{task.title}' postponed to {new_date.strftime('%b %d')} (see Upcoming)"
            else:
                msg = f"'{task.title}' postponed to {new_date.strftime('%b %d')}"
            self._snack.show(msg, update=False)
            self._refresh_ui()
            event_bus.emit(AppEvent.TASK_UPDATED, task)
            event_bus.emit(AppEvent.TASK_POSTPONED, task)
            self._page.update()

        self._page.run_task(_postpone)

    def _on_recurrence(self, task: Task) -> None:
        """Handle task recurrence request."""
        self._task_dialogs.recurrence(task)

    def _on_stats(self, task: Task) -> None:
        """Handle task stats request."""
        self._task_dialogs.stats(task)

    def _on_notes(self, task: Task) -> None:
        """Handle task notes request."""
        self._task_dialogs.notes(task)
