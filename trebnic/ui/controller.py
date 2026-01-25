import flet as ft
from typing import Optional, Any

from models.entities import AppState, Project


class UIController:
    """Facade for UI navigation and project utilities.

    Task actions are now handled by TaskActionHandler via the EventBus.
    This controller is kept for navigation helpers and project utilities
    that are used by various UI components.
    """

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        nav_manager: Any,
    ) -> None:
        self.page = page
        self.state = state
        self._nav_manager = nav_manager

    def get_project(self, project_id: Optional[str]) -> Optional[Project]:
        """Get a project by ID from the app state."""
        return self.state.get_project_by_id(project_id)

    def toggle_project(self, project_id: str) -> None:
        """Toggle project selection - delegates to nav_manager."""
        self._nav_manager.toggle_project(project_id)

    def navigate_to(self, page_name: str) -> None:
        """Navigate to a page - delegates to nav_manager."""
        self._nav_manager.navigate_to(page_name)
