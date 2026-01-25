import flet as ft
from typing import Callable, Dict, Optional, Any 

from config import (
    NavItem,  
    PageType, 
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
        self._projects_arrow: Optional[ft.Icon] = None
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
        projects_arrow: ft.Icon,
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
        self._projects_arrow = projects_arrow
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
        self.state.current_page = PageType.TASKS
        if self.state.is_mobile and self._drawer:
            self._drawer.open = False
        self.update_nav()

    def toggle_projects(self) -> None:
        """Toggle the projects section expansion."""
        self.state.projects_expanded = not self.state.projects_expanded
        self.update_nav()

    def toggle_project(self, project_id: str) -> None:
        """Toggle selection of a specific project (keeps nav selection for filtering)."""
        if project_id in self.state.selected_projects:
            self.state.selected_projects.remove(project_id)
        else:
            self.state.selected_projects.add(project_id)
            # Don't change selected_nav - allow combining nav + project filter
        if self.state.is_mobile and self._drawer:
            self._drawer.open = False
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
        if NavItem.UPCOMING in self._nav_items:
            self._nav_items[NavItem.UPCOMING].selected = self.state.selected_nav == NavItem.UPCOMING
        if NavItem.PROJECTS in self._nav_items:
            self._nav_items[NavItem.PROJECTS].selected = len(self.state.selected_projects) > 0
 
        for pid, btn in self._project_btns.items():
            btn.set_selected(pid in self.state.selected_projects)
 
        if self._projects_items:
            self._projects_items.visible = self.state.projects_expanded
        if self._projects_arrow:
            self._projects_arrow.name = (
                ft.Icons.KEYBOARD_ARROW_DOWN
                if self.state.projects_expanded
                else ft.Icons.KEYBOARD_ARROW_RIGHT
            )
 
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
                    ft.Container(padding=20, content=self._nav_content)
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
        """Open the navigation drawer (mobile)."""
        if self._drawer:
            self._drawer.open = True
            self.page.update()

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

    def on_upcoming_click(self, e: ft.ControlEvent) -> None:
        self.nav_manager.select_nav(NavItem.UPCOMING)  

    def on_projects_toggle(self, e: ft.ControlEvent) -> None:
        self.nav_manager.toggle_projects()

    def on_menu_click(self, e: ft.ControlEvent) -> None:
        self.nav_manager.open_drawer()