import flet as ft
from datetime import datetime, date as date_type, timedelta
from typing import List, Tuple, Optional, Callable

from config import (
    COLORS,
    BORDER_RADIUS,
    PADDING_MD,
    PADDING_SM,
    PageType, 
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
    PADDING_LG,
    PADDING_XL,
    DIALOG_WIDTH_MD, 
)
from models.entities import AppState, TimeEntry, Task
from services.logic import TaskService
from ui.components import DurationKnob
from ui.formatters import TimeFormatter
from ui.helpers import SnackService, accent_btn  
from ui.dialogs.base import open_dialog 


class TimelineColors:
    """Color constants for the timeline view."""
    WORK = COLORS["accent"]
    GAP = COLORS["gap_text"]
    RUNNING = COLORS["green"]
    CONNECTOR = COLORS["border"]
    EDIT_HOVER = "#3d3d3d" 


class TimeEntriesView:
    """Full-page view for displaying time entries for a specific task."""

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        service: TaskService,
        snack: SnackService,
        navigate: Callable[[PageType], None],
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self.snack = snack
        self.navigate = navigate
        self._entries_container: Optional[ft.Column] = None
        self._total_text: Optional[ft.Text] = None
        self._header_text: Optional[ft.Text] = None
        self._stats_row: Optional[ft.Row] = None

    def _format_time(self, dt: datetime) -> str:
        """Format datetime to display time string."""
        return dt.strftime("%H:%M")

    def _format_time_with_seconds(self, dt: datetime) -> str: 
        """Format datetime with seconds for editing precision."""
        return dt.strftime("%H:%M:%S")

    def _format_date(self, dt: datetime) -> str:
        """Format datetime to display date string."""
        return dt.strftime("%b %d, %Y")

    def _format_date_header(self, dt: datetime) -> str:
        """Format date for section header."""
        today = date_type.today()
        entry_date = dt.date()
        if entry_date == today:
            return "Today"
        yesterday = today - timedelta(days=1) 
        if entry_date == yesterday:
            return "Yesterday"
        return dt.strftime("%A, %b %d")

    def _get_task_for_entry(self, entry: TimeEntry) -> Optional[Task]:
        """Get the task associated with a time entry."""
        return self.state.get_task_by_id(entry.task_id)

    def _calculate_gaps(
        self, entries: List[TimeEntry]
    ) -> List[Tuple[str, int, datetime, datetime]]:
        """Calculate gaps between consecutive time entries."""
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

    def _build_timeline_dot(self, color: str, is_running: bool = False) -> ft.Container:
        """Build a timeline dot indicator."""
        size = 12 if not is_running else 14
        inner_content = None 
        if is_running:
            inner_content = ft.Container(
                width=6,
                height=6,
                border_radius=3,
                bgcolor=COLORS["white"],
            )
        return ft.Container(
            width=size,
            height=size,
            border_radius=size // 2,
            bgcolor=color,
            border=ft.border.all(2, COLORS["bg"]) if is_running else None,
            content=inner_content,
            alignment=ft.alignment.center,
        )

    def _build_timeline_line(
        self, 
        height: int = 40, 
        color: str = TimelineColors.CONNECTOR,
        dashed: bool = False,
    ) -> ft.Container:
        """Build a timeline connector line."""
        if dashed:
            return ft.Container(
                width=2,
                height=height,
                content=ft.Column(
                    [
                        ft.Container(
                            width=2,
                            height=4,
                            bgcolor=color,
                            border_radius=1,
                        )
                        for _ in range(height // 8)
                    ],
                    spacing=4,
                ),
            )
        return ft.Container(
            width=2,
            height=height,
            bgcolor=color,
            border_radius=1,
        )

    def _build_progress_bar(
        self, 
        duration_seconds: int, 
        max_seconds: int,
        color: str,
    ) -> ft.Container:
        """Build a horizontal progress bar for duration visualization."""
        progress = min(1.0, duration_seconds / max_seconds) if max_seconds > 0 else 0
        return ft.Container(
            content=ft.Stack( 
                [
                    ft.Container(
                        width=150,
                        height=8, 
                        bgcolor=COLORS["input_bg"],
                        border_radius=4,
                    ),
                    ft.Container(
                        width=max(4, progress * 150),
                        height=8,
                        bgcolor=color,
                        border_radius=4,
                    ),
                ],
            ),
            width=150,
            height=8,
        )

    def _edit_entry(self, entry: TimeEntry) -> None:  
        """Open dialog to edit a time entry using DurationKnob.""" 
        
        if entry.is_running:
            self.snack.show("Cannot edit a running timer", COLORS["danger"])
            return
 
        current_duration_minutes = entry.duration_seconds // 60
        current_duration_minutes = max(5, min(500, current_duration_minutes))
         
        start_time_display = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Start Time (fixed)", size=FONT_SIZE_SM, color=COLORS["done_text"]),
                    ft.Text(
                        self._format_time_with_seconds(entry.start_time),
                        size=FONT_SIZE_XL,
                        weight="bold",
                    ),
                    ft.Text(
                        self._format_date(entry.start_time),
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_XS,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_LG,
            border_radius=BORDER_RADIUS,
            alignment=ft.alignment.center,
        )
         
        knob = DurationKnob(
            initial_minutes=current_duration_minutes,
            size=180,
        )
         
        end_time_text = ft.Text(
            self._format_time(
                entry.start_time + timedelta(minutes=current_duration_minutes)
            ),
            size=FONT_SIZE_XL,
            weight="bold",
            color=COLORS["accent"],
        )
        
        def on_knob_change(minutes: int) -> None:
            new_end = entry.start_time + timedelta(minutes=minutes)
            end_time_text.value = self._format_time(new_end)
            self.page.update()

        knob.set_on_change(on_knob_change)
        
        end_time_display = ft.Container(
            content=ft.Column(
                [
                    ft.Text("End Time", size=FONT_SIZE_SM, color=COLORS["done_text"]),
                    end_time_text,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_XS,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_LG,
            border_radius=BORDER_RADIUS,
            alignment=ft.alignment.center,
        )
        
        error_text = ft.Text("", color=COLORS["danger"], size=FONT_SIZE_SM, visible=False)

        async def save_async() -> None:
            duration_minutes = knob.value
            new_end = entry.start_time + timedelta(minutes=duration_minutes)

            entry.end_time = new_end

            task = self._get_task_for_entry(entry)
            if task:
                await self.service.save_time_entry(entry)
                await self.service.recalculate_task_time_from_entries(task)
            else:
                await self.service.save_time_entry(entry)

            close(None)
            self.snack.show("Time entry updated")
            await self._refresh_async()

        def save(e: ft.ControlEvent) -> None:
            self.page.run_task(save_async)

        content = ft.Container(
            width=DIALOG_WIDTH_MD + 50,
            content=ft.Column(
                [
                    start_time_display,
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    ft.Container(
                        content=knob,
                        alignment=ft.alignment.center,
                    ),
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    end_time_display,
                    error_text,
                ],
                spacing=SPACING_MD,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        _, close = open_dialog(
            self.page,
            "Edit time entry",
            content,
            lambda c: [ft.TextButton("Cancel", on_click=c), accent_btn("Save", save)],
        )

    def _build_entry_row(
        self, 
        entry: TimeEntry, 
        show_date: bool = False,
        max_duration: int = 3600,
        is_first: bool = False,
        is_last: bool = False,
    ) -> ft.Container:
        """Build a row for a single time entry with timeline."""
        task = self._get_task_for_entry(entry)
        project = self.state.get_project_by_id(task.project_id) if task else None

        project_color = project.color if project else COLORS["unassigned"]
        project_icon = project.icon if project else "📋"
        project_name = project.name if project else "No Project"

        start_str = self._format_time(entry.start_time)
        end_str = self._format_time(entry.end_time) if entry.end_time else "Now"
        duration_str = TimeFormatter.seconds_to_short(entry.duration_seconds)

        is_running = entry.end_time is None

        # Date header if needed
        date_header = None
        if show_date:
            date_header = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CALENDAR_TODAY, 
                            size=14, 
                            color=COLORS["done_text"],
                        ),
                        ft.Text(
                            self._format_date_header(entry.start_time),
                            size=FONT_SIZE_MD,
                            color=COLORS["done_text"],
                            weight="bold",
                        ),
                    ],
                    spacing=SPACING_SM,
                ),
                padding=ft.padding.only(left=30, bottom=SPACING_MD, top=SPACING_LG),
            )
 
        dot_color = TimelineColors.RUNNING if is_running else project_color
        timeline_col = ft.Column(
            [
                self._build_timeline_line(20, color=TimelineColors.CONNECTOR) 
                    if not is_first else ft.Container(height=20),
                self._build_timeline_dot(dot_color, is_running),
                self._build_timeline_line(20, color=TimelineColors.CONNECTOR) 
                    if not is_last else ft.Container(height=20),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )
 
        time_col = ft.Container(  
            content=ft.Column(
                [
                    ft.Text(start_str, size=FONT_SIZE_LG, weight="bold"),
                    ft.Text(end_str, size=FONT_SIZE_SM, color=COLORS["done_text"]),
                ],
                spacing=SPACING_XS,
                horizontal_alignment=ft.CrossAxisAlignment.END,
            ),
            width=55, 
            on_click=lambda e, ent=entry: self._edit_entry(ent) if not ent.is_running else None,
            ink=not is_running,
            border_radius=4,
            padding=PADDING_SM,
            tooltip="Click to edit" if not is_running else None,
        )
 
        project_bar = ft.Container(
            width=4,
            height=50,
            bgcolor=project_color,
            border_radius=2,
        )
 
        # On mobile, hide project badge since it's shown in the header
        project_badge = ft.Row(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(project_icon, size=FONT_SIZE_SM),
                            ft.Text(
                                project_name,
                                size=FONT_SIZE_SM,
                                color=COLORS["white"],
                            ),
                        ],
                        spacing=SPACING_XS,
                        tight=True,
                    ),
                    bgcolor=project_color,
                    padding=ft.padding.symmetric(horizontal=PADDING_MD, vertical=2),
                    border_radius=10,
                ),
            ],
            spacing=SPACING_SM,
            visible=not self.state.is_mobile,
        )

        task_info = ft.Column(
            [
                project_badge,
                self._build_progress_bar(
                    entry.duration_seconds,
                    max_duration,
                    project_color,
                ),
            ],
            spacing=SPACING_SM,
            expand=True,
        )
 
        duration_badge = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.TIMER if not is_running else ft.Icons.PLAY_ARROW,
                        size=14,
                        color=COLORS["white"] if is_running else COLORS["accent"],
                    ),
                    ft.Text(
                        duration_str,
                        size=FONT_SIZE_MD,
                        weight="bold",
                        color=COLORS["white"] if is_running else None,
                    ),
                ],
                spacing=SPACING_XS,
                tight=True,
            ),
            bgcolor=COLORS["green"] if is_running else COLORS["card"],
            padding=ft.padding.symmetric(horizontal=PADDING_LG, vertical=PADDING_MD),
            border_radius=BORDER_RADIUS,
            border=None if is_running else ft.border.all(1, COLORS["border"]),
            on_click=lambda e, ent=entry: self._edit_entry(ent) if not ent.is_running else None,
            ink=not is_running,
            tooltip="Click to edit" if not is_running else None,
        )
 
        action_btns = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=COLORS["danger"],
                    icon_size=18,
                    tooltip="Delete entry",
                    on_click=lambda e, eid=entry.id: self._delete_entry(eid),
                    visible=not is_running,
                ),
            ],
            spacing=0,
            tight=True,
        )

        row_content = ft.Container(
            content=ft.Row(
                [
                    timeline_col,
                    time_col, 
                    project_bar,
                    task_info,
                    duration_badge,
                    action_btns, 
                ],
                spacing=SPACING_XL,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["card"],
            padding=ft.padding.symmetric(horizontal=PADDING_LG, vertical=PADDING_MD),
            border_radius=BORDER_RADIUS,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
            border=ft.border.all(1, COLORS["border"]),  
        )

        if date_header:
            return ft.Container(
                content=ft.Column([date_header, row_content], spacing=0),
            )
        return row_content

    def _build_gap_row(
        self, 
        gap_seconds: int, 
        start: datetime, 
        end: datetime,
    ) -> ft.Container:
        """Build a row showing a gap/pause between entries."""
        gap_str = TimeFormatter.seconds_to_short(gap_seconds)
        start_str = self._format_time(start)
        end_str = self._format_time(end)

        # Timeline with dashed line for gap
        timeline_col = ft.Column(
            [
                self._build_timeline_line(15, color=TimelineColors.GAP, dashed=True),
                ft.Container(
                    content=ft.Icon(
                        ft.Icons.PAUSE,
                        size=10,
                        color=TimelineColors.GAP,
                    ),
                    width=12,
                    height=12,
                    border_radius=6,
                    border=ft.border.all(1, TimelineColors.GAP),
                    alignment=ft.alignment.center,
                ),
                self._build_timeline_line(15, color=TimelineColors.GAP, dashed=True),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )

        # Time range for gap
        time_col = ft.Container( 
            content=ft.Column(
                [
                    ft.Text(start_str, size=FONT_SIZE_SM, color=TimelineColors.GAP),
                    ft.Text(end_str, size=FONT_SIZE_SM, color=TimelineColors.GAP),
                ],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.END,
            ),
            width=55, 
            padding=PADDING_SM,
        )

        # Gap info
        gap_info = ft.Row(
            [
                ft.Icon(
                    ft.Icons.COFFEE,
                    size=16,
                    color=TimelineColors.GAP,
                ),
                ft.Text(
                    f"Break · {gap_str}",
                    size=FONT_SIZE_MD,
                    color=TimelineColors.GAP,
                    italic=True,
                ),
            ],
            spacing=SPACING_MD,
        )

        return ft.Container(
            content=ft.Row(
                [
                    timeline_col,
                    time_col,
                    ft.Container(width=4),  # Spacer for alignment
                    gap_info,
                ],
                spacing=SPACING_XL,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["gap_bg"],
            padding=ft.padding.symmetric(horizontal=PADDING_LG, vertical=PADDING_SM),
            border_radius=BORDER_RADIUS,
            border=ft.border.all(1, f"{TimelineColors.GAP}40"),
            opacity=0.8,
        )

    def _build_stats_summary(
        self, 
        entries: List[TimeEntry], 
        gaps: List[Tuple[str, int, datetime, datetime]],
    ) -> ft.Container:
        """Build a summary stats row."""
        total_work = sum(e.duration_seconds for e in entries if e.end_time)
        total_gaps = sum(g[1] for g in gaps)
        total_time = total_work + total_gaps
        efficiency = (total_work / total_time * 100) if total_time > 0 else 100
        entry_count = len(entries) 

        def stat_item(icon: str, label: str, value: str, color: str, sublabel: str = None) -> ft.Container:
            content_col = [
                ft.Row(
                    [
                        ft.Icon(icon, size=16, color=color), 
                        ft.Text(label, size=FONT_SIZE_SM, color=COLORS["done_text"]),
                    ],
                    spacing=SPACING_SM,
                ),
                ft.Text(value, size=FONT_SIZE_XL, weight="bold", color=color), 
            ]
            if sublabel:
                content_col.append(ft.Text(sublabel, size=FONT_SIZE_SM, color=COLORS["done_text"]))
            
            return ft.Container(
                content=ft.Column(
                    content_col,
                    spacing=SPACING_XS,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=COLORS["card"],
                padding=PADDING_LG,
                border_radius=BORDER_RADIUS,
                expand=True,
                border=ft.border.all(1, COLORS["border"]), 
            )

        return ft.Container(
            content=ft.Row(
                [
                    stat_item(
                        ft.Icons.TIMER,
                        "Work Time",
                        TimeFormatter.seconds_to_short(total_work),
                        COLORS["accent"],
                        f"{entry_count} {'entry' if entry_count == 1 else 'entries'}",
                    ),
                    stat_item(
                        ft.Icons.COFFEE,
                        "Break Time",
                        TimeFormatter.seconds_to_short(total_gaps),
                        TimelineColors.GAP,
                        f"{len(gaps)} {'break' if len(gaps) == 1 else 'breaks'}",
                    ),
                    stat_item(
                        ft.Icons.SPEED,
                        "Efficiency",
                        f"{efficiency:.0f}%",
                        COLORS["green"] if efficiency >= 80 else COLORS["orange"],
                    ),
                ],
                spacing=SPACING_MD,
            ),
            margin=ft.margin.only(bottom=SPACING_XL),
        )

    def _delete_entry(self, entry_id: int) -> None:
        """Delete a time entry."""
        async def _delete_async() -> None:
            entries = []
            task_id = self.state.viewing_task_id
            if task_id:
                entries = await self.service.load_time_entries_for_task(task_id)

            await self.service.delete_time_entry(entry_id)

            if task_id:
                task = self.state.get_task_by_id(task_id)
                if task:
                    remaining_entries = [e for e in entries if e.id != entry_id]
                    task.spent_seconds = sum(e.duration_seconds for e in remaining_entries if e.end_time)
                    await self.service.persist_task(task)

            self.snack.show("Time entry deleted", COLORS["danger"])
            await self._refresh_async()

        self.page.run_task(_delete_async)

    def _go_back(self, e: ft.ControlEvent) -> None:
        """Navigate back to tasks."""
        self.state.viewing_task_id = None
        self.navigate(PageType.TASKS)

    async def _refresh_async(self) -> None:
        """Refresh the time entries display (async)."""
        if self._entries_container is None:
            return

        task_id = self.state.viewing_task_id
        task = self.state.get_task_by_id(task_id)

        if task_id:
            entries = await self.service.load_time_entries_for_task(task_id)
        else:
            entries = []

        self._update_entries_display(entries, task)
        self.page.update()

    def _update_entries_display(self, entries: List[TimeEntry], task: Optional[Task]) -> None:
        """Update the entries container with the given entries."""
        if self._entries_container is None:
            return

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
                                "No time entries yet",
                                size=FONT_SIZE_XL,
                                weight="bold",
                                color=COLORS["done_text"],
                            ),
                            ft.Text(
                                "Start a timer on this task to track your time",
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
            gaps = self._calculate_gaps(entries) 
            self._entries_container.controls.append(
                self._build_stats_summary(entries, gaps)
            ) 
            max_duration = max(
                (e.duration_seconds for e in entries if e.end_time), 
                default=3600,
            )
            max_duration = max(max_duration, 1800)  # At least 30 min scale

            current_date = None
            gap_index = 0

            for i, entry in enumerate(entries):
                entry_date = entry.start_time.date()
                show_date = entry_date != current_date
                current_date = entry_date

                is_first = i == 0
                is_last = i == len(entries) - 1 and gap_index >= len(gaps)

                self._entries_container.controls.append(
                    self._build_entry_row(
                        entry, 
                        show_date=show_date,
                        max_duration=max_duration,
                        is_first=is_first,
                        is_last=is_last,
                    )
                )

                # Check for gap after this entry
                if gap_index < len(gaps):
                    gap_type, gap_seconds, gap_start, gap_end = gaps[gap_index]
                    if entry.end_time and entry.end_time == gap_start:
                        self._entries_container.controls.append(
                            self._build_gap_row(gap_seconds, gap_start, gap_end)
                        )
                        gap_index += 1

        total_seconds = sum(e.duration_seconds for e in entries if e.end_time)
        if self._total_text:
            self._total_text.value = f"Total: {TimeFormatter.seconds_to_short(total_seconds)}"

        if self._header_text:
            task_title = task.title if task else "Unknown task"
            self._header_text.value = f"Time entries: {task_title}"

    def refresh(self) -> None:
        """Refresh the time entries display (sync wrapper)."""
        self.page.run_task(self._refresh_async)

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
            f"Time entries: {task.title if task else 'Unknown task'}",
            size=FONT_SIZE_2XL if not self.state.is_mobile else FONT_SIZE_LG,
            weight="bold",
            overflow=ft.TextOverflow.ELLIPSIS,
            expand=True,
        )

        self._total_text = ft.Text(
            "Total: 0m",
            size=FONT_SIZE_LG,
            color=COLORS["done_text"],
            weight="bold",
        )

        if self.state.is_mobile:
            header = ft.Column(
                [
                    ft.Row(
                        [
                            back_btn,
                            self._header_text,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        content=self._total_text,
                        padding=ft.padding.only(left=48),
                    ),
                ],
                spacing=0,
            )
        else:
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
        project_color = project.color if project else COLORS["unassigned"]

        subheader = ft.Container( 
            content=ft.Row(
                [
                    ft.Container(
                        width=8,
                        height=8,
                        border_radius=4,
                        bgcolor=project_color,
                    ),
                    ft.Text(project_icon, size=FONT_SIZE_LG),
                    ft.Text(project_name, size=FONT_SIZE_MD, color=COLORS["done_text"]),
                    ft.Container(expand=True), 
                    ft.Text(
                        "💡 Click duration to edit",
                        size=FONT_SIZE_SM,
                        color=COLORS["done_text"],
                        italic=True,
                        visible=not self.state.is_mobile,
                    ), 
                ],
                spacing=SPACING_MD,
            ),
            padding=ft.padding.symmetric(vertical=SPACING_SM),  
        )

        self._entries_container = ft.Column(
            spacing=SPACING_XS,
            scroll=ft.ScrollMode.AUTO,
        )

        self.refresh()

        return ft.Column(
            [
                header,
                subheader,
                ft.Divider(height=15, color="transparent"), 
                self._entries_container,
            ],
            spacing=SPACING_LG,
            expand=True,
        )