import sys  
import os 
_app_dir = os.path.dirname(os.path.abspath(__file__))  
if _app_dir not in sys.path:  
    sys.path.insert(0, _app_dir)

import flet as ft 
import time 
import threading 

from config import (COLORS, MOBILE_BREAKPOINT, NAV_INBOX, NAV_TODAY, NAV_CALENDAR, NAV_UPCOMING,
                    PAGE_TASKS, PAGE_PROFILE, PAGE_PREFERENCES, ANIMATION_DELAY)
from services.logic import TaskService
from services.timer import TimerService
from ui.controller import UIController
from ui.helpers import SnackService, format_timer_display
from ui.components import ProjectSidebarItem, TimerWidget
from ui.dialogs import TaskDialogs, ProjectDialogs
from ui.pages import TasksView, CalendarView, ProfilePage, PreferencesPage


def main(page: ft.Page):
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    state = TaskService.load_state()
    service = TaskService(state)
    snack = SnackService(page)
    ctrl = UIController(page, state, service)
    timer_svc = TimerService()

    project_btns = {p["id"]: ProjectSidebarItem(p, ctrl) for p in state.projects}

    def rebuild_sidebar():
        project_btns.clear()
        projects_items.controls.clear()
        for p in state.projects:
            project_btns[p["id"]] = ProjectSidebarItem(p, ctrl)
            projects_items.controls.append(project_btns[p["id"]])

    tasks_view = TasksView(page, state, service, ctrl, snack)
    calendar_view = CalendarView(state)
    profile_page = ProfilePage(page, state, service, snack, lambda p: navigate_to(p), tasks_view.refresh, rebuild_sidebar)
    prefs_page = PreferencesPage(page, state, service, snack, lambda p: navigate_to(p), tasks_view)
    task_dialogs = TaskDialogs(page, state, service, snack, tasks_view.refresh)
    project_dialogs = ProjectDialogs(page, state, snack, tasks_view.refresh, rebuild_sidebar)

    timer_widget = TimerWidget(lambda e: stop_timer())

    def start_timer(task):
        if timer_svc.running:
            snack.show("Stop current timer first", COLORS["danger"])
            return
        timer_svc.start(task, service.persist_task)
        timer_widget.start(task.title)
        def tick():
            while timer_svc.running:
                time.sleep(1)
                if timer_svc.running:
                    timer_svc.tick()
                    timer_widget.update_time(timer_svc.seconds)
                    try:
                        page.update()
                    except:
                        break
        threading.Thread(target=tick, daemon=True).start()
        snack.show(f"Timer started for '{task.title}'")

    def stop_timer():
        if not timer_svc.running:
            return
        task, elapsed = timer_svc.stop()
        if task and elapsed > 0:
            snack.show(f"Added {format_timer_display(elapsed)} to '{task.title}'")
            tasks_view.refresh()
        timer_widget.stop()
        page.update()

    def delete_task(task):
        title = task.title
        service.delete_task(task)
        def delayed():
            time.sleep(ANIMATION_DELAY)
            snack.show(f"'{title}' deleted", COLORS["danger"], update=False)
            tasks_view.refresh()
        threading.Thread(target=delayed, daemon=True).start()

    def duplicate_task(task):
        new_task = service.duplicate_task(task)
        def delayed():
            time.sleep(ANIMATION_DELAY)
            snack.show(f"Task duplicated as '{new_task.title}'", update=False)
            tasks_view.refresh()
        threading.Thread(target=delayed, daemon=True).start()

    def postpone_task(task):
        new_date = service.postpone_task(task)
        def delayed():
            time.sleep(ANIMATION_DELAY)
            snack.show(f"'{task.title}' postponed to {new_date.strftime('%b %d')}", update=False)
            tasks_view.refresh()
        threading.Thread(target=delayed, daemon=True).start()

    page_content = ft.Container(expand=True)

    def navigate_to(page_name: str):
        state.current_page = page_name
        update_content()
        page.update()

    def update_content():
        if state.current_page == PAGE_PROFILE:
            page_content.content = profile_page.build()
        elif state.current_page == PAGE_PREFERENCES:
            page_content.content = prefs_page.build()
        elif state.selected_nav == NAV_CALENDAR:
            page_content.content = calendar_view.build()
        else:
            page_content.content = tasks_view.build()

    def update_nav():
        nav_inbox.selected = state.selected_nav == NAV_INBOX
        nav_today.selected = state.selected_nav == NAV_TODAY
        nav_calendar.selected = state.selected_nav == NAV_CALENDAR
        nav_upcoming.selected = state.selected_nav == NAV_UPCOMING
        nav_projects.selected = len(state.selected_projects) > 0
        for pid, btn in project_btns.items():
            btn.set_selected(pid in state.selected_projects)
        projects_items.visible = state.projects_expanded
        projects_arrow.name = ft.Icons.KEYBOARD_ARROW_DOWN if state.projects_expanded else ft.Icons.KEYBOARD_ARROW_RIGHT
        settings_menu.items = get_settings_items()
        update_content()
        tasks_view.refresh()
        page.update()

    def select_nav(name):
        state.selected_nav = name
        state.selected_projects.clear()
        state.current_page = PAGE_TASKS
        if state.is_mobile:
            drawer.open = False
        update_nav()

    def toggle_projects(e):
        state.projects_expanded = not state.projects_expanded
        update_nav()

    ctrl.wire(update_nav=update_nav, refresh=tasks_view.refresh, show_snack=snack.show,
              delete_task=delete_task, duplicate_task=duplicate_task, rename_task=task_dialogs.rename,
              assign_project=task_dialogs.assign_project, date_picker=task_dialogs.date_picker,
              start_timer=start_timer, postpone_task=postpone_task, recurrence=task_dialogs.recurrence,
              stats=task_dialogs.stats, notes=task_dialogs.notes, update_content=update_content)

    nav_inbox = ft.ListTile(leading=ft.Icon(ft.Icons.INBOX), title=ft.Text("Inbox"), selected_color=COLORS["accent"], on_click=lambda e: select_nav(NAV_INBOX))
    nav_today = ft.ListTile(leading=ft.Icon(ft.Icons.TODAY), title=ft.Text("Today"), selected=True, selected_color=COLORS["accent"], on_click=lambda e: select_nav(NAV_TODAY))
    nav_calendar = ft.ListTile(leading=ft.Icon(ft.Icons.CALENDAR_VIEW_WEEK), title=ft.Text("Calendar"), selected_color=COLORS["accent"], on_click=lambda e: select_nav(NAV_CALENDAR))
    nav_upcoming = ft.ListTile(leading=ft.Icon(ft.Icons.UPCOMING), title=ft.Text("Upcoming"), selected_color=COLORS["accent"], on_click=lambda e: select_nav(NAV_UPCOMING))
    projects_arrow = ft.Icon(ft.Icons.KEYBOARD_ARROW_RIGHT, size=20, color="grey")
    add_project_btn = ft.Container(content=ft.Text("➕", size=14), padding=5, border_radius=5, on_click=lambda e: project_dialogs.open(), tooltip="Create new project")
    nav_projects = ft.ListTile(leading=ft.Icon(ft.Icons.FOLDER_OUTLINED), title=ft.Text("Projects"), selected_color=COLORS["accent"],
                               trailing=ft.Row([projects_arrow, add_project_btn], spacing=5, tight=True), on_click=toggle_projects)
    projects_items = ft.Column(visible=False, spacing=0, controls=[project_btns[p["id"]] for p in state.projects])

    nav_content = ft.Column(controls=[ft.Text("Trebnic", size=20, weight="bold"), ft.Divider(color="grey"),
                                      nav_inbox, nav_today, nav_calendar, nav_upcoming, nav_projects, projects_items])

    drawer = ft.NavigationDrawer(bgcolor=COLORS["sidebar"], controls=[])
    page.drawer = drawer
    sidebar = ft.Container(width=250, bgcolor=COLORS["sidebar"], padding=20, content=nav_content, visible=False)
    menu_btn = ft.IconButton(icon=ft.Icons.MENU, icon_color=COLORS["accent"], on_click=lambda e: setattr(drawer, "open", True) or page.update(), visible=True)

    def get_settings_items():
        items = [ft.PopupMenuItem(text="Profile", icon=ft.Icons.PERSON, on_click=lambda e: navigate_to(PAGE_PROFILE)),
                 ft.PopupMenuItem(text="Preferences", icon=ft.Icons.TUNE, on_click=lambda e: navigate_to(PAGE_PREFERENCES))]
        if len(state.selected_projects) == 1:
            project = state.get_project_by_id(list(state.selected_projects)[0])
            if project:
                items.extend([ft.PopupMenuItem(), ft.PopupMenuItem(text=f"Edit '{project['name']}'", icon=ft.Icons.EDIT, on_click=lambda e, p=project: project_dialogs.open(p))])
        items.extend([ft.PopupMenuItem(), ft.PopupMenuItem(text="Logout", icon=ft.Icons.LOGOUT)])
        return items

    settings_menu = ft.PopupMenuButton(icon=ft.Icons.SETTINGS, items=get_settings_items())
    header = ft.Row(controls=[menu_btn, timer_widget, ft.Container(expand=True), settings_menu])
    main_area = ft.Container(expand=True, bgcolor=COLORS["bg"], alignment=ft.alignment.top_left,
                             padding=ft.padding.only(left=20, right=20, top=20, bottom=20),
                             content=ft.Column(alignment=ft.MainAxisAlignment.START, controls=[header, ft.Divider(height=30, color="transparent"), page_content],
                                               scroll=ft.ScrollMode.AUTO, expand=True))
    main_row = ft.Row(expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH, spacing=0, controls=[sidebar, main_area])

    def handle_resize(e=None):
        state.is_mobile = (page.width or 800) < MOBILE_BREAKPOINT
        if state.is_mobile:
            sidebar.visible, sidebar.content, menu_btn.visible = False, None, True
            drawer.controls = [ft.Container(padding=20, content=nav_content)]
        else:
            drawer.controls, sidebar.content, sidebar.visible, menu_btn.visible = [], nav_content, True, False
        tasks_view.set_mobile(state.is_mobile)
        tasks_view.refresh()
        page.update()

    page.on_resized = handle_resize
    page.add(main_row)
    handle_resize()
    update_content()
    tasks_view.refresh()


ft.app(target=main)