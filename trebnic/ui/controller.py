import flet as ft
from typing import Optional, Callable, Any

from models.entities import Task, AppState, Project
from services.logic import TaskService
from services.time_entry_service import TimeEntryService
from ui.presenters.task_presenter import TaskPresenter


class UIController:
    """Facade for UI components to trigger application actions.

    This controller uses explicit callback attributes to decouple UI components
    from specific service/dialog implementations. UI components call methods
    like ctrl.rename(task), and the actual handler (e.g., task_dialogs.rename)
    is invoked.

    All callbacks are typed for IDE navigation and static analysis support.
    All required callbacks must be passed to the constructor - the object is
    fully initialized upon creation (no two-phase initialization).

    This pattern allows:
    - UI components to be tested in isolation with mock callbacks
    - Swapping implementations without changing UI code
    - Centralized action dispatching for logging/metrics if needed
    - Full IDE navigation (Ctrl+Click to definitions)
    """

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        service: TaskService,
        time_entry_service: TimeEntryService,
        nav_manager: Any,
        update_nav: Callable[[], None],
        refresh: Callable[[], None],
        show_snack: Callable[[str], None],
        delete_task: Callable[[Task], None],
        duplicate_task: Callable[[Task], None],
        rename_task: Callable[[Task], None],
        assign_project: Callable[[Task], None],
        date_picker: Callable[[Task], None],
        start_timer: Callable[[Task], None],
        postpone_task: Callable[[Task], None],
        recurrence: Callable[[Task], None],
        stats: Callable[[Task], None],
        notes: Callable[[Task], None],
        update_content: Callable[[], None],
        duration_completion: Callable[[Task, Callable[[Task], None]], None],
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self.time_entry_service = time_entry_service
        self._nav_manager = nav_manager

        self._update_nav = update_nav
        self._refresh = refresh
        self._show_snack = show_snack
        self._delete_task = delete_task
        self._duplicate_task = duplicate_task
        self._rename_task = rename_task
        self._assign_project = assign_project
        self._date_picker = date_picker
        self._start_timer = start_timer
        self._postpone_task = postpone_task
        self._recurrence = recurrence
        self._stats = stats
        self._notes = notes
        self._update_content = update_content
        self._duration_completion = duration_completion

    def get_project(self, project_id: Optional[str]) -> Optional[Project]:
        return self.state.get_project_by_id(project_id)

    def get_due_date_str(self, task: Task) -> Optional[str]:
        return TaskPresenter.format_due_date(task.due_date)

    def toggle_project(self, project_id: str) -> None:
        """Toggle project selection - delegates to nav_manager."""
        self._nav_manager.toggle_project(project_id)

    def navigate_to(self, page_name: str) -> None:
        """Navigate to a page - delegates to nav_manager."""
        self._nav_manager.navigate_to(page_name)

    async def complete_async(self, task: Task) -> None:
        """Complete a task - async version for direct DB access."""
        has_time_entries = False
        if task.id:
            entries = await self.time_entry_service.load_time_entries_for_task(task.id)
            has_time_entries = len(entries) > 0

        if not has_time_entries and task.spent_seconds == 0:
            self._duration_completion(task, self._do_complete)
        else:
            await self._do_complete_async(task)

    def complete(self, task: Task) -> None:
        """Complete a task - sync wrapper that schedules async work."""
        async def _coro() -> None:
            await self.complete_async(task)
        self.page.run_task(_coro)

    async def _do_complete_async(self, task: Task) -> None:
        """Actually complete the task after any duration entry."""
        new_task = await self.service.complete_task(task)
        if new_task:
            self._show_snack(f"Next occurrence scheduled for {new_task.due_date.strftime('%b %d')}")
        self._refresh()

    def _do_complete(self, task: Task) -> None:
        """Sync wrapper for _do_complete_async - used by duration dialog callback."""
        async def _coro() -> None:
            await self._do_complete_async(task)
        self.page.run_task(_coro)

    async def uncomplete_async(self, task: Task) -> None:
        """Uncomplete a task - async version."""
        if await self.service.uncomplete_task(task):
            self._refresh()

    def uncomplete(self, task: Task) -> None:
        """Uncomplete a task - sync wrapper."""
        async def _coro() -> None:
            await self.uncomplete_async(task)
        self.page.run_task(_coro)

    def delete(self, task: Task) -> None:
        self._delete_task(task)

    def duplicate(self, task: Task) -> None:
        self._duplicate_task(task)

    def rename(self, task: Task) -> None:
        self._rename_task(task)

    def assign_project(self, task: Task) -> None:
        self._assign_project(task)

    def date_picker(self, task: Task) -> None:
        self._date_picker(task)

    def start_timer(self, task: Task) -> None:
        self._start_timer(task)

    def postpone(self, task: Task) -> None:
        self._postpone_task(task)

    def recurrence(self, task: Task) -> None:
        self._recurrence(task)

    def stats(self, task: Task) -> None:
        self._stats(task)

    def notes(self, task: Task) -> None:
        self._notes(task)
