import flet as ft 
import time 
import threading 
from typing import Dict, Optional, Any 

from config import ( 
    COLORS, 
    MOBILE_BREAKPOINT, 
    NAV_INBOX, 
    NAV_TODAY, 
    NAV_CALENDAR, 
    NAV_UPCOMING, 
    NAV_PROJECTS, 
    PAGE_TASKS, 
    PAGE_PROFILE, 
    PAGE_PREFERENCES, 
    ANIMATION_DELAY, 
) 
from events import EventBus, AppEvent, event_bus 
from services.logic import TaskService 
from services.timer import TimerService 
from models.entities import Task, AppState 
from ui.controller import UIController 
from ui.helpers import SnackService, format_timer_display 
from ui.components import ProjectSidebarItem, TimerWidget 
from ui.dialogs import TaskDialogs, ProjectDialogs 
from ui.pages import TasksView, CalendarView, ProfilePage, PreferencesPage 


class NavigationHandler: 
    """Handles navigation-related actions with named methods.""" 

    def __init__(self, app: "TrebnicApp") -> None: 
        self.app = app 

    def on_inbox_click(self, e: ft.ControlEvent) -> None: 
        self.app.select_nav(NAV_INBOX) 

    def on_today_click(self, e: ft.ControlEvent) -> None: 
        self.app.select_nav(NAV_TODAY) 

    def on_calendar_click(self, e: ft.ControlEvent) -> None: 
        self.app.select_nav(NAV_CALENDAR) 

    def on_upcoming_click(self, e: ft.ControlEvent) -> None: 
        self.app.select_nav(NAV_UPCOMING) 

    def on_projects_toggle(self, e: ft.ControlEvent) -> None: 
        self.app.toggle_projects() 


class TrebnicApp: 
    """Main application class orchestrating the Trebnic task manager.""" 

    def __init__(self, page: ft.Page) -> None: 
        self.page = page 
        self.event_bus = event_bus 
        self._setup_page() 
        self._init_services() 
        self._init_ui_components() 
        self._subscribe_to_events() 
        self._wire_controller() 
        self._build_layout() 

    def _setup_page(self) -> None: 
        """Configure the Flet page settings.""" 
        self.page.theme_mode = ft.ThemeMode.DARK 
        self.page.padding = 0 

    def _init_services(self) -> None: 
        """Initialize application services.""" 
        self.state = TaskService.load_state() 
        self.service = TaskService(self.state) 
        self.snack = SnackService(self.page) 
        self.timer_svc = TimerService() 
        self.ctrl = UIController(self.page, self.state, self.service) 
        self.nav_handler = NavigationHandler(self) 

    def _init_ui_components(self) -> None: 
        """Initialize UI components.""" 
        self.project_btns: Dict[str, ProjectSidebarItem] = { 
            p["id"]: ProjectSidebarItem(p, self.ctrl) 
            for p in self.state.projects 
        } 

        self.tasks_view = TasksView( 
            self.page, self.state, self.service, self.ctrl, self.snack 
        ) 
        self.calendar_view = CalendarView(self.state) 

        self.profile_page = ProfilePage( 
            self.page, 
            self.state, 
            self.service, 
            self.snack, 
            self.navigate_to, 
            self.tasks_view.refresh, 
            self.rebuild_sidebar, 
        ) 

        self.prefs_page = PreferencesPage( 
            self.page, 
            self.state, 
            self.service, 
            self.snack, 
            self.navigate_to, 
            self.tasks_view, 
        ) 

        self.task_dialogs = TaskDialogs( 
            self.page, 
            self.state, 
            self.service, 
            self.snack, 
            self.tasks_view.refresh, 
        ) 

        self.project_dialogs = ProjectDialogs( 
            self.page, 
            self.state, 
            self.service, 
            self.snack, 
            self.tasks_view.refresh, 
            self.rebuild_sidebar, 
        ) 

        self.timer_widget = TimerWidget(self._on_timer_stop) 

    def _subscribe_to_events(self) -> None: 
        """Subscribe to application events.""" 
        self.event_bus.subscribe(AppEvent.REFRESH_UI, self._on_refresh_ui) 
        self.event_bus.subscribe(AppEvent.SIDEBAR_REBUILD, self._on_sidebar_rebuild) 

    def _on_refresh_ui(self, data: Any) -> None: 
        """Handle UI refresh events.""" 
        self.tasks_view.refresh() 

    def _on_sidebar_rebuild(self, data: Any) -> None: 
        """Handle sidebar rebuild events.""" 
        self.rebuild_sidebar() 

    def _wire_controller(self) -> None: 
        """Wire up the UI controller callbacks.""" 
        self.ctrl.wire( 
            update_nav=self.update_nav, 
            refresh=self.tasks_view.refresh, 
            show_snack=self.snack.show, 
            delete_task=self._delete_task, 
            duplicate_task=self._duplicate_task, 
            rename_task=self.task_dialogs.rename, 
            assign_project=self.task_dialogs.assign_project, 
            date_picker=self.task_dialogs.date_picker, 
            start_timer=self._start_timer, 
            postpone_task=self._postpone_task, 
            recurrence=self.task_dialogs.recurrence, 
            stats=self.task_dialogs.stats, 
            notes=self.task_dialogs.notes, 
            update_content=self.update_content, 
        ) 

    def rebuild_sidebar(self) -> None: 
        """Rebuild the sidebar with updated project list.""" 
        self.project_btns.clear() 
        self.projects_items.controls.clear() 
        for p in self.state.projects: 
            self.project_btns[p["id"]] = ProjectSidebarItem(p, self.ctrl) 
            self.projects_items.controls.append(self.project_btns[p["id"]]) 
        self.event_bus.emit(AppEvent.PROJECT_UPDATED) 

    def _start_timer(self, task: Task) -> None: 
        """Start the timer for a task.""" 
        if self.timer_svc.running: 
            self.snack.show("Stop current timer first", COLORS["danger"]) 
            return 

        self.timer_svc.start(task, self.service.persist_task) 
        self.timer_widget.start(task.title) 
        self.event_bus.emit(AppEvent.TIMER_STARTED, task) 

        def tick() -> None: 
            while self.timer_svc.running: 
                time.sleep(1) 
                if self.timer_svc.running: 
                    self.timer_svc.tick() 
                    self.timer_widget.update_time(self.timer_svc.seconds) 
                    try: 
                        self.page.update() 
                    except Exception: 
                        break 

        threading.Thread(target=tick, daemon=True).start() 
        self.snack.show(f"Timer started for '{task.title}'") 

    def _on_timer_stop(self, e: ft.ControlEvent) -> None: 
        """Handle timer stop button click.""" 
        self._stop_timer() 

    def _stop_timer(self) -> None: 
        """Stop the current timer.""" 
        if not self.timer_svc.running: 
            return 

        task, elapsed = self.timer_svc.stop() 
        if task and elapsed > 0: 
            self.snack.show( 
                f"Added {format_timer_display(elapsed)} to '{task.title}'" 
            ) 
            self.tasks_view.refresh() 
            self.event_bus.emit(AppEvent.TIMER_STOPPED, {"task": task, "elapsed": elapsed}) 

        self.timer_widget.stop() 
        self.page.update() 

    def _delete_task(self, task: Task) -> None: 
        """Delete a task with animation delay.""" 
        title = task.title 
        self.service.delete_task(task) 

        def delayed() -> None: 
            time.sleep(ANIMATION_DELAY) 
            self.snack.show(f"'{title}' deleted", COLORS["danger"], update=False) 
            self.tasks_view.refresh() 
            self.event_bus.emit(AppEvent.TASK_DELETED, task) 

        threading.Thread(target=delayed, daemon=True).start() 

    def _duplicate_task(self, task: Task) -> None: 
        """Duplicate a task.""" 
        new_task = self.service.duplicate_task(task) 

        def delayed() -> None: 
            time.sleep(ANIMATION_DELAY) 
            self.snack.show( 
                f"Task duplicated as '{new_task.title}'", update=False 
            ) 
            self.tasks_view.refresh() 
            self.event_bus.emit(AppEvent.TASK_DUPLICATED, new_task) 

        threading.Thread(target=delayed, daemon=True).start() 

    def _postpone_task(self, task: Task) -> None: 
        """Postpone a task by one day.""" 
        new_date = self.service.postpone_task(task) 

        def delayed() -> None: 
            time.sleep(ANIMATION_DELAY) 
            self.snack.show( 
                f"'{task.title}' postponed to {new_date.strftime('%b %d')}", 
                update=False, 
            ) 
            self.tasks_view.refresh() 
            self.event_bus.emit(AppEvent.TASK_POSTPONED, task) 

        threading.Thread(target=delayed, daemon=True).start() 

    def navigate_to(self, page_name: str) -> None: 
        """Navigate to a specific page.""" 
        self.state.current_page = page_name 
        self.update_content() 
        self.event_bus.emit(AppEvent.NAV_CHANGED, page_name) 
        self.page.update() 

    def update_content(self) -> None: 
        """Update the main content area based on current state.""" 
        if self.state.current_page == PAGE_PROFILE: 
            self.page_content.content = self.profile_page.build() 
        elif self.state.current_page == PAGE_PREFERENCES: 
            self.page_content.content = self.prefs_page.build() 
        elif self.state.selected_nav == NAV_CALENDAR: 
            self.page_content.content = self.calendar_view.build() 
        else: 
            self.page_content.content = self.tasks_view.build() 

    def update_nav(self) -> None: 
        """Update navigation state and UI.""" 
        self.nav_inbox.selected = self.state.selected_nav == NAV_INBOX 
        self.nav_today.selected = self.state.selected_nav == NAV_TODAY 
        self.nav_calendar.selected = self.state.selected_nav == NAV_CALENDAR 
        self.nav_upcoming.selected = self.state.selected_nav == NAV_UPCOMING 
        self.nav_projects.selected = len(self.state.selected_projects) > 0 

        for pid, btn in self.project_btns.items(): 
            btn.set_selected(pid in self.state.selected_projects) 

        self.projects_items.visible = self.state.projects_expanded 
        self.projects_arrow.name = ( 
            ft.Icons.KEYBOARD_ARROW_DOWN 
            if self.state.projects_expanded 
            else ft.Icons.KEYBOARD_ARROW_RIGHT 
        ) 

        self.settings_menu.items = self._get_settings_items() 
        self.update_content() 
        self.tasks_view.refresh() 
        self.page.update() 

    def select_nav(self, name: str) -> None: 
        """Select a navigation item.""" 
        self.state.selected_nav = name 
        self.state.selected_projects.clear() 
        self.state.current_page = PAGE_TASKS 
        if self.state.is_mobile: 
            self.drawer.open = False 
        self.update_nav() 

    def toggle_projects(self) -> None: 
        """Toggle the projects section expansion.""" 
        self.state.projects_expanded = not self.state.projects_expanded 
        self.update_nav() 

    def _on_menu_click(self, e: ft.ControlEvent) -> None: 
        """Handle menu button click.""" 
        self.drawer.open = True 
        self.page.update() 

    def _on_profile_click(self, e: ft.ControlEvent) -> None: 
        """Handle profile menu item click.""" 
        self.navigate_to(PAGE_PROFILE) 

    def _on_preferences_click(self, e: ft.ControlEvent) -> None: 
        """Handle preferences menu item click.""" 
        self.navigate_to(PAGE_PREFERENCES) 

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
        ] 

        if len(self.state.selected_projects) == 1: 
            project = self.state.get_project_by_id( 
                list(self.state.selected_projects)[0] 
            ) 
            if project: 
                items.extend([ 
                    ft.PopupMenuItem(), 
                    ft.PopupMenuItem( 
                        text=f"Edit '{project['name']}'", 
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
        # Navigation items 
        self.nav_inbox = ft.ListTile( 
            leading=ft.Icon(ft.Icons.INBOX), 
            title=ft.Text("Inbox"), 
            selected_color=COLORS["accent"], 
            on_click=self.nav_handler.on_inbox_click, 
        ) 

        self.nav_today = ft.ListTile( 
            leading=ft.Icon(ft.Icons.TODAY), 
            title=ft.Text("Today"), 
            selected=True, 
            selected_color=COLORS["accent"], 
            on_click=self.nav_handler.on_today_click, 
        ) 

        self.nav_calendar = ft.ListTile( 
            leading=ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK), 
            title=ft.Text("Calendar"), 
            selected_color=COLORS["accent"], 
            on_click=self.nav_handler.on_calendar_click, 
        ) 

        self.nav_upcoming = ft.ListTile( 
            leading=ft.Icon(ft.Icons.UPCOMING), 
            title=ft.Text("Upcoming"), 
            selected_color=COLORS["accent"], 
            on_click=self.nav_handler.on_upcoming_click, 
        ) 

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
            title=ft.Text("Projects"), 
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
            controls=[self.project_btns[p["id"]] for p in self.state.projects], 
        ) 

        self.nav_content = ft.Column( 
            controls=[ 
                ft.Text("Trebnic", size=20, weight="bold"), 
                ft.Divider(color="grey"), 
                self.nav_inbox, 
                self.nav_today, 
                self.nav_calendar, 
                self.nav_upcoming, 
                self.nav_projects, 
                self.projects_items, 
            ] 
        ) 

        # Drawer and sidebar 
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
            on_click=self._on_menu_click, 
            visible=True, 
        ) 

        # Settings menu 
        self.settings_menu = ft.PopupMenuButton( 
            icon=ft.Icons.SETTINGS, items=self._get_settings_items() 
        ) 

        # Header 
        header = ft.Row( 
            controls=[ 
                self.menu_btn, 
                self.timer_widget, 
                ft.Container(expand=True), 
                self.settings_menu, 
            ] 
        ) 

        # Page content 
        self.page_content = ft.Container(expand=True) 

        # Main area 
        main_area = ft.Container( 
            expand=True, 
            bgcolor=COLORS["bg"], 
            alignment=ft.alignment.top_left, 
            padding=ft.padding.only(left=20, right=20, top=20, bottom=20), 
            content=ft.Column( 
                alignment=ft.MainAxisAlignment.START, 
                controls=[ 
                    header, 
                    ft.Divider(height=30, color="transparent"), 
                    self.page_content, 
                ], 
                scroll=ft.ScrollMode.AUTO, 
                expand=True, 
            ), 
        ) 

        # Main row 
        main_row = ft.Row( 
            expand=True, 
            vertical_alignment=ft.CrossAxisAlignment.STRETCH, 
            spacing=0, 
            controls=[self.sidebar, main_area], 
        ) 

        # Set up resize handler 
        self.page.on_resized = self._handle_resize 

        # Add main layout to page 
        self.page.add(main_row) 

        # Initial setup 
        self._handle_resize() 
        self.update_content() 
        self.tasks_view.refresh() 

    def _handle_resize(self, e: Optional[ft.ControlEvent] = None) -> None: 
        """Handle window resize events.""" 
        self.state.is_mobile = (self.page.width or 800) < MOBILE_BREAKPOINT 

        if self.state.is_mobile: 
            self.sidebar.visible = False 
            self.sidebar.content = None 
            self.menu_btn.visible = True 
            self.drawer.controls = [ 
                ft.Container(padding=20, content=self.nav_content) 
            ] 
        else: 
            self.drawer.controls = [] 
            self.sidebar.content = self.nav_content 
            self.sidebar.visible = True 
            self.menu_btn.visible = False 

        self.tasks_view.set_mobile(self.state.is_mobile) 
        self.tasks_view.refresh() 
        self.page.update() 


def create_app(page: ft.Page) -> TrebnicApp: 
    """Factory function to create the application.""" 
    return TrebnicApp(page) 