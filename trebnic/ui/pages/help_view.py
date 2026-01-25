"""Help page - user guide explaining how to use Trebnic.

Displays privacy-first messaging and feature explanations in a scrollable view.
Accessed via Settings menu -> Help. Emphasizes local-first data storage.
"""
import flet as ft
from typing import Callable

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    FONT_SIZE_MD,
    FONT_SIZE_BASE,
)
from i18n import t


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
                    ft.Text(title, weight="bold", size=FONT_SIZE_MD),
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
        header = ft.Row([back_btn, ft.Text(t("how_to_use"), size=24, weight="bold")])

        # Privacy-first intro
        intro_card = ft.Container(
            content=ft.Column(
                [
                    ft.Row([
                        ft.Icon(ft.Icons.SHIELD, color=COLORS["green"]),
                        ft.Text(t("privacy_first_title"), weight="bold", size=16),
                    ], spacing=10),
                    ft.Text(
                        t("privacy_first_desc"),
                        size=FONT_SIZE_MD,
                    ),
                    ft.Container(height=5),
                    ft.Row([
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.WIFI_OFF, size=16, color=COLORS["done_text"]),
                                ft.Text(t("works_offline"), size=12, color=COLORS["done_text"]),
                            ], spacing=5),
                        ),
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.LOCK, size=16, color=COLORS["done_text"]),
                                ft.Text(t("optional_encryption"), size=12, color=COLORS["done_text"]),
                            ], spacing=5),
                        ),
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.VISIBILITY_OFF, size=16, color=COLORS["done_text"]),
                                ft.Text(t("no_tracking"), size=12, color=COLORS["done_text"]),
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
        tasks_section = self._section(t("tasks_section"), [
            ft.Text(
                t("tasks_help_1"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
            ft.Text(
                t("tasks_help_2"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
        ])

        # Projects section
        projects_section = self._section(t("projects_section"), [
            ft.Text(
                t("projects_help_1"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
            ft.Text(
                t("projects_help_2"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
        ])

        # Timer section - enhanced
        timer_section = self._section(t("time_tracking_section"), [
            ft.Text(
                t("time_tracking_help_1"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
            ft.Text(
                t("time_tracking_help_2"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
            ft.Text(
                t("time_tracking_help_3"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
        ])

        # Recurrence section - enhanced
        recurrence_section = self._section(t("recurring_section"), [
            ft.Text(
                t("recurring_help_1"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
            ft.Text(
                t("recurring_help_2"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
            ft.Text(
                t("recurring_help_3"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
        ])

        # Calendar section
        calendar_section = self._section(t("calendar_section"), [
            ft.Text(
                t("calendar_help_1"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
        ])

        # Security section - enhanced
        security_section = self._section(t("security_section"), [
            ft.Text(
                t("security_help_1"),
                size=FONT_SIZE_BASE,
                color=COLORS["done_text"],
            ),
            ft.Text(
                t("security_help_2"),
                size=FONT_SIZE_BASE,
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
                t("feedback_link"),
                icon=ft.Icons.FEEDBACK,
                on_click=lambda e: self.navigate(PageType.FEEDBACK),
            ),
            alignment=ft.alignment.center,
        )

        # Motivational footer with a pun
        footer_text = ft.Container(
            content=ft.Text(
                t("motivational_footer"),
                size=FONT_SIZE_MD,
                color=COLORS["done_text"],
                italic=True,
                text_align=ft.TextAlign.CENTER,
            ),
            alignment=ft.alignment.center,
            padding=ft.padding.only(top=10, bottom=20),
        )

        return ft.Column(
            [
                header,
                ft.Divider(height=20, color="transparent"),
                intro_card,
                how_to_use_card,
                feedback_link,
                footer_text,
            ],
            spacing=15,
            scroll=ft.ScrollMode.AUTO,
        )
