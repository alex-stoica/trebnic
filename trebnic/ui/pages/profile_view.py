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
        navigate: Callable[[PageType], None],
        tasks_view=None,
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self.snack = snack
        self.navigate = navigate
        self.tasks_view = tasks_view
        self._avatar_path: str | None = None
        self._avatar_icon: ft.Icon | None = None
        self._avatar_image: ft.Image | None = None
        self._file_picker = ft.FilePicker(on_result=self._on_file_picked)
        self.page.overlay.append(self._file_picker)

    def set_tasks_view(self, tasks_view) -> None:
        """Set the tasks view reference (for updating pending details on save)."""
        self.tasks_view = tasks_view

    def _on_avatar_click(self, e: ft.ControlEvent) -> None:
        """Open file picker to select avatar image."""
        self._file_picker.pick_files(
            allowed_extensions=["png", "jpg", "jpeg", "gif", "webp"],
            dialog_title="Select profile photo",
        )

    def _on_file_picked(self, e: ft.FilePickerResultEvent) -> None:
        """Handle file picker result."""
        if e.files and len(e.files) > 0:
            self._avatar_path = e.files[0].path
            if self._avatar_icon and self._avatar_image:
                self._avatar_icon.visible = False
                self._avatar_image.src = self._avatar_path
                self._avatar_image.visible = True
                self.page.update()

    def _open_reset_dialog(self, e: ft.ControlEvent) -> None:
        def confirm(e: ft.ControlEvent) -> None:
            async def _reset() -> None:
                await self.service.reset()
                close()
                event_bus.emit(AppEvent.DATA_RESET)
                self.snack.show("All data has been reset", COLORS["danger"])
            self.page.run_task(_reset)

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

    def _build_preferences_section(self) -> ft.Container:
        """Build the preferences section with estimated time and notifications."""
        label = ft.Text(
            format_duration(self.state.default_estimated_minutes),
            size=14,
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
            async def _save() -> None:
                self.state.default_estimated_minutes = (
                    int(slider.value) * DURATION_SLIDER_STEP
                )
                self.state.email_weekly_stats = email_cb.value
                await self.service.save_settings()
                if self.tasks_view:
                    self.tasks_view.pending_details["estimated_minutes"] = (
                        self.state.default_estimated_minutes
                    )
                    self.tasks_view.details_btn.content.controls[1].value = "Add details"
                self.snack.show("Preferences saved")
            self.page.run_task(_save)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text("Preferences", weight="bold", size=16),
                    ft.Divider(height=10, color=COLORS["border"]),
                    ft.Text("Default estimated time", size=13),
                    ft.Row([ft.Icon(ft.Icons.TIMER, size=18), label], spacing=8),
                    slider,
                    ft.Text(
                        "5 min - 8 hrs 20 min",
                        size=11,
                        color=COLORS["done_text"],
                    ),
                    ft.Divider(height=10, color="transparent"),
                    ft.Text("Notifications", size=13),
                    email_cb,
                    ft.Divider(height=10, color="transparent"),
                    ft.Container(
                        content=accent_btn("Save preferences", save),
                        alignment=ft.alignment.center,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=COLORS["card"],
            padding=15,
            border_radius=BORDER_RADIUS,
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

        self._avatar_icon = ft.Icon(
            ft.Icons.ACCOUNT_CIRCLE,
            size=64,
            color=COLORS["accent"],
            visible=self._avatar_path is None,
        )
        self._avatar_image = ft.Image(
            src=self._avatar_path or "",
            width=64,
            height=64,
            fit=ft.ImageFit.COVER,
            border_radius=32,
            visible=self._avatar_path is not None,
        )
        avatar_section = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Stack(
                            [
                                self._avatar_icon,
                                self._avatar_image,
                            ],
                        ),
                        on_click=self._on_avatar_click,
                        ink=True,
                        border_radius=32,
                    ),
                    ft.Text("User", size=18, weight="bold"),
                    ft.Text(
                        "Tap photo to change",
                        size=11,
                        color=COLORS["done_text"],
                    ),
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
                            ft.Text("Account age", weight="bold", size=13),
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
                            ft.Text("Tasks completed", weight="bold", size=13),
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
                            ft.Text("Most active project", weight="bold", size=13),
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

        preferences_section = self._build_preferences_section()

        reset_btn_container = ft.Container(
            content=danger_btn(
                "Factory reset",
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
                preferences_section,
                ft.Divider(height=15, color="transparent"),
                reset_btn_container,
            ],
            spacing=8,
        )