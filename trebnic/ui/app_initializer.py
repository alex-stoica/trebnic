import flet as ft
from typing import Dict, Optional

from database import DatabaseError
from events import event_bus
from registry import registry, Services
from services.crypto import crypto
from services.logic import TaskService
from services.timer import TimerService
from models.entities import AppState
from ui.controller import UIController
from ui.navigation import NavigationManager, NavigationHandler
from ui.helpers import SnackService
from ui.components import ProjectSidebarItem, TimerWidget
from ui.dialogs import TaskDialogs, ProjectDialogs
from ui.pages import TasksView, CalendarView, ProfilePage, PreferencesPage, TimeEntriesView
from ui.timer_controller import TimerController
from ui.auth_controller import AuthController


class AppComponents:
    """Container for initialized application components."""

    def __init__(self) -> None:
        self.state: Optional[AppState] = None
        self.service: Optional[TaskService] = None
        self.snack: Optional[SnackService] = None
        self.timer_svc: Optional[TimerService] = None
        self.ctrl: Optional[UIController] = None
        self.nav_manager: Optional[NavigationManager] = None
        self.nav_handler: Optional[NavigationHandler] = None
        self.timer_ctrl: Optional[TimerController] = None
        self.auth_ctrl: Optional[AuthController] = None
        
        # UI Components
        self.project_btns: Dict[str, ProjectSidebarItem] = {}
        self.tasks_view: Optional[TasksView] = None
        self.calendar_view: Optional[CalendarView] = None
        self.time_entries_view: Optional[TimeEntriesView] = None
        self.profile_page: Optional[ProfilePage] = None
        self.prefs_page: Optional[PreferencesPage] = None
        self.task_dialogs: Optional[TaskDialogs] = None
        self.project_dialogs: Optional[ProjectDialogs] = None
        self.timer_widget: Optional[TimerWidget] = None
        
        # Layout elements
        self.nav_items: Dict[str, ft.ListTile] = {}
        self.projects_items: Optional[ft.Column] = None
        self.projects_arrow: Optional[ft.Icon] = None
        self.drawer: Optional[ft.NavigationDrawer] = None
        self.sidebar: Optional[ft.Container] = None
        self.menu_btn: Optional[ft.IconButton] = None
        self.nav_content: Optional[ft.Column] = None
        self.settings_menu: Optional[ft.PopupMenuButton] = None
        self.header: Optional[ft.Row] = None
        self.page_content: Optional[ft.Container] = None
        self.main_area: Optional[ft.Container] = None
        
        self.pending_error: Optional[str] = None


class AppInitializer:
    """Handles application setup and component wiring."""
    
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.components = AppComponents()
    
    def initialize(self) -> AppComponents:
        """Initialize all application components and return them."""
        self._register_core_services()
        self._setup_page()
        self._init_auth()
        self._init_services()
        self._init_navigation()
        self._init_ui_components()
        self._init_timer_controller()
        self._subscribe_to_events()
        return self.components

    def _register_core_services(self) -> None:
        """Register core services in the registry before any component initialization.

        This must run first to ensure services are available to other modules
        that depend on them via the registry (e.g., database.py uses crypto).
        """
        registry.register(Services.CRYPTO, crypto)
        registry.register(Services.EVENT_BUS, event_bus)

    def _init_auth(self) -> None:
        """Initialize authentication controller.

        Note: Auth initialization is async but we need to run it synchronously
        during app init. The actual auth check (unlock dialog) happens after
        the main UI is built.
        """
        self.components.auth_ctrl = AuthController(self.page)
    
    def _setup_page(self) -> None:
        """Configure the Flet page settings."""
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
    
    def _init_services(self) -> None:
        """Initialize application services."""
        try:
            self.components.state = TaskService.load_state()
        except DatabaseError as e:
            self.components.state = TaskService.create_empty_state()
            self.components.pending_error = f"Failed to load data: {e}"

        # Pass page to TaskService for proper async scheduling in Flet context
        self.components.service = TaskService(self.components.state, self.page)
        self.components.snack = SnackService(self.page)
        self.components.timer_svc = TimerService()
        self.components.ctrl = UIController(
            self.page,
            self.components.state,
            self.components.service
        )
    
    def _init_navigation(self) -> None:
        """Initialize navigation manager and handler."""
        self.components.nav_manager = NavigationManager(
            self.page, 
            self.components.state
        )
        self.components.nav_handler = NavigationHandler(self.components.nav_manager)
        self.components.ctrl.set_nav_manager(self.components.nav_manager)
    
    def _init_ui_components(self) -> None:
        """Initialize UI components."""
        state = self.components.state
        ctrl = self.components.ctrl
        service = self.components.service
        snack = self.components.snack
        nav_manager = self.components.nav_manager
        
        self.components.project_btns = {
            p.id: ProjectSidebarItem(p, ctrl)
            for p in state.projects
        }

        self.components.tasks_view = TasksView(
            self.page, state, service, ctrl, snack
        )
        self.components.calendar_view = CalendarView(state, on_update=None)

        self.components.time_entries_view = TimeEntriesView(
            self.page, state, service, snack, nav_manager.navigate_to,
        )

        self.components.profile_page = ProfilePage(
            self.page, state, service, snack, nav_manager.navigate_to,
        )

        self.components.prefs_page = PreferencesPage(
            self.page, state, service, snack, nav_manager.navigate_to,
            self.components.tasks_view,
        )

        self.components.task_dialogs = TaskDialogs(
            self.page, state, service, snack, nav_manager.navigate_to,
        )

        self.components.project_dialogs = ProjectDialogs(
            self.page, state, service, snack,
        )

        self.components.timer_widget = TimerWidget(lambda e: None) 
    
    def _init_timer_controller(self) -> None:
        """Initialize the timer controller."""
        self.components.timer_ctrl = TimerController(
            page=self.page,
            timer_svc=self.components.timer_svc,
            service=self.components.service,
            snack=self.components.snack,
            timer_widget=self.components.timer_widget,
        )
    
    def _subscribe_to_events(self) -> None:
        """Subscribe to application events."""
        # Events are subscribed by the main app class
        pass