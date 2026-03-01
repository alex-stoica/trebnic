import flet as ft
from typing import Callable, Dict, Optional, Any 

from config import (
    NavItem,
    PageType,
    PADDING_2XL,
)
from models.entities import AppState


class NavigationManager:
    """Manages navigation state and UI updates."""

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
    ) -> None:
        self.page = page
        self.state = state
        self._nav_items: Dict[NavItem, ft.ListTile] = {} 
        self._project_btns: Dict[str, Any] = {}
        self._projects_items: Optional[ft.Column] = None
        self._drawer: Optional[ft.NavigationDrawer] = None
        self._sidebar: Optional[ft.Container] = None
        self._menu_btn: Optional[ft.IconButton] = None
        self._nav_content: Optional[ft.Column] = None
        self._on_content_update: Optional[Callable[[], None]] = None
        self._on_refresh: Optional[Callable[[], None]] = None
        self._settings_menu: Optional[ft.PopupMenuButton] = None
        self._get_settings_items: Optional[Callable[[], list]] = None

    def wire(
        self,
        nav_items: Dict[NavItem, ft.ListTile], 
        project_btns: Dict[str, Any],
        projects_items: ft.Column,
        drawer: ft.NavigationDrawer,
        sidebar: ft.Container,
        menu_btn: ft.IconButton,
        nav_content: ft.Column,
        settings_menu: ft.PopupMenuButton,
        on_content_update: Callable[[], None],
        on_refresh: Callable[[], None],
        get_settings_items: Callable[[], list],
    ) -> None:
        """Wire up navigation components."""
        self._nav_items = nav_items
        self._project_btns = project_btns
        self._projects_items = projects_items
        self._drawer = drawer
        self._sidebar = sidebar
        self._menu_btn = menu_btn
        self._nav_content = nav_content
        self._settings_menu = settings_menu
        self._on_content_update = on_content_update
        self._on_refresh = on_refresh
        self._get_settings_items = get_settings_items

    def select_nav(self, name: NavItem) -> None:
        """Select a navigation item (keeps project selection for filtering)."""
        self.state.selected_nav = name
        # Don't clear selected_projects - allow combining nav + project filter
        if name == NavItem.NOTES:
            self.state.current_page = PageType.NOTES
        else:
            self.state.current_page = PageType.TASKS
        if self.state.is_mobile and self._drawer:
            self.page.run_task(self.page.close_drawer)
        self.update_nav()

    def toggle_project(self, project_id: str) -> None:
        """Toggle selection of a specific project (mutually exclusive - only one at a time)."""
        if project_id in self.state.selected_projects:
            # Clicking selected project deselects it
            self.state.selected_projects.remove(project_id)
        else:
            # Clear any other selected projects first (only one can be selected)
            self.state.selected_projects.clear()
            self.state.selected_projects.add(project_id)
        if self.state.is_mobile and self._drawer:
            self.page.run_task(self.page.close_drawer)
        self.update_nav()

    def navigate_to(self, page_name: PageType) -> None:  
        """Navigate to a specific page."""
        self.state.current_page = page_name
        if self._on_content_update:
            self._on_content_update()
        self.page.update()

    def update_nav(self) -> None:
        """Update navigation state and UI."""  
        if NavItem.INBOX in self._nav_items:
            self._nav_items[NavItem.INBOX].selected = self.state.selected_nav == NavItem.INBOX
        if NavItem.TODAY in self._nav_items:
            self._nav_items[NavItem.TODAY].selected = self.state.selected_nav == NavItem.TODAY
        if NavItem.CALENDAR in self._nav_items:
            self._nav_items[NavItem.CALENDAR].selected = self.state.selected_nav == NavItem.CALENDAR
        if NavItem.NOTES in self._nav_items:
            self._nav_items[NavItem.NOTES].selected = self.state.selected_nav == NavItem.NOTES
        if NavItem.PROJECTS in self._nav_items:
            self._nav_items[NavItem.PROJECTS].selected = len(self.state.selected_projects) > 0
 
        for pid, btn in self._project_btns.items():
            btn.set_selected(pid in self.state.selected_projects)

        # Projects always visible, no toggle needed
 
        if self._settings_menu and self._get_settings_items:
            self._settings_menu.items = self._get_settings_items()
 
        if self._on_content_update:
            self._on_content_update()
        if self._on_refresh:
            self._on_refresh()
        self.page.update()

    def handle_resize(self, is_mobile: bool) -> None:
        """Handle layout changes based on mobile/desktop mode."""
        self.state.is_mobile = is_mobile

        if is_mobile:
            if self._sidebar:
                self._sidebar.visible = False
                self._sidebar.content = None
            if self._menu_btn:
                self._menu_btn.visible = True
            if self._drawer and self._nav_content:
                self._drawer.controls = [
                    ft.Container(padding=PADDING_2XL, content=self._nav_content)
                ]
        else:
            if self._drawer:
                self._drawer.controls = []
            if self._sidebar and self._nav_content:
                self._sidebar.content = self._nav_content
                self._sidebar.visible = True
            if self._menu_btn:
                self._menu_btn.visible = False

    def open_drawer(self) -> None:
        """Open the navigation drawer (mobile).

        Uses page.show_drawer() which is async in Flet 0.80+.
        """
        if self._drawer:
            self.page.run_task(self.page.show_drawer)

    def set_project_btns(self, project_btns: Dict[str, Any]) -> None:
        """Update the project buttons reference."""
        self._project_btns = project_btns

    def set_projects_items(self, projects_items: ft.Column) -> None:
        """Update the projects items column reference."""
        self._projects_items = projects_items


class NavigationHandler:
    """Handles navigation-related click events with named methods."""

    def __init__(self, nav_manager: NavigationManager) -> None:
        self.nav_manager = nav_manager

    def on_inbox_click(self, e: ft.ControlEvent) -> None:
        self.nav_manager.select_nav(NavItem.INBOX) 

    def on_today_click(self, e: ft.ControlEvent) -> None:
        self.nav_manager.select_nav(NavItem.TODAY)  

    def on_calendar_click(self, e: ft.ControlEvent) -> None:
        self.nav_manager.select_nav(NavItem.CALENDAR)  

    def on_notes_click(self, e: ft.ControlEvent) -> None:
        self.nav_manager.select_nav(NavItem.NOTES)

    def on_menu_click(self, e: ft.ControlEvent) -> None:
        self.nav_manager.open_drawer()