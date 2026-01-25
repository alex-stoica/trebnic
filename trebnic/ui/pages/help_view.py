import flet as ft
from typing import Callable

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    FONT_SIZE_SM,
)


class HelpPage:
    def __init__(
        self,
        page: ft.Page,
        navigate: Callable[[PageType], None],
    ) -> None:
        self.page = page
        self.navigate = navigate

    def _section(self, title: str, content: list[ft.Control]) -> ft.Container:
        """Create a styled section container."""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(title, weight="bold", size=FONT_SIZE_SM),
                    *content,
                ],
                spacing=6,
            ),
        )

    def build(self) -> ft.Column:
        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"],
        )
        header = ft.Row([back_btn, ft.Text("How to Use Trebnic", size=24, weight="bold")])

        # Privacy-first intro
        intro_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([
                        ft.Icon(ft.Icons.SHIELD, color=COLORS["green"]),
                        ft.Text("Privacy-First Task Manager", weight="bold", size=16),
                    ], spacing=10),
                    ft.Text(
                        "Trebnic is built with your privacy at its core. All your data stays on your device - "
                        "we never collect, track, or share any of your information. No accounts, no cloud sync, "
                        "no analytics. Your tasks, your device, your privacy.",
                        size=FONT_SIZE_SM,
                    ),
                    ft.Container(height=5),
                    ft.Row([
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.WIFI_OFF, size=16, color=COLORS["done_text"]),
                                ft.Text("Works offline", size=12, color=COLORS["done_text"]),
                            ], spacing=5),
                        ),
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.LOCK, size=16, color=COLORS["done_text"]),
                                ft.Text("Optional encryption", size=12, color=COLORS["done_text"]),
                            ], spacing=5),
                        ),
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.VISIBILITY_OFF, size=16, color=COLORS["done_text"]),
                                ft.Text("No tracking", size=12, color=COLORS["done_text"]),
                            ], spacing=5),
                        ),
                    ], spacing=15, wrap=True),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        )

        # Tasks section
        tasks_section = self._section("Tasks", [
            ft.Text(
                "Tap the + button to create a new task. Tap a task to mark it complete. "
                "Swipe right to start the timer, swipe left to delete.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
            ft.Text(
                "Long-press or tap the menu icon for more options: edit title, set due date, "
                "configure recurrence, view time stats, or move to a different project.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
        ])

        # Projects section
        projects_section = self._section("Projects", [
            ft.Text(
                "Use the sidebar to organize tasks into projects. Tap a project to filter tasks. "
                "Create new projects from the sidebar menu. Each project can have its own icon and color.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
            ft.Text(
                "Project filtering combines with your current view. For example, selecting 'Today' in the "
                "navigation and then a project shows only today's tasks from that project. This lets you "
                "focus on what matters right now.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
        ])

        # Timer section - enhanced
        timer_section = self._section("Time Tracking", [
            ft.Text(
                "Track how much time you spend on each task. Start the timer by swiping right on a task "
                "or from the task menu.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
            ft.Text(
                "The active timer appears in the header showing elapsed time and task name. Tap the timer "
                "to stop it or switch to a different task. You can only have one timer running at a time.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
            ft.Text(
                "View your time history for any task from the task menu. All time entries are stored locally "
                "and can be used to understand how you spend your time.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
        ])

        # Recurrence section - enhanced
        recurrence_section = self._section("Recurring Tasks", [
            ft.Text(
                "Set tasks to repeat automatically. From the task menu, select 'Recurrence' to configure "
                "how often the task should repeat.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
            ft.Text(
                "Choose from daily, weekly, or monthly intervals. For example: every 2 days, every week, "
                "or every 3 months. You can also select specific days of the week for weekly recurrence.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
            ft.Text(
                "When you complete a recurring task, it automatically reschedules to the next occurrence. "
                "The next due date is calculated based on your recurrence settings, ensuring you never "
                "miss a repeated task.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
        ])

        # Calendar section
        calendar_section = self._section("Calendar View", [
            ft.Text(
                "View tasks organized by week. Swipe left or right to navigate between weeks. "
                "Tasks are shown on their due dates, helping you plan ahead.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
        ])

        # Security section - enhanced
        security_section = self._section("Security & Encryption", [
            ft.Text(
                "For extra privacy, enable encryption in Settings to protect sensitive data with a "
                "master password. Task titles, notes, and project names are encrypted using AES-256-GCM.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
            ft.Text(
                "Your master password never leaves your device and is never stored - only a verification "
                "hash is kept to confirm you entered the correct password. On supported devices, use "
                "fingerprint or face unlock for convenient access.",
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
            ),
        ])

        # How to use card containing all sections
        how_to_use_card = ft.Container(
            content=ft.Column(
                [
                    tasks_section,
                    ft.Divider(color=COLORS["border"]),
                    projects_section,
                    ft.Divider(color=COLORS["border"]),
                    timer_section,
                    ft.Divider(color=COLORS["border"]),
                    recurrence_section,
                    ft.Divider(color=COLORS["border"]),
                    calendar_section,
                    ft.Divider(color=COLORS["border"]),
                    security_section,
                ],
                spacing=12,
            ),
            bgcolor=COLORS["card"],
            padding=20,
            border_radius=BORDER_RADIUS,
        )

        # Link to Feedback page
        feedback_link = ft.Container(
            content=ft.TextButton(
                "Have feedback or want to support Trebnic?",
                icon=ft.Icons.FEEDBACK,
                on_click=lambda e: self.navigate(PageType.FEEDBACK),
            ),
            alignment=ft.alignment.center,
        )

        return ft.Column(
            [
                header,
                ft.Divider(height=20, color="transparent"),
                intro_card,
                how_to_use_card,
                feedback_link,
            ],
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
        )
