import flet as ft
from typing import Optional, Callable, Any

from config import NavItem
from models.entities import Task, AppState, Project
from services.logic import TaskService
from ui.presenters.task_presenter import TaskPresenter


class UIController:
    """Facade for UI components to trigger application actions.

    This controller uses explicit callback attributes to decouple UI components
    from specific service/dialog implementations. UI components call methods
    like ctrl.rename(task), and the actual handler (e.g., task_dialogs.rename)
    is wired at app initialization time via the wire() method.

    All callbacks are typed for IDE navigation and static analysis support.
    Callbacks are initialized to None and must be wired before use.

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
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self._nav_manager = None

        # Typed callback attributes - must be wired before use
        self._update_nav: Optional[Callable[[], None]] = None
        self._refresh: Optional[Callable[[], None]] = None
        self._show_snack: Optional[Callable[[str], None]] = None
        self._delete_task: Optional[Callable[[Task], None]] = None
        self._duplicate_task: Optional[Callable[[Task], None]] = None
        self._rename_task: Optional[Callable[[Task], None]] = None
        self._assign_project: Optional[Callable[[Task], None]] = None
        self._date_picker: Optional[Callable[[Task], None]] = None
        self._start_timer: Optional[Callable[[Task], None]] = None
        self._postpone_task: Optional[Callable[[Task], None]] = None
        self._recurrence: Optional[Callable[[Task], None]] = None
        self._stats: Optional[Callable[[Task], None]] = None
        self._notes: Optional[Callable[[Task], None]] = None
        self._update_content: Optional[Callable[[], None]] = None
        self._duration_completion: Optional[Callable[[Task, Callable[[Task], None]], None]] = None

    def set_nav_manager(self, nav_manager: Any) -> None:
        """Set the navigation manager reference."""
        self._nav_manager = nav_manager

    def wire(
        self,
        update_nav: Callable[[], None] = None,
        refresh: Callable[[], None] = None,
        show_snack: Callable[[str], None] = None,
        delete_task: Callable[[Task], None] = None,
        duplicate_task: Callable[[Task], None] = None,
        rename_task: Callable[[Task], None] = None,
        assign_project: Callable[[Task], None] = None,
        date_picker: Callable[[Task], None] = None,
        start_timer: Callable[[Task], None] = None,
        postpone_task: Callable[[Task], None] = None,
        recurrence: Callable[[Task], None] = None,
        stats: Callable[[Task], None] = None,
        notes: Callable[[Task], None] = None,
        update_content: Callable[[], None] = None,
        duration_completion: Callable[[Task, Callable[[Task], None]], None] = None,
    ) -> None:
        """Wire action callbacks. Called once at app initialization.

        All parameters are optional to allow partial wiring for tests.
        """
        if update_nav is not None:
            self._update_nav = update_nav
        if refresh is not None:
            self._refresh = refresh
        if show_snack is not None:
            self._show_snack = show_snack
        if delete_task is not None:
            self._delete_task = delete_task
        if duplicate_task is not None:
            self._duplicate_task = duplicate_task
        if rename_task is not None:
            self._rename_task = rename_task
        if assign_project is not None:
            self._assign_project = assign_project
        if date_picker is not None:
            self._date_picker = date_picker
        if start_timer is not None:
            self._start_timer = start_timer
        if postpone_task is not None:
            self._postpone_task = postpone_task
        if recurrence is not None:
            self._recurrence = recurrence
        if stats is not None:
            self._stats = stats
        if notes is not None:
            self._notes = notes
        if update_content is not None:
            self._update_content = update_content
        if duration_completion is not None:
            self._duration_completion = duration_completion

    def get_project(self, project_id: Optional[str]) -> Optional[Project]:
        return self.state.get_project_by_id(project_id)

    def get_due_date_str(self, task: Task) -> Optional[str]:
        return TaskPresenter.format_due_date(task.due_date)

    def toggle_project(self, project_id: str) -> None:
        """Toggle project selection - delegates to nav_manager if available."""
        if self._nav_manager:
            self._nav_manager.toggle_project(project_id)
        else:
            # Fallback for backwards compatibility
            if project_id in self.state.selected_projects:
                self.state.selected_projects.remove(project_id)
            else:
                self.state.selected_projects.add(project_id)
                self.state.selected_nav = NavItem.PROJECTS
            if self.state.is_mobile:
                self.page.drawer.open = False
            if self._update_nav:
                self._update_nav()

    def navigate_to(self, page_name: str) -> None:
        """Navigate to a page - delegates to nav_manager if available."""
        if self._nav_manager:
            self._nav_manager.navigate_to(page_name)
        else:
            self.state.current_page = page_name
            if self._update_content:
                self._update_content()
            self.page.update()

    async def complete_async(self, task: Task) -> None:
        """Complete a task - async version for direct DB access."""
        # Check if task has time entries
        has_time_entries = False
        if task.id:
            entries = await self.service.load_time_entries_for_task(task.id)
            has_time_entries = len(entries) > 0

        if not has_time_entries and task.spent_seconds == 0:
            # Show duration knob dialog for tasks without time entries
            if self._duration_completion:
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
        if new_task and self._show_snack:
            self._show_snack(f"Next occurrence scheduled for {new_task.due_date.strftime('%b %d')}")
        if self._refresh:
            self._refresh()

    def _do_complete(self, task: Task) -> None:
        """Sync wrapper for _do_complete_async - used by duration dialog callback."""
        async def _coro() -> None:
            await self._do_complete_async(task)
        self.page.run_task(_coro)

    async def uncomplete_async(self, task: Task) -> None:
        """Uncomplete a task - async version."""
        if await self.service.uncomplete_task(task):
            if self._refresh:
                self._refresh()

    def uncomplete(self, task: Task) -> None:
        """Uncomplete a task - sync wrapper."""
        async def _coro() -> None:
            await self.uncomplete_async(task)
        self.page.run_task(_coro)

    def delete(self, task: Task) -> None:
        if self._delete_task:
            self._delete_task(task)

    def duplicate(self, task: Task) -> None:
        if self._duplicate_task:
            self._duplicate_task(task)

    def rename(self, task: Task) -> None:
        if self._rename_task:
            self._rename_task(task)

    def assign_project(self, task: Task) -> None:
        if self._assign_project:
            self._assign_project(task)

    def date_picker(self, task: Task) -> None:
        if self._date_picker:
            self._date_picker(task)

    def start_timer(self, task: Task) -> None:
        if self._start_timer:
            self._start_timer(task)

    def postpone(self, task: Task) -> None:
        if self._postpone_task:
            self._postpone_task(task)

    def recurrence(self, task: Task) -> None:
        if self._recurrence:
            self._recurrence(task)

    def stats(self, task: Task) -> None:
        if self._stats:
            self._stats(task)

    def notes(self, task: Task) -> None:
        if self._notes:
            self._notes(task)
