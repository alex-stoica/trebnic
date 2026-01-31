import flet as ft
import logging
from typing import Optional, Any, List

logger = logging.getLogger(__name__)

from config import COLORS, MOBILE_BREAKPOINT, NavItem, PageType, FONT_SIZE_LG
from database import db
from events import event_bus, AppEvent, Subscription
from i18n import t
from services.notification_service import notification_service
from ui.components import ProjectSidebarItem, TimerWidget
from ui.app_initializer import AppInitializer
from ui.controller import UIController


class TrebnicApp:
    """Main application class orchestrating the Trebnic task manager."""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.event_bus = event_bus
        self._subscriptions: List[Subscription] = []

        initializer = AppInitializer(page)
        self._components = initializer.initialize()

        self._extract_components()

        # Wire page to service for proper async scheduling
        self.service.set_page(page)

        # Wire calendar update callback
        self.calendar_view.on_update = self._on_calendar_update

        self.timer_widget = TimerWidget(self._on_timer_stop)
        self.timer_ctrl.timer_widget = self.timer_widget

        self._subscribe_to_events()
        self._create_controller()
        self._build_layout()

        # Recover any running timer from before app restart
        self.timer_ctrl.recover_timer(self.state)

        # Register cleanup on page close
        self.page.on_close = self._on_page_close

        # Initialize auth and check if unlock needed
        self.page.run_task(self._init_auth)

    def _extract_components(self) -> None:
        """Extract components from initializer for class-level access.

        Note: ctrl (UIController) is created separately in _create_controller()
        after all components are extracted, to ensure all callbacks are available.
        """
        c = self._components
        self.state = c.state
        self.service = c.service
        self.snack = c.snack
        self.timer_svc = c.timer_svc
        self.nav_manager = c.nav_manager
        self.nav_handler = c.nav_handler
        self.timer_ctrl = c.timer_ctrl
        self.auth_ctrl = c.auth_ctrl
        self.project_btns = c.project_btns
        self.tasks_view = c.tasks_view
        self.calendar_view = c.calendar_view
        self.time_entries_view = c.time_entries_view
        self.profile_page = c.profile_page
        self.help_page = c.help_page
        self.feedback_page = c.feedback_page
        self.stats_page = c.stats_page
        self.task_dialogs = c.task_dialogs
        self.project_dialogs = c.project_dialogs
        self.time_entry_service = c.time_entry_service
        self.task_handler = c.task_handler
        self._pending_error = c.pending_error

    def _subscribe_to_events(self) -> None:
        """Subscribe to application events and track subscriptions for cleanup."""
        # UI refresh and lifecycle events
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.REFRESH_UI, self._on_refresh_ui)
        )
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.SIDEBAR_REBUILD, self._on_sidebar_rebuild)
        )
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.DATA_RESET, self._on_data_reset)
        )
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.PROJECT_UPDATED, self._on_project_or_task_changed)
        )
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.TASK_POSTPONED, self._on_project_or_task_changed)
        )
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.LANGUAGE_CHANGED, self._on_language_changed)
        )
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.NOTIFICATION_TAPPED, self._on_notification_tapped)
        )
        # Note: Task action events (TASK_*_REQUESTED) are handled by TaskActionHandler

    def _unsubscribe_all(self) -> None:
        """Unsubscribe all event subscriptions."""
        for subscription in self._subscriptions:
            subscription.unsubscribe()
        self._subscriptions.clear()

    def _on_page_close(self, e: ft.ControlEvent) -> None:
        """Handle page close - cleanup resources."""
        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up all resources."""
        self._unsubscribe_all()

        # Clean up task handler subscriptions
        if self.task_handler:
            self.task_handler.cleanup()

        # Stop timer if running
        if self.timer_ctrl:
            self.timer_ctrl.cleanup()

        # Clean up notification service and database sequentially
        # Must be in single async function to ensure notifications finish before db closes
        async def cleanup_all() -> None:
            try:
                await notification_service.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up notification service: {e}")
            try:
                await db.close()
            except Exception as e:
                logger.warning(f"Error closing database on cleanup: {e}")

        try:
            self.page.run_task(cleanup_all)
        except RuntimeError as e:
            # Page may be closing or event loop unavailable - expected during shutdown
            logger.debug(f"Could not schedule cleanup (page closing): {e}")

    async def _init_auth(self) -> None:
        """Initialize authentication and show unlock dialog if needed."""
        if self.auth_ctrl is None:
            return

        await self.auth_ctrl.initialize()

        # Set up callback for when app is unlocked
        async def on_unlocked() -> None:
            # Reload data with decryption enabled - use async version
            # This emits REFRESH_UI which triggers UI rebuild with fresh Task objects
            await self.service.reload_state_async()
            # Also rebuild sidebar in case project names were encrypted
            self.rebuild_sidebar()
            self.page.update()

        self.auth_ctrl.set_unlock_callback(on_unlocked)

        # Show unlock dialog if app is locked
        if self.auth_ctrl.needs_unlock:
            self.auth_ctrl.show_unlock_dialog(allow_cancel=True)

    def _on_refresh_ui(self, data: Any) -> None:
        """Handle UI refresh events."""
        async def _refresh() -> None:
            # Always refresh state.tasks from DB so calendar has fresh data
            await self.service.refresh_state_tasks()
            self.tasks_view.refresh()
            # Also refresh calendar view if it's currently displayed
            if self.state.selected_nav == NavItem.CALENDAR:
                self.update_content()
            self.page.update()

        self.page.run_task(_refresh)

    def _on_calendar_update(self) -> None:
        """Handle calendar week navigation."""
        self.update_content()
        self.page.update()

    def _on_sidebar_rebuild(self, data: Any) -> None:
        """Handle sidebar rebuild events."""
        self.rebuild_sidebar()

    def _on_data_reset(self, data: Any) -> None:
        """Handle data reset events."""
        self.rebuild_sidebar()
        self.nav_manager.navigate_to(PageType.TASKS)  # EDITED - Use enum
        self.tasks_view.refresh()

    def _on_project_or_task_changed(self, data: Any) -> None:
        """Handle project color changes or task postponements - refresh calendar/stats if visible."""
        if self.state.selected_nav == NavItem.CALENDAR or self.state.current_page == PageType.STATS:
            self.update_content()
            self.page.update()

    def _on_language_changed(self, data: Any) -> None:
        """Handle language changes - update all translatable UI text."""
        # Update navigation items
        self.nav_inbox.title.value = t("inbox")
        self.nav_today.title.value = t("today")
        self.nav_calendar.title.value = t("calendar")
        self.nav_upcoming.title.value = t("upcoming")
        self.nav_projects.title.value = t("projects")

        # Update task view translatable text
        self.tasks_view.update_translations()

        # Update settings menu items
        self.settings_menu.items = self._get_settings_items()

        # Refresh the current view to update any other translatable text
        self.update_content()
        self.page.update()

    def _on_notification_tapped(self, data: Any) -> None:
        """Handle notification tap - navigate to task and show stats."""
        if data is None:
            return

        task_id = data.get("task_id") if isinstance(data, dict) else None
        if task_id is None:
            return

        # Navigate to tasks view
        self.nav_manager.navigate_to(PageType.TASKS)

        # Find task and emit stats requested event for deep-linking
        task = self.state.get_task_by_id(task_id)
        if task is not None:
            event_bus.emit(AppEvent.TASK_STATS_REQUESTED, task)

    def _create_controller(self) -> None:
        """Create UIController for navigation utilities.

        Task actions are now handled by TaskActionHandler via EventBus.
        UIController is kept for navigation and project utilities.
        """
        self.ctrl = UIController(
            page=self.page,
            state=self.state,
            nav_manager=self.nav_manager,
        )

        # Update nav_manager with project buttons
        self.nav_manager.set_project_btns(self.project_btns)

    def rebuild_sidebar(self) -> None:
        """Rebuild the sidebar with updated project list."""
        self.project_btns.clear()
        self.projects_items.controls.clear()
        for p in self.state.projects:
            btn = ProjectSidebarItem(p, self.nav_manager.toggle_project)
            self.project_btns[p.id] = btn
            self.projects_items.controls.append(btn)
        # Update scroll/height based on project count
        num_projects = len(self.state.projects)
        self.projects_items.scroll = ft.ScrollMode.AUTO if num_projects > 5 else None
        self.projects_items.height = 200 if num_projects > 5 else None
        self.nav_manager.set_project_btns(self.project_btns)
        self.event_bus.emit(AppEvent.PROJECT_UPDATED)

    def _on_timer_stop(self, e: ft.ControlEvent) -> None:
        """Handle timer stop button click - delegates to timer controller."""
        self.timer_ctrl.on_timer_stop(e)

    def update_content(self) -> None:
        """Update the main content area based on current state."""
        if self.state.current_page == PageType.PROFILE:
            self.page_content.content = self.profile_page.build()
        elif self.state.current_page == PageType.HELP:
            self.page_content.content = self.help_page.build()
        elif self.state.current_page == PageType.FEEDBACK:
            self.page_content.content = self.feedback_page.build()
        elif self.state.current_page == PageType.STATS:
            self.page_content.content = self.stats_page.build()
        elif self.state.current_page == PageType.TIME_ENTRIES:
            self.page_content.content = self.time_entries_view.build()
        elif self.state.selected_nav == NavItem.CALENDAR:
            # Refresh state.tasks before building calendar to ensure fresh data
            self.page.run_task(self._refresh_state_and_build_calendar)
            return
        else:
            self.page_content.content = self.tasks_view.build()

    async def _refresh_state_and_build_calendar(self) -> None:
        """Refresh state.tasks from DB and build calendar view."""
        await self.service.refresh_state_tasks()
        self.page_content.content = self.calendar_view.build()
        self.page.update()

    def _on_profile_click(self, e: ft.ControlEvent) -> None:
        """Handle profile menu item click."""
        self.nav_manager.navigate_to(PageType.PROFILE)

    def _on_encryption_click(self, e: ft.ControlEvent) -> None:
        """Handle encryption settings menu item click."""
        if self.auth_ctrl:
            self.auth_ctrl.show_encryption_settings()

    def _on_help_click(self, e: ft.ControlEvent) -> None:
        """Handle help menu item click."""
        self.nav_manager.navigate_to(PageType.HELP)

    def _on_stats_click(self, e: ft.ControlEvent) -> None:
        """Handle stats menu item click."""
        self.nav_manager.navigate_to(PageType.STATS)

    def _get_settings_items(self) -> list:
        """Get the settings menu items."""
        items = [
            ft.PopupMenuItem(
                content=t("profile"),
                icon=ft.Icons.PERSON,
                on_click=self._on_profile_click,
            ),
            ft.PopupMenuItem(
                content=t("menu_stats"),
                icon=ft.Icons.BAR_CHART,
                on_click=self._on_stats_click,
            ),
            ft.PopupMenuItem(
                content=t("menu_encryption"),
                icon=ft.Icons.LOCK,
                on_click=self._on_encryption_click,
            ),
            ft.PopupMenuItem(
                content=t("menu_help"),
                icon=ft.Icons.HELP_OUTLINE,
                on_click=self._on_help_click,
            )
        ]

        if len(self.state.selected_projects) == 1:
            project = self.state.get_project_by_id(
                list(self.state.selected_projects)[0]
            )
            if project:
                items.extend([
                    ft.PopupMenuItem(),
                    ft.PopupMenuItem(
                        content=f"{t('edit')} '{project.name}'",
                        icon=ft.Icons.EDIT,
                        on_click=lambda e, p=project: self.project_dialogs.open(p),
                    ),
                ])

        items.extend([
            ft.PopupMenuItem(),
            ft.PopupMenuItem(content=t("menu_logout"), icon=ft.Icons.LOGOUT),
        ])

        return items

    def _on_add_project_click(self, e: ft.ControlEvent) -> None:
        """Handle add project button click."""
        self.project_dialogs.open()

    def _build_layout(self) -> None:
        """Build the main application layout."""
        self._build_nav_items()
        self._build_projects_section()
        self._build_nav_content()
        self._build_drawer_and_sidebar()
        self._build_header()
        self._build_main_area()
        self._finalize_navigation_wiring()
        self._assemble_layout()
        self._show_pending_errors()

    def _build_nav_items(self) -> None:
        """Build navigation list tiles."""
        self.nav_inbox = ft.ListTile(
            leading=ft.Icon(ft.Icons.INBOX),
            title=ft.Text(t("inbox"), size=FONT_SIZE_LG),
            selected_color=COLORS["accent"],
            on_click=self.nav_handler.on_inbox_click,
        )

        self.nav_today = ft.ListTile(
            leading=ft.Icon(ft.Icons.TODAY),
            title=ft.Text(t("today"), size=FONT_SIZE_LG),
            selected=True,
            selected_color=COLORS["accent"],
            on_click=self.nav_handler.on_today_click,
        )

        self.nav_calendar = ft.ListTile(
            leading=ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK),
            title=ft.Text(t("calendar"), size=FONT_SIZE_LG),
            selected_color=COLORS["accent"],
            on_click=self.nav_handler.on_calendar_click,
        )

        self.nav_upcoming = ft.ListTile(
            leading=ft.Icon(ft.Icons.UPCOMING),
            title=ft.Text(t("upcoming"), size=FONT_SIZE_LG),
            selected_color=COLORS["accent"],
            on_click=self.nav_handler.on_upcoming_click,
        )

    def _build_projects_section(self) -> None:
        """Build the projects navigation section."""
        # Arrow kept for nav_manager compatibility but hidden
        self.projects_arrow = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_DOWN, size=20, color="grey", visible=False
        )

        add_project_btn = ft.Container(
            content=ft.Text("➕", size=14),
            padding=5,
            border_radius=5,
            on_click=self._on_add_project_click,
            tooltip="Create new project",
        )

        self.nav_projects = ft.ListTile(
            leading=ft.Icon(ft.Icons.FOLDER_OUTLINED),
            title=ft.Text(t("projects"), size=FONT_SIZE_LG),
            selected_color=COLORS["accent"],
            trailing=add_project_btn,
        )

        # Always visible, scrollable if >5 projects
        project_controls = [self.project_btns[p.id] for p in self.state.projects]
        self.projects_items = ft.Column(
            visible=True,
            spacing=0,
            controls=project_controls,
            scroll=ft.ScrollMode.AUTO if len(project_controls) > 5 else None,
            height=200 if len(project_controls) > 5 else None,  # ~5 items height
        )

    def _build_nav_content(self) -> None:
        """Build the navigation content column."""
        self.nav_content = ft.Column(
            controls=[
                ft.Text("Trebnic", size=20, weight="bold"),
                ft.Divider(color="grey"),
                self.nav_inbox,
                self.nav_today,
                self.nav_upcoming,
                self.nav_calendar,
                ft.Divider(color="grey"),
                self.nav_projects,
                self.projects_items,
            ]
        )

    def _build_drawer_and_sidebar(self) -> None:
        """Build the navigation drawer and sidebar."""
        self.drawer = ft.NavigationDrawer(
            bgcolor=COLORS["sidebar"], controls=[]
        )
        self.page.drawer = self.drawer

        self.sidebar = ft.Container(
            width=250,
            bgcolor=COLORS["sidebar"],
            padding=20,
            content=self.nav_content,
            visible=False,
        )

        self.menu_btn = ft.IconButton(
            icon=ft.Icons.MENU,
            icon_color=COLORS["accent"],
            on_click=self.nav_handler.on_menu_click,
            visible=True,
        )

    def _build_header(self) -> None:
        """Build the header row with menu, timer, and settings."""
        self.settings_menu = ft.PopupMenuButton(
            icon=ft.Icons.SETTINGS, items=self._get_settings_items()
        )

        self.header = ft.Row(
            controls=[
                self.menu_btn,
                self.timer_widget,
                ft.Container(expand=True),
                self.settings_menu,
            ]
        )

    def _build_main_area(self) -> None:
        """Build the main content area."""
        self.page_content = ft.Container(expand=True)

        self.main_area = ft.Container(
            expand=True,
            bgcolor=COLORS["bg"],
            alignment=ft.Alignment(-1, -1),
            padding=ft.Padding.only(left=20, right=20, top=20, bottom=20),
            content=ft.Column(
                alignment=ft.MainAxisAlignment.START,
                controls=[
                    self.header,
                    ft.Divider(height=30, color="transparent"),
                    self.page_content,
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        )

    def _finalize_navigation_wiring(self) -> None:
        """Wire navigation manager with all built components.""" 
        nav_items = {
            NavItem.INBOX: self.nav_inbox,
            NavItem.TODAY: self.nav_today,
            NavItem.CALENDAR: self.nav_calendar,
            NavItem.UPCOMING: self.nav_upcoming,
            NavItem.PROJECTS: self.nav_projects,
        }

        self.nav_manager.wire(
            nav_items=nav_items,
            project_btns=self.project_btns,
            projects_items=self.projects_items,
            projects_arrow=self.projects_arrow,
            drawer=self.drawer,
            sidebar=self.sidebar,
            menu_btn=self.menu_btn,
            nav_content=self.nav_content,
            settings_menu=self.settings_menu,
            on_content_update=self.update_content,
            on_refresh=self.tasks_view.refresh,
            get_settings_items=self._get_settings_items,
        )

    def _assemble_layout(self) -> None:
        """Assemble the final layout and add to page."""
        main_row = ft.Row(
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=0,
            controls=[self.sidebar, self.main_area],
        )

        self.page.on_resized = self._handle_resize
        self.page.add(main_row)
        self._handle_resize()
        self.update_content()
        self.tasks_view.refresh()

    def _show_pending_errors(self) -> None:
        """Show any pending errors that occurred during initialization."""
        if self._pending_error:
            self.snack.show(self._pending_error, COLORS["danger"])
            self._pending_error = None

    def _handle_resize(self, e: Optional[ft.ControlEvent] = None) -> None:
        """Handle window resize events."""
        is_mobile = (self.page.width or 800) < MOBILE_BREAKPOINT
        self.nav_manager.handle_resize(is_mobile)
        self.tasks_view.set_mobile(is_mobile)
        self.tasks_view.refresh()
        self.page.update()


def create_app(page: ft.Page) -> TrebnicApp:
    """Factory function to create the application."""
    return TrebnicApp(page)