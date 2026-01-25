import flet as ft
import asyncio
import logging
from typing import Optional, Any, List

logger = logging.getLogger(__name__)

from config import (
    COLORS,
    MOBILE_BREAKPOINT,
    NavItem,
    PageType,
    ANIMATION_DELAY,
    FONT_SIZE_LG,
)
from database import db, DatabaseError
from events import event_bus, AppEvent, Subscription
from models.entities import Task
from ui.components import ProjectSidebarItem, TimerWidget
from ui.app_initializer import AppInitializer


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
        self._wire_controller()
        self._build_layout()

        # Recover any running timer from before app restart
        self.timer_ctrl.recover_timer(self.state)

        # Register cleanup on page close
        self.page.on_close = self._on_page_close

        # Initialize auth and check if unlock needed
        self.page.run_task(self._init_auth)

    def _extract_components(self) -> None:
        """Extract components from initializer for class-level access."""
        c = self._components
        self.state = c.state
        self.service = c.service
        self.snack = c.snack
        self.timer_svc = c.timer_svc
        self.ctrl = c.ctrl
        self.nav_manager = c.nav_manager
        self.nav_handler = c.nav_handler
        self.timer_ctrl = c.timer_ctrl
        self.auth_ctrl = c.auth_ctrl
        self.project_btns = c.project_btns
        self.tasks_view = c.tasks_view
        self.calendar_view = c.calendar_view
        self.time_entries_view = c.time_entries_view
        self.profile_page = c.profile_page
        self.prefs_page = c.prefs_page
        self.help_page = c.help_page
        self.task_dialogs = c.task_dialogs
        self.project_dialogs = c.project_dialogs
        self._pending_error = c.pending_error

    def _subscribe_to_events(self) -> None:
        """Subscribe to application events and track subscriptions for cleanup."""
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.REFRESH_UI, self._on_refresh_ui)
        )
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.SIDEBAR_REBUILD, self._on_sidebar_rebuild)
        )
        self._subscriptions.append(
            self.event_bus.subscribe(AppEvent.DATA_RESET, self._on_data_reset)
        )

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
        # Unsubscribe from all events
        self._unsubscribe_all()

        # Stop timer if running
        if self.timer_ctrl:
            self.timer_ctrl.cleanup()

        # Close database connection on the page's event loop
        async def close_db() -> None:
            try:
                await db.close()
            except Exception as e:
                logger.warning(f"Error closing database on cleanup: {e}")

        try:
            self.page.run_task(close_db)
        except Exception:
            pass  # Best effort on cleanup

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
        self.tasks_view.refresh()

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

    def _wire_controller(self) -> None:
        """Wire up the UI controller callbacks."""
        self.ctrl.wire(
            update_nav=self.nav_manager.update_nav,
            refresh=self.tasks_view.refresh,
            show_snack=self.snack.show,
            delete_task=self._delete_task,
            duplicate_task=self._duplicate_task,
            rename_task=self.task_dialogs.rename,
            assign_project=self.task_dialogs.assign_project,
            date_picker=self.task_dialogs.date_picker,
            start_timer=self.timer_ctrl.start_timer,
            postpone_task=self._postpone_task,
            recurrence=self.task_dialogs.recurrence,
            stats=self.task_dialogs.stats,
            notes=self.task_dialogs.notes,
            update_content=self.update_content,
            duration_completion=self.task_dialogs.duration_completion,
        )

    def rebuild_sidebar(self) -> None:
        """Rebuild the sidebar with updated project list."""
        self.project_btns.clear()
        self.projects_items.controls.clear()
        for p in self.state.projects:
            self.project_btns[p.id] = ProjectSidebarItem(p, self.ctrl)
            self.projects_items.controls.append(self.project_btns[p.id])
        self.nav_manager.set_project_btns(self.project_btns)
        self.event_bus.emit(AppEvent.PROJECT_UPDATED)

    def _on_timer_stop(self, e: ft.ControlEvent) -> None:
        """Handle timer stop button click - delegates to timer controller."""
        self.timer_ctrl.on_timer_stop(e)

    def _delete_task(self, task: Task) -> None:
        """Delete a task with animation delay and error handling.

        For recurring tasks, shows a dialog to choose between deleting
        just this occurrence or all recurring instances.
        """
        if task.recurrent:
            self.task_dialogs.delete_recurrence(
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
                await self.service.delete_task(task)
            except DatabaseError as e:
                self.snack.show(f"Failed to delete task: {e}", COLORS["danger"])
                return

            await asyncio.sleep(ANIMATION_DELAY)
            self.snack.show(f"'{title}' deleted", COLORS["danger"], update=False)
            self.tasks_view.refresh()
            self.event_bus.emit(AppEvent.TASK_DELETED, task)
            self.page.update()

        self.page.run_task(_delete)

    def _do_delete_all_recurring(self, task: Task) -> None:
        """Delete all recurring instances of a task."""
        async def _delete() -> None:
            title = task.title
            try:
                count = await self.service.delete_all_recurring_tasks(task)
            except DatabaseError as e:
                self.snack.show(f"Failed to delete tasks: {e}", COLORS["danger"])
                return

            await asyncio.sleep(ANIMATION_DELAY)
            msg = f"Deleted {count} '{title}' occurrence{'s' if count != 1 else ''}"
            self.snack.show(msg, COLORS["danger"], update=False)
            self.tasks_view.refresh()
            self.event_bus.emit(AppEvent.TASK_DELETED, task)
            self.page.update()

        self.page.run_task(_delete)

    def _duplicate_task(self, task: Task) -> None:
        """Duplicate a task with error handling."""
        async def _duplicate() -> None:
            try:
                new_task = await self.service.duplicate_task(task)
            except DatabaseError as e:
                self.snack.show(f"Failed to duplicate task: {e}", COLORS["danger"])
                return

            await asyncio.sleep(ANIMATION_DELAY)
            self.snack.show(f"Task duplicated as '{new_task.title}'", update=False)
            self.tasks_view.refresh()
            self.event_bus.emit(AppEvent.TASK_DUPLICATED, new_task)
            self.page.update()

        self.page.run_task(_duplicate)

    def _postpone_task(self, task: Task) -> None:
        """Postpone a task by one day with error handling."""
        async def _postpone() -> None:
            try:
                new_date = await self.service.postpone_task(task)
            except DatabaseError as e:
                self.snack.show(f"Failed to postpone task: {e}", COLORS["danger"])
                return

            await asyncio.sleep(ANIMATION_DELAY)
            self.snack.show(
                f"'{task.title}' postponed to {new_date.strftime('%b %d')}",
                update=False,
            )
            self.tasks_view.refresh()
            self.event_bus.emit(AppEvent.TASK_POSTPONED, task)
            self.page.update()

        self.page.run_task(_postpone)

    def update_content(self) -> None:
        """Update the main content area based on current state.""" 
        if self.state.current_page == PageType.PROFILE:
            self.page_content.content = self.profile_page.build()
        elif self.state.current_page == PageType.PREFERENCES:
            self.page_content.content = self.prefs_page.build()
        elif self.state.current_page == PageType.HELP:
            self.page_content.content = self.help_page.build()
        elif self.state.current_page == PageType.TIME_ENTRIES:
            self.page_content.content = self.time_entries_view.build()
        elif self.state.selected_nav == NavItem.CALENDAR:
            self.page_content.content = self.calendar_view.build()
        else:
            self.page_content.content = self.tasks_view.build()

    def _on_profile_click(self, e: ft.ControlEvent) -> None:
        """Handle profile menu item click."""
        self.nav_manager.navigate_to(PageType.PROFILE) 

    def _on_preferences_click(self, e: ft.ControlEvent) -> None:
        """Handle preferences menu item click."""
        self.nav_manager.navigate_to(PageType.PREFERENCES)

    def _on_encryption_click(self, e: ft.ControlEvent) -> None:
        """Handle encryption settings menu item click."""
        if self.auth_ctrl:
            self.auth_ctrl.show_encryption_settings()

    def _on_help_click(self, e: ft.ControlEvent) -> None: 
        """Handle help menu item click.""" 
        self.nav_manager.navigate_to(PageType.HELP)

    def _get_settings_items(self) -> list:
        """Get the settings menu items."""
        items = [
            ft.PopupMenuItem(
                text="Profile",
                icon=ft.Icons.PERSON,
                on_click=self._on_profile_click,
            ),
            ft.PopupMenuItem(
                text="Preferences",
                icon=ft.Icons.TUNE,
                on_click=self._on_preferences_click,
            ),
            ft.PopupMenuItem(
                text="Encryption",
                icon=ft.Icons.LOCK,
                on_click=self._on_encryption_click,
            ),
            ft.PopupMenuItem(
                text="Help & feedback",
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
                        text=f"Edit '{project.name}'",
                        icon=ft.Icons.EDIT,
                        on_click=lambda e, p=project: self.project_dialogs.open(p),
                    ),
                ])

        items.extend([
            ft.PopupMenuItem(),
            ft.PopupMenuItem(text="Logout", icon=ft.Icons.LOGOUT),
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
            title=ft.Text("Inbox", size=FONT_SIZE_LG),
            selected_color=COLORS["accent"],
            on_click=self.nav_handler.on_inbox_click,
        )

        self.nav_today = ft.ListTile(
            leading=ft.Icon(ft.Icons.TODAY),
            title=ft.Text("Today", size=FONT_SIZE_LG),
            selected=True,
            selected_color=COLORS["accent"],
            on_click=self.nav_handler.on_today_click,
        )

        self.nav_calendar = ft.ListTile(
            leading=ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK),
            title=ft.Text("Calendar", size=FONT_SIZE_LG),
            selected_color=COLORS["accent"],
            on_click=self.nav_handler.on_calendar_click,
        )

        self.nav_upcoming = ft.ListTile(
            leading=ft.Icon(ft.Icons.UPCOMING),
            title=ft.Text("Upcoming", size=FONT_SIZE_LG),
            selected_color=COLORS["accent"],
            on_click=self.nav_handler.on_upcoming_click,
        )

    def _build_projects_section(self) -> None:
        """Build the projects navigation section."""
        self.projects_arrow = ft.Icon(
            ft.Icons.KEYBOARD_ARROW_RIGHT, size=20, color="grey"
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
            title=ft.Text("Projects", size=FONT_SIZE_LG),
            selected_color=COLORS["accent"],
            trailing=ft.Row(
                [self.projects_arrow, add_project_btn],
                spacing=5,
                tight=True,
            ),
            on_click=self.nav_handler.on_projects_toggle,
        )

        self.projects_items = ft.Column(
            visible=False,
            spacing=0,
            controls=[self.project_btns[p.id] for p in self.state.projects],
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
            alignment=ft.alignment.top_left,
            padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
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