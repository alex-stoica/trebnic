import flet as ft
from typing import Optional, Dict, Any, Callable

from config import NavItem
from models.entities import Task, AppState, Project
from services.logic import TaskService
from ui.presenters.task_presenter import TaskPresenter


class UIController:
    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        service: TaskService,
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self._callbacks: Dict[str, Callable[..., Any]] = {}
        self._nav_manager = None  

    def set_nav_manager(self, nav_manager: Any) -> None:
        """Set the navigation manager reference."""
        self._nav_manager = nav_manager

    def wire(self, **callbacks: Callable[..., Any]) -> None:
        self._callbacks = callbacks

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name in self._callbacks:
            return self._callbacks[name](*args, **kwargs)
        return None

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
            self._call("update_nav")

    def navigate_to(self, page_name: str) -> None:
        """Navigate to a page - delegates to nav_manager if available."""
        if self._nav_manager:
            self._nav_manager.navigate_to(page_name)
        else:
            self.state.current_page = page_name
            self._call("update_content")
            self.page.update()

    def complete(self, task: Task) -> None:
        new_task = self.service.complete_task(task)
        if new_task:
            self._call(
                "show_snack",
                f"Next occurrence scheduled for {new_task.due_date.strftime('%b %d')}",
            )
        self._call("refresh")

    def uncomplete(self, task: Task) -> None:
        if self.service.uncomplete_task(task):
            self._call("refresh")

    def delete(self, task: Task) -> None:
        self._call("delete_task", task)

    def duplicate(self, task: Task) -> None:
        self._call("duplicate_task", task)

    def rename(self, task: Task) -> None:
        self._call("rename_task", task)

    def assign_project(self, task: Task) -> None:
        self._call("assign_project", task)

    def date_picker(self, task: Task) -> None:
        self._call("date_picker", task)

    def start_timer(self, task: Task) -> None:
        self._call("start_timer", task)

    def postpone(self, task: Task) -> None:
        self._call("postpone_task", task)

    def recurrence(self, task: Task) -> None:
        self._call("recurrence", task)

    def stats(self, task: Task) -> None:
        self._call("stats", task)

    def notes(self, task: Task) -> None:
        self._call("notes", task)