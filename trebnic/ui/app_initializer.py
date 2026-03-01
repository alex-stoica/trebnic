import flet as ft
from typing import Dict, Optional

from config import NavItem
from database import DatabaseError
from events import event_bus
from registry import registry, Services
from services.crypto import crypto
from services.logic import TaskService
from services.timer import TimerService
from services.project_service import ProjectService
from services.time_entry_service import TimeEntryService
from services.settings_service import SettingsService
from services.notification_service import notification_service
from services.daily_notes_service import DailyNoteService
from models.entities import AppState
from ui.navigation import NavigationManager, NavigationHandler
from ui.helpers import SnackService
from ui.components import ProjectSidebarItem, TimerWidget
from ui.dialogs import TaskDialogs, ProjectDialogs
from ui.pages import (
    TasksView, CalendarView, NotesView, ProfilePage, TimeEntriesView, HelpPage, FeedbackPage,
    StatsPage, ChatView,
)
from ui.timer_controller import TimerController
from ui.auth_controller import AuthController
from ui.handlers import TaskActionHandler
from api import TrebnicAPI
from core import ServiceContainer
from services.claude_service import ClaudeService


class AppComponents:
    """Container for initialized application components."""

    def __init__(self) -> None:
        self.state: Optional[AppState] = None
        self.service: Optional[TaskService] = None
        self.project_service: Optional[ProjectService] = None
        self.time_entry_service: Optional[TimeEntryService] = None
        self.settings_service: Optional[SettingsService] = None
        self.daily_notes_service: Optional[DailyNoteService] = None
        self.snack: Optional[SnackService] = None
        self.timer_svc: Optional[TimerService] = None
        self.nav_manager: Optional[NavigationManager] = None
        self.nav_handler: Optional[NavigationHandler] = None
        self.timer_ctrl: Optional[TimerController] = None
        self.auth_ctrl: Optional[AuthController] = None

        # UI Components
        self.project_btns: Dict[str, ProjectSidebarItem] = {}
        self.tasks_view: Optional[TasksView] = None
        self.calendar_view: Optional[CalendarView] = None
        self.notes_view: Optional[NotesView] = None
        self.time_entries_view: Optional[TimeEntriesView] = None
        self.profile_page: Optional[ProfilePage] = None
        self.help_page: Optional[HelpPage] = None
        self.feedback_page: Optional[FeedbackPage] = None
        self.stats_page: Optional[StatsPage] = None
        self.task_dialogs: Optional[TaskDialogs] = None
        self.project_dialogs: Optional[ProjectDialogs] = None
        self.timer_widget: Optional[TimerWidget] = None
        self.task_handler: Optional[TaskActionHandler] = None
        self.chat_view: Optional[ChatView] = None
        self.claude_service: Optional[ClaudeService] = None

        # Layout elements
        self.nav_items: Dict[str, ft.ListTile] = {}
        self.projects_items: Optional[ft.Column] = None
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
        self._init_notification_service()
        self._init_task_handler()
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
 
        self.components.service = TaskService(self.components.state, self.page)
 
        self.components.project_service = ProjectService(self.components.state)
        self.components.time_entry_service = TimeEntryService()
        self.components.settings_service = SettingsService(self.components.state)
        self.components.daily_notes_service = DailyNoteService()

        self.components.snack = SnackService(self.page)
        if self.components.auth_ctrl:
            self.components.auth_ctrl.snack = self.components.snack
        self.components.timer_svc = TimerService()

        registry.register(Services.TASK, self.components.service)
        registry.register(Services.PROJECT, self.components.project_service)
        registry.register(Services.TIME_ENTRY, self.components.time_entry_service)
        registry.register(Services.SETTINGS, self.components.settings_service)
        registry.register(Services.DAILY_NOTES, self.components.daily_notes_service)
        registry.register(Services.TIMER, self.components.timer_svc)
        # Note: UIController is created in app.py after all components are ready
    
    def _init_navigation(self) -> None:
        """Initialize navigation manager and handler."""
        self.components.nav_manager = NavigationManager(
            self.page,
            self.components.state
        )
        self.components.nav_handler = NavigationHandler(self.components.nav_manager)
    
    def _init_ui_components(self) -> None:
        """Initialize UI components.

        Components emit events to the EventBus for user interactions rather than
        calling controller methods directly. This decouples UI from business logic
        and eliminates the need for late-binding workarounds.
        """
        state = self.components.state
        task_service = self.components.service
        project_service = self.components.project_service
        time_entry_service = self.components.time_entry_service
        settings_service = self.components.settings_service
        snack = self.components.snack
        nav_manager = self.components.nav_manager

        # ProjectSidebarItem uses nav_manager.toggle_project directly
        self.components.project_btns = {
            p.id: ProjectSidebarItem(p, nav_manager.toggle_project)
            for p in state.projects
        }

        def open_notes() -> None:
            nav_manager.select_nav(NavItem.NOTES)

        self.components.tasks_view = TasksView(
            self.page, state, task_service, snack,
            on_open_notes=open_notes,
        )
        self.components.calendar_view = CalendarView(
            self.page, state, self.components.daily_notes_service, snack,
            on_update=None,
            on_open_notes=open_notes,
        )

        self.components.notes_view = NotesView(
            self.page, state, self.components.daily_notes_service, snack,
        )

        self.components.time_entries_view = TimeEntriesView(
            self.page, state, task_service, time_entry_service, snack, nav_manager.navigate_to,
        )

        self.components.profile_page = ProfilePage(
            self.page, state, task_service, settings_service, snack, nav_manager.navigate_to,
            self.components.tasks_view,
        )

        self.components.help_page = HelpPage(
            self.page, nav_manager.navigate_to
        )

        self.components.feedback_page = FeedbackPage(
            self.page, nav_manager.navigate_to, snack
        )

        self.components.stats_page = StatsPage(
            self.page, state, nav_manager.navigate_to, time_entry_service.load_time_entries,
        )

        self.components.task_dialogs = TaskDialogs(
            self.page, state, task_service, time_entry_service, snack, nav_manager.navigate_to,
        )

        self.components.project_dialogs = ProjectDialogs(
            self.page, state, project_service, snack,
        )

        self.components.timer_widget = TimerWidget(lambda e: None)

        # Claude chat service and view
        svc_container = ServiceContainer(
            state=state,
            task=task_service,
            project=project_service,
            time_entry=time_entry_service,
            settings=settings_service,
            timer=self.components.timer_svc,
            daily_notes=self.components.daily_notes_service,
        )
        trebnic_api = TrebnicAPI(svc_container)
        self.components.claude_service = ClaudeService(trebnic_api)
        self.components.chat_view = ChatView(
            self.page, state, self.components.claude_service, snack, nav_manager.navigate_to,
        )
    
    def _init_timer_controller(self) -> None:
        """Initialize the timer controller.

        Injects dependencies into the timer service first, then creates the
        controller which subscribes to service events.
        """
        # Inject dependencies into service (framework-agnostic scheduling)
        self.components.timer_svc.inject_dependencies(
            time_entry_service=self.components.time_entry_service,
            task_service=self.components.service,
            async_scheduler=self.page.run_task,
        )

        self.components.timer_ctrl = TimerController(
            page=self.page,
            timer_svc=self.components.timer_svc,
            snack=self.components.snack,
            timer_widget=self.components.timer_widget,
        )

    def _init_notification_service(self) -> None:
        """Initialize the notification service.

        Injects dependencies and starts the scheduler loop for task reminders.
        """
        notification_service.inject_dependencies(
            page=self.page,
            async_scheduler=self.page.run_task,
            get_state=lambda: self.components.state,
        )
        notification_service.start_scheduler()
        registry.register(Services.NOTIFICATION, notification_service)

    def _init_task_handler(self) -> None:
        """Initialize the task action handler.

        TaskActionHandler subscribes to TASK_*_REQUESTED events and handles
        task actions that were previously routed through app.py.
        """
        self.components.task_handler = TaskActionHandler(
            page=self.page,
            state=self.components.state,
            service=self.components.service,
            time_entry_service=self.components.time_entry_service,
            task_dialogs=self.components.task_dialogs,
            timer_ctrl=self.components.timer_ctrl,
            snack=self.components.snack,
            refresh_ui=self.components.tasks_view.refresh,
            refresh_ui_async=self.components.tasks_view._refresh_async,
        )

    def _subscribe_to_events(self) -> None:
        """Subscribe to application events."""
        # Events are subscribed by the main app class
        pass