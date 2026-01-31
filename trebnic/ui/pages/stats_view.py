import flet as ft
from typing import Any, Callable, Optional, List
from datetime import datetime, date, timedelta

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    FONT_SIZE_XS,
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
from events import event_bus, AppEvent
from i18n import t
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
        self._time_entries: List[dict] = []
        self._content_column: Optional[ft.Column] = None  # Reference to rebuild on filter change
        self._week_offset: int = 0  # 0 = current week, -1 = last week, etc.

        # Subscribe to events that should trigger stats refresh
        self._task_deleted_sub = event_bus.subscribe(AppEvent.TASK_DELETED, self._on_data_changed)
        self._project_deleted_sub = event_bus.subscribe(AppEvent.PROJECT_DELETED, self._on_data_changed)

    def _on_data_changed(self, data: Any) -> None:
        """Handle task/project deletion - reload data and rebuild content."""
        self._load_data()

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

    def _build_header(self) -> ft.Row:
        """Build the page header with back button."""
        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"],
        )
        return ft.Row([back_btn, ft.Text(t("statistics"), size=FONT_SIZE_4XL, weight="bold")])

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
                accuracy_subtitle = t("taking_longer")
            elif stats.avg_estimation_accuracy < 90:
                accuracy_subtitle = t("faster_than_estimated")
            else:
                accuracy_subtitle = t("on_target")
        else:
            accuracy_text = "N/A"
            accuracy_subtitle = t("no_data_yet")

        # Format streak
        streak_text = f"{streak} {t('days')}" if streak != 1 else f"1 {t('day')}"
        streak_subtitle = t("best_consecutive_run")

        return ft.Column(
            [
                ft.Row(
                    [
                        self._build_stat_card(
                            ft.Icons.CHECK_CIRCLE,
                            COLORS["green"],
                            t("tasks_completed_stat"),
                            str(stats.total_tasks_completed),
                            f"{stats.total_tasks_pending} {t('pending')}",
                        ),
                        self._build_stat_card(
                            ft.Icons.TIMER,
                            COLORS["blue"],
                            t("time_tracked"),
                            time_tracked,
                            f"{stats.tasks_with_time_entries} {t('tasks_with_time')}",
                        ),
                    ],
                    spacing=SPACING_XL,
                ),
                ft.Row(
                    [
                        self._build_stat_card(
                            ft.Icons.ANALYTICS,
                            COLORS["orange"],
                            t("estimation_accuracy"),
                            accuracy_text,
                            accuracy_subtitle,
                        ),
                        self._build_stat_card(
                            ft.Icons.LOCAL_FIRE_DEPARTMENT,
                            COLORS["danger"],
                            t("longest_streak"),
                            streak_text,
                            streak_subtitle,
                        ),
                    ],
                    spacing=SPACING_XL,
                ),
            ],
            spacing=SPACING_XL,
        )

    def _get_week_start(self, offset: int = 0) -> date:
        """Get the Monday of the week with given offset (0 = current week)."""
        today = date.today()
        # Monday is weekday 0
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)
        return monday + timedelta(weeks=offset)

    def _on_week_prev(self, e: ft.ControlEvent) -> None:
        """Navigate to previous week."""
        self._week_offset -= 1
        self._rebuild_content()

    def _on_week_next(self, e: ft.ControlEvent) -> None:
        """Navigate to next week."""
        self._week_offset += 1
        self._rebuild_content()

    def _build_daily_chart(self) -> ft.Container:
        """Build the weekly time chart with dual bars per day.

        Layout per day:
        - Left bar: Tracked time (blue)
        - Right bar: Estimated done + Estimated pending stacked (orange tones)

        Always shows ALL projects regardless of filter selection.
        """
        # Get week start date (Monday)
        week_start = self._get_week_start(self._week_offset)
        week_end = week_start + timedelta(days=6)

        # Calculate daily stats for the selected week
        daily_stats = stats_service.calculate_daily_stats(
            self._time_entries,
            self.state.done_tasks,
            self.state.tasks,
            days=7,
            start_date=week_start,
        )

        # Find max for scaling (max of tracked OR total estimated)
        max_seconds = max(
            (max(d.tracked_seconds, d.estimated_done_seconds + d.estimated_pending_seconds) for d in daily_stats),
            default=1,
        )
        if max_seconds == 0:
            max_seconds = 1

        max_bar_height = 100
        bar_width = 12

        # Build bar chart with dual bars per day
        bars = []
        today = date.today()
        for day_stat in daily_stats:
            # Calculate bar heights
            tracked_height = int((day_stat.tracked_seconds / max_seconds) * max_bar_height) if max_seconds > 0 else 0
            tracked_height = max(tracked_height, 2) if day_stat.tracked_seconds > 0 else 0

            est_done_height = int((day_stat.estimated_done_seconds / max_seconds) * max_bar_height) if max_seconds > 0 else 0
            est_done_height = max(est_done_height, 2) if day_stat.estimated_done_seconds > 0 else 0

            est_pending_height = int((day_stat.estimated_pending_seconds / max_seconds) * max_bar_height) if max_seconds > 0 else 0
            est_pending_height = max(est_pending_height, 2) if day_stat.estimated_pending_seconds > 0 else 0

            # Format durations for tooltips
            tracked_text = seconds_to_time(day_stat.tracked_seconds) if day_stat.tracked_seconds > 0 else "0m"
            est_done_text = seconds_to_time(day_stat.estimated_done_seconds) if day_stat.estimated_done_seconds > 0 else "0m"
            est_pending_text = seconds_to_time(day_stat.estimated_pending_seconds) if day_stat.estimated_pending_seconds > 0 else "0m"

            # Day label with date
            day_label = day_stat.date.strftime("%a")
            date_label = day_stat.date.strftime("%d")
            is_today = day_stat.date == today

            bar_container_height = max_bar_height + 4

            # Left bar: Tracked (blue) - standalone
            tracked_bar = ft.Container(
                width=bar_width,
                height=tracked_height,
                bgcolor=COLORS["accent"],
                border_radius=3,
                tooltip=f"{t('tooltip_tracked')}: {tracked_text}",
            ) if tracked_height > 0 else ft.Container(width=bar_width, height=0)

            # Right bar: Estimated stacked (done at bottom, pending on top)
            has_pending = est_pending_height > 0
            has_done = est_done_height > 0

            est_stacked_controls = []
            # Est pending (top - light orange)
            if has_pending:
                top_radius = 3
                bottom_radius = 0 if has_done else 3
                est_stacked_controls.append(ft.Container(
                    width=bar_width,
                    height=est_pending_height,
                    bgcolor=COLORS["estimated_pending"],
                    border_radius=ft.BorderRadius.only(
                        top_left=top_radius, top_right=top_radius,
                        bottom_left=bottom_radius, bottom_right=bottom_radius,
                    ),
                    tooltip=f"{t('tooltip_est_pending')}: {est_pending_text}",
                ))

            # Est done (bottom - dark orange)
            if has_done:
                top_radius = 0 if has_pending else 3
                est_stacked_controls.append(ft.Container(
                    width=bar_width,
                    height=est_done_height,
                    bgcolor=COLORS["estimated_done"],
                    border_radius=ft.BorderRadius.only(
                        top_left=top_radius, top_right=top_radius,
                        bottom_left=3, bottom_right=3,
                    ),
                    tooltip=f"{t('tooltip_est_done')}: {est_done_text}",
                ))

            est_stacked_bar = ft.Column(
                est_stacked_controls if est_stacked_controls else [ft.Container(width=bar_width, height=0)],
                spacing=0,
                alignment=ft.MainAxisAlignment.END,
            )

            # Dual bars side by side
            dual_bars = ft.Row(
                [
                    tracked_bar,
                    ft.Container(
                        content=est_stacked_bar,
                        alignment=ft.Alignment(0, 1),
                    ),
                ],
                spacing=2,
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.END,
            )

            # Total time label at top (shows tracked)
            total_text = tracked_text if day_stat.tracked_seconds > 0 else ""

            bar = ft.Column(
                [
                    ft.Text(total_text, size=FONT_SIZE_SM, color=COLORS["done_text"]),
                    ft.Container(
                        height=bar_container_height,
                        content=dual_bars,
                        alignment=ft.Alignment(0, 1),
                    ),
                    ft.Text(
                        day_label,
                        size=FONT_SIZE_SM,
                        color=COLORS["accent"] if is_today else COLORS["done_text"],
                        weight="bold" if is_today else None,
                    ),
                    ft.Text(
                        date_label,
                        size=FONT_SIZE_XS,
                        color=COLORS["accent"] if is_today else COLORS["done_text"],
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=2,
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
                ft.Container(width=10, height=10, bgcolor=COLORS["accent"], border_radius=2),
                ft.Text(t("tracked"), size=FONT_SIZE_SM, color=COLORS["done_text"]),
                ft.Container(width=SPACING_MD),
                ft.Container(width=10, height=10, bgcolor=COLORS["estimated_done"], border_radius=2),
                ft.Text(t("est_done"), size=FONT_SIZE_SM, color=COLORS["done_text"]),
                ft.Container(width=SPACING_MD),
                ft.Container(width=10, height=10, bgcolor=COLORS["estimated_pending"], border_radius=2),
                ft.Text(t("est_pending"), size=FONT_SIZE_SM, color=COLORS["done_text"]),
            ],
            spacing=SPACING_SM,
            wrap=True,
        )

        # Week navigation
        week_label = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
        is_current_week = self._week_offset == 0

        week_nav = ft.Row(
            [
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    on_click=self._on_week_prev,
                    icon_color=COLORS["accent"],
                    icon_size=20,
                    tooltip=t("previous_week"),
                ),
                ft.Text(
                    week_label,
                    size=FONT_SIZE_SM,
                    color=COLORS["accent"] if is_current_week else COLORS["done_text"],
                    weight="bold" if is_current_week else None,
                ),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    on_click=self._on_week_next,
                    icon_color=COLORS["accent"],
                    icon_size=20,
                    tooltip=t("next_week"),
                ),
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        # Calculate weekly totals
        total_tracked = sum(d.tracked_seconds for d in daily_stats)
        total_estimated = sum(d.estimated_done_seconds + d.estimated_pending_seconds for d in daily_stats)

        weekly_totals = ft.Row(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(width=8, height=8, bgcolor=COLORS["accent"], border_radius=2),
                            ft.Text(f"{t('tracked')}: {seconds_to_time(total_tracked)}", size=FONT_SIZE_SM),
                        ],
                        spacing=SPACING_SM,
                    ),
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(width=8, height=8, bgcolor=COLORS["estimated_done"], border_radius=2),
                            ft.Text(f"{t('estimated')}: {seconds_to_time(total_estimated)}", size=FONT_SIZE_SM),
                        ],
                        spacing=SPACING_SM,
                    ),
                ),
            ],
            spacing=SPACING_XL,
            alignment=ft.MainAxisAlignment.CENTER,
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.BAR_CHART, size=20, color=COLORS["accent"]),
                            ft.Text(t("weekly_time"), weight="bold", size=FONT_SIZE_LG),
                            ft.Container(expand=True),
                            legend,
                        ],
                        spacing=SPACING_MD,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    week_nav,
                    ft.Container(height=SPACING_MD),
                    chart_content,
                    ft.Container(height=SPACING_MD),
                    weekly_totals,
                ],
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
        )

    def _build_project_breakdown(self) -> ft.Container:
        """Build project breakdown section showing all projects with scroll."""
        project_stats = stats_service.calculate_project_stats(
            self.state.tasks,
            self.state.done_tasks,
            self.state.projects,
        )

        # Sort by time tracked
        project_stats.sort(key=lambda p: p.tracked_seconds, reverse=True)

        # Find max time for progress bar scaling
        max_seconds = max((p.tracked_seconds for p in project_stats), default=1)
        if max_seconds == 0:
            max_seconds = 1

        rows = []
        for ps in project_stats:
            time_text = seconds_to_time(ps.tracked_seconds) if ps.tracked_seconds > 0 else "0m"
            total_tasks = ps.tasks_completed + ps.tasks_pending
            completion_rate = (ps.tasks_completed / total_tasks * 100) if total_tasks > 0 else 0
            progress_width = (ps.tracked_seconds / max_seconds) if max_seconds > 0 else 0

            # Get project color (gray for unassigned)
            if ps.project_id is None:
                project_color = COLORS["unassigned"]
            else:
                project_color = COLORS["accent"]  # Fallback
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
                                    f"{ps.tasks_completed}/{total_tasks} {t('tasks')}",
                                    size=FONT_SIZE_SM,
                                    color=COLORS["done_text"],
                                ),
                                ft.Text(
                                    f"{completion_rate:.0f}% {t('complete')}",
                                    size=FONT_SIZE_SM,
                                    color=COLORS["done_text"],
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=6,
                ),
                padding=ft.Padding.symmetric(vertical=SPACING_MD),
                border=ft.Border.only(bottom=ft.BorderSide(1, COLORS["border"])),
            )
            rows.append(row)

        if not rows:
            rows.append(
                ft.Container(
                    content=ft.Text(t("no_project_data"), color=COLORS["done_text"]),
                    padding=PADDING_LG,
                )
            )

        # Scrollable container for projects (max ~4 visible, ~280px height)
        projects_list = ft.Container(
            content=ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO),
            height=280 if len(rows) > 4 else None,
        )

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.FOLDER, size=20, color=COLORS["blue"]),
                            ft.Text(t("by_project"), weight="bold", size=FONT_SIZE_LG),
                        ],
                        spacing=SPACING_MD,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=SPACING_LG),
                    projects_list,
                ],
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
        )

    def _export_to_json(self, e: ft.ControlEvent) -> None:
        """Export stats to JSON file."""
        async def _do_export() -> None:
            json_data = stats_service.export_to_json(
                self.state.tasks,
                self.state.done_tasks,
                self.state.projects,
                self._time_entries,
            )

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trebnic_stats_{timestamp}.json"

            # Use file picker to save (flet 0.80.x async API)
            file_picker = ft.FilePicker()
            self.page.services.append(file_picker)
            self.page.update()

            result = await file_picker.save_file(
                dialog_title=t("export_statistics"),
                file_name=filename,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
            )

            if result:
                try:
                    with open(result, "w", encoding="utf-8") as f:
                        f.write(json_data)
                    SnackService.show(self.page, f"{t('exported_to')} {result}")
                except OSError as ex:
                    SnackService.show(self.page, f"{t('export_failed')}: {ex}")

        self.page.run_task(_do_export)

    def _build_export_section(self) -> ft.Container:
        """Build export section with JSON export button."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DOWNLOAD, size=20, color=COLORS["accent"]),
                    ft.Text(t("export_data"), weight="bold", size=FONT_SIZE_LG),
                    ft.Container(expand=True),
                    ft.Button(
                        t("export_to_json"),
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
            (t("estimation_breakdown"), t("estimation_breakdown_desc")),
        ]

        feature_chips = []
        for name, description in features:
            chip = ft.Container(
                content=ft.Text(name, size=FONT_SIZE_SM),
                bgcolor=COLORS["input_bg"],
                padding=ft.Padding.symmetric(horizontal=PADDING_LG, vertical=SPACING_MD),
                border_radius=BORDER_RADIUS,
                border=ft.Border.all(1, COLORS["border"]),
                tooltip=description,
            )
            feature_chips.append(chip)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.UPCOMING, size=20, color=COLORS["done_text"]),
                            ft.Text(t("coming_soon"), weight="bold", size=FONT_SIZE_LG, color=COLORS["done_text"]),
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
