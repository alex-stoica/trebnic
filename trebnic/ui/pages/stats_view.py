import flet as ft
from typing import Callable, Optional, List
from datetime import datetime

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    FONT_SIZE_SM,
    FONT_SIZE_BASE,
    FONT_SIZE_LG,
    FONT_SIZE_XL,
    FONT_SIZE_4XL,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    SPACING_XL,
    PADDING_LG,
    PADDING_XL,
    PADDING_2XL,
)
from models.entities import AppState
from services.stats import stats_service
from ui.helpers import seconds_to_time, SnackService


class StatsPage:
    """User statistics page with charts and analytics."""

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        navigate: Callable[[PageType], None],
        load_time_entries: Callable,
    ) -> None:
        self.page = page
        self.state = state
        self.navigate = navigate
        self.load_time_entries = load_time_entries
        self._selected_project: Optional[str] = None  # None means "All projects"
        self._time_entries: List[dict] = []
        self._content_column: Optional[ft.Column] = None  # Reference to rebuild on filter change

    def _load_data(self) -> None:
        """Load time entries for stats calculation."""
        async def _load() -> None:
            self._time_entries = await self.load_time_entries()
            self._rebuild_content()

        self.page.run_task(_load)

    def _rebuild_content(self) -> None:
        """Rebuild the page content (used when filter changes or data loads)."""
        if self._content_column is None:
            return
        self._content_column.controls = [
            self._build_header(),
            ft.Container(height=SPACING_MD),
            self._build_overview_cards(),
            ft.Container(height=SPACING_XL),
            self._build_daily_chart(),
            ft.Container(height=SPACING_XL),
            self._build_project_breakdown(),
            ft.Container(height=SPACING_XL),
            self._build_export_section(),
            ft.Container(height=SPACING_XL),
            self._build_coming_soon_section(),
        ]
        self.page.update()

    def _on_project_change(self, e: ft.ControlEvent) -> None:
        """Handle project filter change."""
        value = e.control.value
        self._selected_project = None if value == "all" else value
        self._rebuild_content()

    def _build_header(self) -> ft.Row:
        """Build the page header with back button."""
        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"],
        )
        return ft.Row([back_btn, ft.Text("Statistics", size=FONT_SIZE_4XL, weight="bold")])

    def _build_stat_card(
        self,
        icon: str,
        icon_color: str,
        title: str,
        value: str,
        subtitle: Optional[str] = None,
    ) -> ft.Container:
        """Build a single stat card."""
        content_controls = [
            ft.Icon(icon, color=icon_color, size=24),
            ft.Text(title, weight="bold", size=FONT_SIZE_BASE),
            ft.Text(value, size=FONT_SIZE_XL, weight="bold", color=COLORS["accent"]),
        ]
        if subtitle:
            content_controls.append(
                ft.Text(subtitle, size=FONT_SIZE_SM, color=COLORS["done_text"])
            )

        return ft.Container(
            content=ft.Column(
                content_controls,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_MD,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
            expand=True,
        )

    def _build_overview_cards(self) -> ft.Column:
        """Build the overview stat cards. Always shows ALL projects."""
        # Always use ALL data (not filtered by project)
        stats = stats_service.calculate_overall_stats(
            self.state.tasks, self.state.done_tasks, self._time_entries
        )
        streak = stats_service.calculate_completion_streak(self.state.done_tasks)

        # Format time tracked
        time_tracked = seconds_to_time(stats.total_time_tracked_seconds)

        # Format accuracy
        if stats.avg_estimation_accuracy > 0:
            accuracy_text = f"{stats.avg_estimation_accuracy:.0f}%"
            if stats.avg_estimation_accuracy > 100:
                accuracy_subtitle = "Taking longer than estimated"
            elif stats.avg_estimation_accuracy < 90:
                accuracy_subtitle = "Faster than estimated"
            else:
                accuracy_subtitle = "On target"
        else:
            accuracy_text = "N/A"
            accuracy_subtitle = "No data yet"

        # Format streak
        streak_text = f"{streak} days" if streak != 1 else "1 day"
        streak_subtitle = "Best consecutive run"

        return ft.Column(
            [
                ft.Row(
                    [
                        self._build_stat_card(
                            ft.Icons.CHECK_CIRCLE,
                            COLORS["green"],
                            "Tasks completed",
                            str(stats.total_tasks_completed),
                            f"{stats.total_tasks_pending} pending",
                        ),
                        self._build_stat_card(
                            ft.Icons.TIMER,
                            COLORS["blue"],
                            "Time tracked",
                            time_tracked,
                            f"{stats.tasks_with_time_entries} tasks with time",
                        ),
                    ],
                    spacing=SPACING_XL,
                ),
                ft.Row(
                    [
                        self._build_stat_card(
                            ft.Icons.ANALYTICS,
                            COLORS["orange"],
                            "Estimation accuracy",
                            accuracy_text,
                            accuracy_subtitle,
                        ),
                        self._build_stat_card(
                            ft.Icons.LOCAL_FIRE_DEPARTMENT,
                            COLORS["danger"],
                            "Longest streak",
                            streak_text,
                            streak_subtitle,
                        ),
                    ],
                    spacing=SPACING_XL,
                ),
            ],
            spacing=SPACING_XL,
        )

    def _build_daily_chart(self) -> ft.Container:
        """Build the daily time chart (last 7 days) with estimated and tracked bars.

        Always shows ALL projects regardless of filter selection.
        """
        # Always use ALL data for the daily chart (not filtered by project)
        daily_stats = stats_service.calculate_daily_stats(
            self._time_entries, self.state.done_tasks, self.state.tasks, days=7
        )

        # Find max for scaling (consider both tracked and estimated)
        max_seconds = max(
            (max(d.tracked_seconds, d.estimated_seconds) for d in daily_stats),
            default=1
        )
        if max_seconds == 0:
            max_seconds = 1

        max_bar_height = 100

        # Build bar chart with dual bars (estimated and tracked)
        bars = []
        for day_stat in daily_stats:
            # Calculate bar heights
            tracked_height = int((day_stat.tracked_seconds / max_seconds) * max_bar_height) if max_seconds > 0 else 0
            tracked_height = max(tracked_height, 2) if day_stat.tracked_seconds > 0 else 0

            estimated_height = int((day_stat.estimated_seconds / max_seconds) * max_bar_height) if max_seconds > 0 else 0
            estimated_height = max(estimated_height, 2) if day_stat.estimated_seconds > 0 else 0

            # Format durations for tooltip
            tracked_text = seconds_to_time(day_stat.tracked_seconds) if day_stat.tracked_seconds > 0 else "0m"
            estimated_text = seconds_to_time(day_stat.estimated_seconds) if day_stat.estimated_seconds > 0 else "0m"

            # Day label
            day_label = day_stat.date.strftime("%a")

            # Create the dual bar column with fixed height container for alignment
            bar_container_height = max_bar_height + 4

            bar = ft.Column(
                [
                    # Duration label (shows tracked time)
                    ft.Text(tracked_text, size=FONT_SIZE_SM, color=COLORS["done_text"]),
                    # Container to hold bars with bottom alignment
                    ft.Container(
                        height=bar_container_height,
                        content=ft.Row(
                            [
                                # Estimated bar (orange color)
                                ft.Container(
                                    width=14,
                                    height=estimated_height,
                                    bgcolor=COLORS["orange"],
                                    border_radius=ft.border_radius.only(top_left=3, top_right=3),
                                    tooltip=f"Est: {estimated_text}",
                                ),
                                # Tracked bar (accent color)
                                ft.Container(
                                    width=14,
                                    height=tracked_height,
                                    bgcolor=COLORS["accent"],
                                    border_radius=ft.border_radius.only(top_left=3, top_right=3),
                                    tooltip=f"Tracked: {tracked_text}",
                                ),
                            ],
                            spacing=2,
                            alignment=ft.MainAxisAlignment.CENTER,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                    ),
                    ft.Text(day_label, size=FONT_SIZE_SM, color=COLORS["done_text"]),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            )
            bars.append(bar)

        chart_content = ft.Row(
            bars,
            alignment=ft.MainAxisAlignment.SPACE_AROUND,
            vertical_alignment=ft.CrossAxisAlignment.END,
        )

        # Legend
        legend = ft.Row(
            [
                ft.Container(width=12, height=12, bgcolor=COLORS["orange"], border_radius=2),
                ft.Text("Estimated", size=FONT_SIZE_SM, color=COLORS["done_text"]),
                ft.Container(width=SPACING_LG),
                ft.Container(width=12, height=12, bgcolor=COLORS["accent"], border_radius=2),
                ft.Text("Tracked", size=FONT_SIZE_SM, color=COLORS["done_text"]),
            ],
            spacing=SPACING_SM,
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.BAR_CHART, size=20, color=COLORS["accent"]),
                            ft.Text("Time (last 7 days)", weight="bold", size=FONT_SIZE_LG),
                            ft.Container(expand=True),
                            legend,
                        ],
                        spacing=SPACING_MD,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=SPACING_XL),
                    chart_content,
                ],
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
        )

    def _build_project_breakdown(self) -> ft.Container:
        """Build project breakdown section with filter dropdown."""
        project_stats = stats_service.calculate_project_stats(
            self.state.tasks,
            self.state.done_tasks,
            self.state.projects,
        )

        # Filter by selected project if one is chosen
        if self._selected_project is not None:
            project_stats = [ps for ps in project_stats if ps.project_id == self._selected_project]

        # Sort by time tracked
        project_stats.sort(key=lambda p: p.tracked_seconds, reverse=True)

        # Find max time for progress bar scaling
        max_seconds = max((p.tracked_seconds for p in project_stats), default=1)
        if max_seconds == 0:
            max_seconds = 1

        # Build project filter dropdown
        options = [ft.dropdown.Option(key="all", text="All projects")]
        for p in self.state.projects:
            options.append(ft.dropdown.Option(key=p.id, text=p.name))

        dropdown = ft.Dropdown(
            value=self._selected_project or "all",
            options=options,
            on_change=self._on_project_change,
            width=200,
            bgcolor=COLORS["input_bg"],
            border_color=COLORS["border"],
            text_size=FONT_SIZE_SM,
            content_padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )

        rows = []
        for ps in project_stats:
            time_text = seconds_to_time(ps.tracked_seconds) if ps.tracked_seconds > 0 else "0m"
            total_tasks = ps.tasks_completed + ps.tasks_pending
            completion_rate = (ps.tasks_completed / total_tasks * 100) if total_tasks > 0 else 0
            progress_width = (ps.tracked_seconds / max_seconds) if max_seconds > 0 else 0

            # Get project color
            project_color = COLORS["accent"]
            for proj in self.state.projects:
                if proj.id == ps.project_id:
                    project_color = proj.color
                    break

            row = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(ps.project_name, weight="bold", size=FONT_SIZE_BASE, expand=True),
                                ft.Text(time_text, size=FONT_SIZE_BASE, color=COLORS["accent"]),
                            ],
                        ),
                        ft.Container(
                            content=ft.Container(
                                width=progress_width * 200,
                                height=4,
                                bgcolor=project_color,
                                border_radius=2,
                            ),
                            width=200,
                            height=4,
                            bgcolor=COLORS["border"],
                            border_radius=2,
                        ),
                        ft.Row(
                            [
                                ft.Text(
                                    f"{ps.tasks_completed}/{total_tasks} tasks",
                                    size=FONT_SIZE_SM,
                                    color=COLORS["done_text"],
                                ),
                                ft.Text(
                                    f"{completion_rate:.0f}% complete",
                                    size=FONT_SIZE_SM,
                                    color=COLORS["done_text"],
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=6,
                ),
                padding=ft.padding.symmetric(vertical=SPACING_MD),
                border=ft.border.only(bottom=ft.BorderSide(1, COLORS["border"])),
            )
            rows.append(row)

        if not rows:
            rows.append(
                ft.Container(
                    content=ft.Text("No project data yet", color=COLORS["done_text"]),
                    padding=PADDING_LG,
                )
            )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.FOLDER, size=20, color=COLORS["blue"]),
                            ft.Text("By project", weight="bold", size=FONT_SIZE_LG),
                            ft.Container(expand=True),
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.FILTER_LIST, size=16, color=COLORS["done_text"]),
                                    ft.Text("Filter stats:", size=FONT_SIZE_SM, color=COLORS["done_text"]),
                                    dropdown,
                                ],
                                spacing=SPACING_MD,
                            ),
                        ],
                        spacing=SPACING_MD,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=SPACING_LG),
                    *rows,
                ],
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
        )

    def _export_to_json(self, e: ft.ControlEvent) -> None:
        """Export stats to JSON file."""
        json_data = stats_service.export_to_json(
            self.state.tasks,
            self.state.done_tasks,
            self.state.projects,
            self._time_entries,
        )

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trebnic_stats_{timestamp}.json"

        # Use file picker to save
        def save_result(e: ft.FilePickerResultEvent) -> None:
            if e.path:
                try:
                    with open(e.path, "w", encoding="utf-8") as f:
                        f.write(json_data)
                    SnackService.show(self.page, f"Exported to {e.path}")
                except OSError as ex:
                    SnackService.show(self.page, f"Export failed: {ex}")

        file_picker = ft.FilePicker(on_result=save_result)
        self.page.overlay.append(file_picker)
        self.page.update()
        file_picker.save_file(
            dialog_title="Export statistics",
            file_name=filename,
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["json"],
        )

    def _build_export_section(self) -> ft.Container:
        """Build export section with JSON export button."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DOWNLOAD, size=20, color=COLORS["accent"]),
                    ft.Text("Export data", weight="bold", size=FONT_SIZE_LG),
                    ft.Container(expand=True),
                    ft.ElevatedButton(
                        "Export to JSON",
                        icon=ft.Icons.FILE_DOWNLOAD,
                        on_click=self._export_to_json,
                        bgcolor=COLORS["accent"],
                        color=COLORS["bg"],
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
        )

    def _build_coming_soon_section(self) -> ft.Container:
        """Build placeholder for upcoming features."""
        features = [
            ("Weekly view", "Toggle between daily and weekly aggregation"),
            ("Estimation breakdown", "See which tasks took longer vs faster"),
            ("Date range picker", "View stats for custom time periods"),
        ]

        feature_chips = []
        for name, description in features:
            chip = ft.Container(
                content=ft.Text(name, size=FONT_SIZE_SM),
                bgcolor=COLORS["input_bg"],
                padding=ft.padding.symmetric(horizontal=PADDING_LG, vertical=SPACING_MD),
                border_radius=BORDER_RADIUS,
                border=ft.border.all(1, COLORS["border"]),
                tooltip=description,
            )
            feature_chips.append(chip)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.UPCOMING, size=20, color=COLORS["done_text"]),
                            ft.Text("Coming soon", weight="bold", size=FONT_SIZE_LG, color=COLORS["done_text"]),
                        ],
                        spacing=SPACING_MD,
                    ),
                    ft.Container(height=SPACING_LG),
                    ft.Row(feature_chips, wrap=True, spacing=SPACING_MD, run_spacing=SPACING_MD),
                ],
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
            opacity=0.7,
        )

    def build(self) -> ft.Column:
        """Build the stats page."""
        # Load time entries if not already loaded
        if not self._time_entries:
            self._load_data()

        self._content_column = ft.Column(
            [
                self._build_header(),
                ft.Container(height=SPACING_MD),
                self._build_overview_cards(),
                ft.Container(height=SPACING_XL),
                self._build_daily_chart(),
                ft.Container(height=SPACING_XL),
                self._build_project_breakdown(),
                ft.Container(height=SPACING_XL),
                self._build_export_section(),
                ft.Container(height=SPACING_XL),
                self._build_coming_soon_section(),
            ],
            spacing=SPACING_MD,
        )
        return self._content_column
