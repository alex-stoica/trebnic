import flet as ft
from datetime import date, datetime, timedelta
from typing import List, Tuple, Optional, Callable

from config import (
    COLORS,
    BORDER_RADIUS,
    PAGE_TASKS,
    GAP_THRESHOLD_SECONDS,
    FONT_SIZE_SM,
    FONT_SIZE_MD,
    FONT_SIZE_LG,
    FONT_SIZE_XL,
    FONT_SIZE_2XL,
    SPACING_XS,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    SPACING_XL,
    PADDING_MD,
    PADDING_LG,
    PADDING_XL,
)
from models.entities import AppState, TimeEntry, Task
from services.logic import TaskService
from ui.helpers import SnackService, seconds_to_time


class TimeEntriesView:
    """Full-page view for displaying time entries for a specific task."""

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
        self._entries_container: Optional[ft.Column] = None
        self._total_text: Optional[ft.Text] = None
        self._header_text: Optional[ft.Text] = None

    def _format_time(self, dt: datetime) -> str:
        """Format datetime to display time string."""
        return dt.strftime("%H:%M")

    def _format_date(self, dt: datetime) -> str:
        """Format datetime to display date string."""
        return dt.strftime("%b %d, %Y")

    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to human-readable string."""
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
        return f"{mins}m"

    def _get_task_for_entry(self, entry: TimeEntry) -> Optional[Task]:
        """Get the task associated with a time entry."""
        return self.state.get_task_by_id(entry.task_id)

    def _calculate_gaps(
        self, entries: List[TimeEntry]
    ) -> List[Tuple[str, int, datetime, datetime]]:
        """Calculate gaps between consecutive time entries.
        
        Returns list of tuples: (gap_type, duration_seconds, start, end)
        """
        gaps = []
        if len(entries) < 2:
            return gaps

        for i in range(len(entries) - 1):
            current = entries[i]
            next_entry = entries[i + 1]

            if current.end_time and next_entry.start_time:
                gap_seconds = int(
                    (next_entry.start_time - current.end_time).total_seconds()
                )
                if gap_seconds >= GAP_THRESHOLD_SECONDS:
                    gaps.append((
                        "gap",
                        gap_seconds,
                        current.end_time,
                        next_entry.start_time,
                    ))

        return gaps

    def _build_entry_row(self, entry: TimeEntry, show_date: bool = False) -> ft.Container:
        """Build a row for a single time entry."""
        task = self._get_task_for_entry(entry)
        project = self.state.get_project_by_id(task.project_id) if task else None

        task_title = task.title if task else "Unknown Task"
        project_color = project.color if project else COLORS["unassigned"]
        project_icon = project.icon if project else "📋"
        project_name = project.name if project else "No Project"

        start_str = self._format_time(entry.start_time)
        end_str = self._format_time(entry.end_time) if entry.end_time else "Running..."
        duration_str = self._format_duration(entry.duration_seconds)

        is_running = entry.end_time is None

        # Date label for grouping
        date_label = None
        if show_date:
            date_label = ft.Container(
                content=ft.Text(
                    self._format_date(entry.start_time),
                    size=FONT_SIZE_SM,
                    color=COLORS["done_text"],
                    weight="bold",
                ),
                padding=ft.padding.only(bottom=SPACING_SM),
            )

        # Time column
        time_col = ft.Container(
            content=ft.Column(
                [
                    ft.Text(start_str, size=FONT_SIZE_LG, weight="bold"),
                    ft.Text(end_str, size=FONT_SIZE_MD, color=COLORS["done_text"]),
                ],
                spacing=SPACING_XS,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=60,
        )

        # Project indicator
        project_indicator = ft.Container(
            width=4,
            height=50,
            bgcolor=project_color,
            border_radius=2,
        )

        # Task info - show project when viewing task-specific entries
        task_info = ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(project_icon, size=FONT_SIZE_SM),
                        ft.Text(
                            project_name,
                            size=FONT_SIZE_SM,
                            color=COLORS["done_text"],
                        ),
                    ],
                    spacing=SPACING_SM,
                ),
            ],
            spacing=SPACING_XS,
            expand=True,
        )

        # Duration badge
        duration_badge = ft.Container(
            content=ft.Text(
                duration_str,
                size=FONT_SIZE_MD,
                weight="bold",
                color=COLORS["white"] if is_running else COLORS["accent"],
            ),
            bgcolor=COLORS["accent"] if is_running else COLORS["input_bg"],
            padding=ft.padding.symmetric(horizontal=PADDING_LG, vertical=PADDING_MD),
            border_radius=BORDER_RADIUS,
        )

        # Delete button
        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=COLORS["danger"],
            icon_size=18,
            tooltip="Delete entry",
            on_click=lambda e, eid=entry.id: self._delete_entry(eid),
            visible=not is_running,
        )

        row_content = ft.Container(
            content=ft.Row(
                [
                    time_col,
                    project_indicator,
                    task_info,
                    duration_badge,
                    delete_btn,
                ],
                spacing=SPACING_XL,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_LG,
            border_radius=BORDER_RADIUS,
            animate=ft.animation.Animation(200, ft.AnimationCurve.EASE_OUT),
        )

        if date_label:
            return ft.Container(
                content=ft.Column([date_label, row_content], spacing=0),
            )
        return row_content

    def _build_gap_row(
        self, gap_seconds: int, start: datetime, end: datetime
    ) -> ft.Container:
        """Build a row showing a gap between entries."""
        gap_str = self._format_duration(gap_seconds)
        start_str = self._format_time(start)
        end_str = self._format_time(end)

        return ft.Container(
            content=ft.Row(
                [
                    ft.Container( 
                        content=ft.Column(
                            [
                                ft.Text(
                                    start_str,
                                    size=FONT_SIZE_SM,
                                    color=COLORS["gap_text"],
                                ),
                                ft.Text(
                                    end_str,
                                    size=FONT_SIZE_SM,
                                    color=COLORS["gap_text"],
                                ),
                            ],
                            spacing=0,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        width=60,
                    ),
                    ft.Container( 
                        width=4,
                        height=30,
                        border=ft.border.all(1, COLORS["gap_text"]),
                        border_radius=2,
                    ),
                    ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.PAUSE_CIRCLE_OUTLINE,
                                size=16,
                                color=COLORS["gap_text"],
                            ),
                            ft.Text(
                                f"Gap: {gap_str}",
                                size=FONT_SIZE_MD,
                                color=COLORS["gap_text"],
                                italic=True,
                            ),
                        ],
                        spacing=SPACING_MD,
                    ),
                ],
                spacing=SPACING_XL,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["gap_bg"],
            padding=ft.padding.symmetric(horizontal=PADDING_LG, vertical=PADDING_MD),
            border_radius=BORDER_RADIUS,
            opacity=0.7,
        )

    def _delete_entry(self, entry_id: int) -> None:
        """Delete a time entry."""
        self.service.delete_time_entry(entry_id)
        self.snack.show("Time entry deleted", COLORS["danger"])
        self.refresh()

    def _go_back(self, e: ft.ControlEvent) -> None:
        """Navigate back to tasks."""
        self.state.viewing_task_id = None
        self.navigate(PAGE_TASKS)

    def refresh(self) -> None:
        """Refresh the time entries display."""
        if self._entries_container is None:
            return

        task_id = self.state.viewing_task_id
        task = self.state.get_task_by_id(task_id)
        
        if task_id:
            entries = self.service.load_time_entries_for_task(task_id)
        else:
            entries = []

        self._entries_container.controls.clear()

        if not entries:
            self._entries_container.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(
                                ft.Icons.TIMER_OFF_OUTLINED,
                                size=64,
                                color=COLORS["done_text"],
                            ),
                            ft.Text(
                                "No time entries",
                                size=FONT_SIZE_XL,
                                weight="bold",
                                color=COLORS["done_text"],
                            ),
                            ft.Text(
                                "Start a timer on this task to track time",
                                size=FONT_SIZE_MD,
                                color=COLORS["done_text"],
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=SPACING_LG,
                    ),
                    alignment=ft.alignment.center,
                    padding=PADDING_XL * 3,
                )
            )
        else: 
            current_date = None
            gaps = self._calculate_gaps(entries)
            gap_index = 0

            for i, entry in enumerate(entries):
                entry_date = entry.start_time.date()
                show_date = entry_date != current_date
                current_date = entry_date
                
                self._entries_container.controls.append(
                    self._build_entry_row(entry, show_date=show_date)
                )

                # Check if there's a gap after this entry
                if gap_index < len(gaps):
                    gap_type, gap_seconds, gap_start, gap_end = gaps[gap_index]
                    if entry.end_time and entry.end_time == gap_start:
                        self._entries_container.controls.append(
                            self._build_gap_row(gap_seconds, gap_start, gap_end)
                        )
                        gap_index += 1
 
        total_seconds = sum(e.duration_seconds for e in entries if e.end_time)
        if self._total_text:
            self._total_text.value = f"Total: {self._format_duration(total_seconds)}"

        # Update header
        if self._header_text and task:
            self._header_text.value = f"Time Entries: {task.title}"

        self.page.update()

    def build(self) -> ft.Column:
        """Build the time entries view.""" 
        task_id = self.state.viewing_task_id
        task = self.state.get_task_by_id(task_id)
        
        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=self._go_back,
            icon_color=COLORS["accent"],
        )

        self._header_text = ft.Text(
            f"Time Entries: {task.title if task else 'Unknown'}",
            size=FONT_SIZE_2XL,
            weight="bold",
        )

        self._total_text = ft.Text(
            "Total: 0m",
            size=FONT_SIZE_LG,
            color=COLORS["done_text"],
            weight="bold",
        )

        header = ft.Row(
            [
                back_btn,
                self._header_text,  
                ft.Container(expand=True),
                self._total_text,
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
 
        project = self.state.get_project_by_id(task.project_id) if task else None 
        project_icon = project.icon if project else "📋"  
        project_name = project.name if project else "No Project" 
        
        subheader = ft.Row(
            [
                ft.Text(project_icon, size=FONT_SIZE_LG), 
                ft.Text(project_name, size=FONT_SIZE_MD, color=COLORS["done_text"]), 
            ],
            spacing=SPACING_MD,
        )

        self._entries_container = ft.Column( 
            spacing=SPACING_MD,
            scroll=ft.ScrollMode.AUTO,
        )

        self.refresh() 
        return ft.Column(  
            [
                header,
                subheader,
                ft.Divider(height=20, color="transparent"),
                self._entries_container,
            ],
            spacing=SPACING_LG,
            expand=True,
        )