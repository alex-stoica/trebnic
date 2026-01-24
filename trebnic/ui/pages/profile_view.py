import flet as ft
from datetime import date
from typing import Callable 

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    DURATION_SLIDER_STEP,
    DURATION_SLIDER_MIN,
    DURATION_SLIDER_MAX,
    DIALOG_WIDTH_MD,
) 
from models.entities import AppState
from services.logic import TaskService
from ui.helpers import format_duration, accent_btn, danger_btn, SnackService
from ui.dialogs.base import open_dialog
from events import event_bus, AppEvent


class ProfilePage:
    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        service: TaskService,
        snack: SnackService,
        navigate: Callable[[str], None],
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self.snack = snack
        self.navigate = navigate

    def _open_reset_dialog(self, e: ft.ControlEvent) -> None: 
        def confirm(e: ft.ControlEvent) -> None:
            self.service.reset()
            close()
            event_bus.emit(AppEvent.DATA_RESET)
            self.snack.show("All data has been reset", COLORS["danger"])

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column(
                [ 
                    ft.Icon( 
                        ft.Icons.WARNING_AMBER_ROUNDED, 
                        size=48, 
                        color=COLORS["danger"], 
                    ), 
                    ft.Text( 
                        "This action cannot be undone!", 
                        weight="bold", 
                        color=COLORS["danger"], 
                        text_align=ft.TextAlign.CENTER, 
                    ), 
                    ft.Text( 
                        "All your tasks, projects, and settings will be " 
                        "permanently deleted.", 
                        text_align=ft.TextAlign.CENTER, 
                        color=COLORS["done_text"], 
                    ), 
                ], 
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=15,
            ), 
        ) 

        _, close = open_dialog(
            self.page, 
            "⚠️ Factory Reset", 
            content, 
            lambda c: [ 
                ft.TextButton("Cancel", on_click=c), 
                danger_btn("Reset everything", confirm), 
            ], 
        ) 

    def build(self) -> ft.Column:
        most_active = None
        if self.state.projects:
            most_active = max(
                self.state.projects, 
                key=lambda p: len([ 
                    t for t in self.state.done_tasks if t.project_id == p.id
                ]), 
                default=None, 
            ) 

        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK, 
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"], 
        ) 
        header = ft.Row([back_btn, ft.Text("Profile", size=24, weight="bold")])

        avatar_section = ft.Container(
            content=ft.Column(
                [ 
                    ft.Icon(ft.Icons.ACCOUNT_CIRCLE, size=64, color=COLORS["accent"]), 
                    ft.Text("User", size=18, weight="bold"), 
                ], 
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5,
            ), 
            alignment=ft.alignment.center,
            padding=10,
        ) 

        account_age_card = ft.Container(
            content=ft.Row(
                [ 
                    ft.Icon(ft.Icons.CALENDAR_TODAY, color=COLORS["accent"], size=18), 
                    ft.Column( 
                        [ 
                            ft.Text("Account Age", weight="bold", size=13), 
                            ft.Text( 
                                f"Since {date.today().strftime('%b %d, %Y')}", 
                                color=COLORS["done_text"], 
                                size=12, 
                            ), 
                        ], 
                        spacing=2, 
                        expand=True, 
                    ), 
                ], 
                spacing=10,
            ), 
            bgcolor=COLORS["card"],
            padding=12,
            border_radius=BORDER_RADIUS,
        ) 

        tasks_completed_card = ft.Container(
            content=ft.Row(
                [ 
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=COLORS["green"], size=18), 
                    ft.Column( 
                        [ 
                            ft.Text("Tasks Completed", weight="bold", size=13), 
                            ft.Text( 
                                f"{len(self.state.done_tasks)} total", 
                                color=COLORS["done_text"], 
                                size=12, 
                            ), 
                        ], 
                        spacing=2, 
                        expand=True, 
                    ), 
                ], 
                spacing=10,
            ), 
            bgcolor=COLORS["card"],
            padding=12,
            border_radius=BORDER_RADIUS,
        ) 

        most_active_name = most_active.name if most_active else "None" 
        most_active_card = ft.Container(
            content=ft.Row(
                [ 
                    ft.Icon(ft.Icons.FOLDER, color=COLORS["blue"], size=18), 
                    ft.Column( 
                        [ 
                            ft.Text("Most Active", weight="bold", size=13), 
                            ft.Text( 
                                most_active_name, 
                                color=COLORS["done_text"], 
                                size=12, 
                            ), 
                        ], 
                        spacing=2, 
                        expand=True, 
                    ), 
                ], 
                spacing=10,
            ), 
            bgcolor=COLORS["card"],
            padding=12,
            border_radius=BORDER_RADIUS,
        ) 

        reset_btn_container = ft.Container(
            content=danger_btn( 
                "Factory Reset", 
                self._open_reset_dialog, 
                icon=ft.Icons.RESTORE, 
            ), 
            alignment=ft.alignment.center,
        ) 

        return ft.Column(
            [ 
                header, 
                avatar_section, 
                ft.Divider(height=10, color=COLORS["border"]), 
                account_age_card, 
                tasks_completed_card, 
                most_active_card, 
                ft.Divider(height=15, color="transparent"), 
                reset_btn_container, 
            ], 
            spacing=8,
        ) 


class PreferencesPage:
    def __init__(
        self, 
        page: ft.Page, 
        state: AppState, 
        service: TaskService, 
        snack: SnackService, 
        navigate: Callable[[str], None], 
        tasks_view, 
    ) -> None: 
        self.page = page
        self.state = state
        self.service = service
        self.snack = snack
        self.navigate = navigate
        self.tasks_view = tasks_view

    def build(self) -> ft.Column:
        label = ft.Text(
            format_duration(self.state.default_estimated_minutes), 
            size=16, 
            weight="bold", 
        ) 

        def on_slider(e: ft.ControlEvent) -> None: 
            label.value = format_duration(int(e.control.value) * DURATION_SLIDER_STEP)
            self.page.update()

        slider = ft.Slider(
            min=DURATION_SLIDER_MIN, 
            max=DURATION_SLIDER_MAX, 
            divisions=DURATION_SLIDER_MAX - DURATION_SLIDER_MIN, 
            value=self.state.default_estimated_minutes // DURATION_SLIDER_STEP, 
            label="{value}", 
            on_change=on_slider, 
        ) 

        email_cb = ft.Checkbox(
            value=self.state.email_weekly_stats, 
            label="Email weekly stats", 
        ) 

        def save(e: ft.ControlEvent) -> None: 
            self.state.default_estimated_minutes = (
                int(slider.value) * DURATION_SLIDER_STEP 
            ) 
            self.state.email_weekly_stats = email_cb.value
            self.service.save_settings()
            self.tasks_view.pending_details["estimated_minutes"] = (
                self.state.default_estimated_minutes 
            ) 
            self.tasks_view.details_btn.content.controls[1].value = "Add details"
            self.snack.show("Preferences saved")
            self.navigate(PageType.TASKS)

        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK, 
            on_click=lambda e: self.navigate(PageType.TASKS), 
            icon_color=COLORS["accent"], 
        ) 

        header = ft.Row([back_btn, ft.Text("Preferences", size=24, weight="bold")])

        time_card = ft.Container(
            content=ft.Column(
                [ 
                    ft.Text("Default estimated time", weight="bold", size=14), 
                    ft.Row([ft.Icon(ft.Icons.TIMER, size=18), label], spacing=8), 
                    slider, 
                    ft.Text( 
                        "5 min - 8 hrs 20 min", 
                        size=11, 
                        color=COLORS["done_text"], 
                    ), 
                ], 
                spacing=12,
            ), 
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        ) 

        notifications_card = ft.Container(
            content=ft.Column(
                [ 
                    ft.Text("Notifications", weight="bold", size=14), 
                    email_cb, 
                ], 
                spacing=12,
            ), 
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        ) 

        save_btn_container = ft.Container(
            content=accent_btn("Save", save), 
            alignment=ft.alignment.center, 
        ) 

        return ft.Column(
            [ 
                header, 
                ft.Divider(height=30, color="transparent"), 
                time_card, 
                notifications_card, 
                ft.Divider(height=20, color="transparent"), 
                save_btn_container, 
            ], 
            spacing=15,
        )