import flet as ft
from datetime import date, timedelta
from typing import Dict, Any, Optional

from config import (
    COLORS,
    BORDER_RADIUS,
    NavItem,
    DURATION_SLIDER_STEP,
    DURATION_SLIDER_MIN,
    DURATION_SLIDER_MAX,
    DIALOG_WIDTH_MD,
)
from i18n import t
from models.entities import AppState
from services.logic import TaskService
from ui.helpers import format_duration, accent_btn, SnackService
from ui.components.task_tile import TaskTile
from ui.dialogs.base import open_dialog


class TasksView:
    """Main task list view that displays pending and completed tasks.

    This component no longer depends on UIController. Task interactions
    are handled via events emitted by TaskTile to the EventBus.
    """

    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        service: TaskService,
        snack: SnackService,
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self.snack = snack
        self.pending_details: Dict[str, Any] = {
            "estimated_minutes": state.default_estimated_minutes
        }
        self._section_label: ft.Text = None  # Will be set in _build_controls
        self._done_section: ft.Column = None  # Will be set in _build_controls
        self._build_controls()

    def _build_controls(self) -> None: 
        self.empty_state = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE_OUTLINE,
                        size=64,
                        color=COLORS["done_text"],
                    ),
                    ft.Text(
                        t("all_caught_up"),
                        size=20,
                        weight="bold",
                        color=COLORS["done_text"],
                    ),
                    ft.Text(
                        t("enjoy_your_day"),
                        size=14,
                        color=COLORS["done_text"],
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.alignment.center,
            padding=40,
            visible=False,
        ) 

        self.task_list = ft.ReorderableListView(
            show_default_drag_handles=False, 
            on_reorder=self._on_reorder, 
            controls=[], 
        ) 

        self.done_list = ft.Column(controls=[], spacing=8)

        self.details_btn = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.TUNE, size=16, color=COLORS["accent"]),
                    ft.Text(t("add_details"), size=13, color=COLORS["accent"]),
                    ft.Icon(
                        ft.Icons.KEYBOARD_ARROW_RIGHT,
                        size=16,
                        color=COLORS["accent"],
                    ),
                ],
                spacing=4,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=10),
            border_radius=BORDER_RADIUS,
            bgcolor=COLORS["card"],
            visible=False,
            tooltip=t("add_details_tooltip"),
            on_click=self._open_details,
        ) 

        self.task_input = ft.TextField(
            hint_text=t("add_new_task"),
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            expand=True,
            on_submit=self._on_submit,
            on_change=self._on_change,
            border_radius=BORDER_RADIUS,
            prefix_icon=ft.Icons.ADD_TASK,
        ) 

        self.submit_btn = ft.IconButton(
            icon=ft.Icons.SEND, 
            icon_color=COLORS["accent"], 
            on_click=self._on_submit, 
            visible=False, 
        ) 

    def _get_default_due_date(self) -> Optional[date]:
        """Determine default due date based on current navigation view."""
        if self.state.selected_nav == NavItem.TODAY:
            return date.today()
        elif self.state.selected_nav == NavItem.UPCOMING:
            return date.today() + timedelta(days=7)
        return None

    async def _on_submit(self, e: ft.ControlEvent) -> None:
        """Handle task submission - async for direct DB access."""
        title = self.task_input.value.strip()
        if not title:
            return

        project_id = (
            list(self.state.selected_projects)[0]
            if len(self.state.selected_projects) == 1 else None
        )

        await self.service.add_task(
            title=title,
            project_id=project_id,
            estimated_seconds=self.pending_details["estimated_minutes"] * 60,
            due_date=self._get_default_due_date(),
        )

        self.pending_details["estimated_minutes"] = self.state.default_estimated_minutes
        self.details_btn.content.controls[1].value = t("add_details")
        self.task_input.value = ""
        self.details_btn.visible = False
        self.refresh()

    def _on_change(self, e: ft.ControlEvent) -> None: 
        self.details_btn.visible = bool(self.task_input.value.strip())
        self.page.update()

    async def _on_reorder(self, e: ft.OnReorderEvent) -> None:
        """Handle task reorder - async for efficient batch DB update."""
        old_idx, new_idx = e.old_index, e.new_index
        n = len(self.task_list.controls)

        # Validate indices
        if old_idx < 0 or old_idx >= n:
            return
        if new_idx < 0 or new_idx > n:
            return
        if old_idx == new_idx:
            return

        # Get task IDs from current UI order (draggables have task.id in data)
        ui_task_ids = [ctrl.data for ctrl in self.task_list.controls]

        # Apply the reorder to get desired order
        moved_id = ui_task_ids.pop(old_idx)
        ui_task_ids.insert(new_idx, moved_id)

        # Get fresh tasks from DB
        filtered, _ = await self.service.get_filtered_tasks()
        task_map = {t.id: t for t in filtered}

        # Assign sort_order based on desired UI order
        for i, task_id in enumerate(ui_task_ids):
            if task_id in task_map:
                task_map[task_id].sort_order = i

        # Persist using efficient batch update (single transaction)
        await self.service.persist_reordered_tasks(list(task_map.values()))

        # Refresh UI from DB
        self.refresh()

    def _open_details(self, e: ft.ControlEvent) -> None: 
        label = ft.Text(
            format_duration(self.pending_details["estimated_minutes"]), 
            size=16, 
            weight="bold", 
        ) 

        def on_slider(ev: ft.ControlEvent) -> None: 
            label.value = format_duration(int(ev.control.value) * DURATION_SLIDER_STEP)
            self.page.update()

        slider = ft.Slider(
            min=DURATION_SLIDER_MIN,
            max=DURATION_SLIDER_MAX,
            divisions=DURATION_SLIDER_MAX - DURATION_SLIDER_MIN,
            value=self.pending_details["estimated_minutes"] // DURATION_SLIDER_STEP,
            on_change=on_slider,
        ) 

        def save(ev: ft.ControlEvent) -> None: 
            self.pending_details["estimated_minutes"] = (
                int(slider.value) * DURATION_SLIDER_STEP 
            ) 
            self.details_btn.content.controls[1].value = format_duration(
                self.pending_details["estimated_minutes"] 
            ) 
            close()
            self.page.update()

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column(
                [
                    ft.Text(t("estimated_time"), weight="bold", size=14),
                    ft.Row(
                        [ft.Icon(ft.Icons.TIMER, size=18), label],
                        spacing=8,
                    ),
                    slider,
                    ft.Text(
                        t("time_range_hint"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=12,
                tight=True,
            ),
        )

        _, close = open_dialog(
            self.page,
            t("task_details"),
            content,
            lambda c: [ft.TextButton(t("cancel"), on_click=c), accent_btn(t("save"), save)],
        ) 

    def refresh(self) -> None:
        """Refresh the task list from database.

        Uses page.run_task to schedule async refresh on the page's event loop.
        """
        self.page.run_task(self._refresh_async)

    async def _refresh_async(self) -> None:
        """Async implementation of refresh - queries DB directly."""
        pending, done = await self.service.get_filtered_tasks()

        # Update section label based on current navigation
        if self._section_label is not None:
            self._section_label.value = self._get_section_label()

        # Update done section visibility
        if self._done_section is not None:
            self._done_section.visible = self._should_show_done_section()

        self.task_list.controls.clear()
        for i, task in enumerate(pending):
            project = self.state.get_project_by_id(task.project_id)
            draggable = ft.ReorderableDraggable(
                index=i,
                content=TaskTile(task, False, self.state, project).build(),
                data=task.id,  # Store task ID for reorder identification
            )
            self.task_list.controls.append(draggable)

        self.done_list.controls.clear()
        for task in done:
            project = self.state.get_project_by_id(task.project_id)
            self.done_list.controls.append(TaskTile(task, True, self.state, project).build())

        # Show empty state only when there are no pending tasks in Today view
        self.empty_state.visible = (
            len(pending) == 0 and self.state.selected_nav == NavItem.TODAY
        )
        self.page.update()

    def set_mobile(self, is_mobile: bool) -> None:
        self.submit_btn.visible = is_mobile

    def update_translations(self) -> None:
        """Update all translatable text in the view."""
        # Update task input hint
        self.task_input.hint_text = t("add_new_task")

        # Update details button text and tooltip
        self.details_btn.content.controls[1].value = t("add_details")
        self.details_btn.tooltip = t("add_details_tooltip")

        # Update empty state text
        self.empty_state.content.controls[1].value = t("all_caught_up")
        self.empty_state.content.controls[2].value = t("enjoy_your_day")

    def _get_section_label(self) -> str:
        """Get the appropriate section label based on current navigation."""
        nav = self.state.selected_nav
        if nav == NavItem.TODAY:
            return t("section_today")
        elif nav == NavItem.INBOX:
            return t("section_inbox")
        elif nav == NavItem.UPCOMING:
            return t("section_upcoming")
        elif nav == NavItem.PROJECTS:
            return t("section_tasks")
        return t("section_tasks")

    def _should_show_done_section(self) -> bool:
        """Determine if the done section should be visible."""
        # Show done section for all task views
        return True

    def build(self) -> ft.Column:
        self._section_label = ft.Text(self._get_section_label(), color="grey", weight="bold")

        self._done_section = ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE,
                            size=16,
                            color=COLORS["done_text"],
                        ),
                        ft.Text(
                            t("section_done"),
                            color=COLORS["done_text"],
                            weight="bold",
                        ),
                    ],
                    spacing=8,
                ),
                ft.Divider(height=10, color="transparent"),
                self.done_list,
            ],
            visible=self._should_show_done_section(),
        )

        return ft.Column(
            alignment=ft.MainAxisAlignment.START,
            controls=[
                ft.Row(
                    controls=[self.task_input, self.details_btn, self.submit_btn],
                    spacing=10,
                ),
                ft.Divider(height=15, color="transparent"),
                self._section_label,
                self.empty_state,
                self.task_list,
                ft.Divider(height=25, color="transparent"),
                self._done_section,
            ],
            scroll=ft.ScrollMode.AUTO,
        ) 