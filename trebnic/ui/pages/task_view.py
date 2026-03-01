import flet as ft
from datetime import date, timedelta
from typing import Callable, Dict, Any, Optional

from config import (
    COLORS,
    BORDER_RADIUS,
    NavItem,
    TaskFilter,
    DURATION_SLIDER_STEP,
    DURATION_SLIDER_MIN,
    DURATION_SLIDER_MAX,
    DIALOG_WIDTH_LG,
)
from i18n import t
from models.entities import AppState
from services.logic import TaskService
from ui.helpers import format_duration, accent_btn, SnackService
from ui.components.task_tile import TaskTile
from ui.presenters.task_presenter import TaskPresenter
from ui.dialogs.base import open_dialog
from ui.dialogs.task_dialogs import get_date_picker
from events import event_bus, AppEvent


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
        on_open_notes: Optional[Callable] = None,
    ) -> None:
        self.page = page
        self.state = state
        self.service = service
        self.snack = snack
        self._on_open_notes = on_open_notes
        self.pending_details: Dict[str, Any] = {
            "estimated_minutes": state.default_estimated_minutes,
            "due_date": None,       # None = use nav-based default at submit time
            "project_id": None,     # None = use sidebar-based default at submit time
        }
        self._section_label: ft.Text = None  # Will be set in _build_controls
        self._done_section: ft.Column = None  # Will be set in _build_controls
        self._build_controls()

    def _build_controls(self) -> None:
        # Tappable card linking to Notes page — shown in empty state
        self._note_card = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.EDIT_NOTE, color=COLORS["accent"], size=20),
                    ft.Text(t("tap_to_write"), size=14, color=COLORS["done_text"]),
                    ft.Container(expand=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=COLORS["done_text"]),
                ],
            ),
            padding=ft.Padding.symmetric(horizontal=16, vertical=14),
            border_radius=8,
            bgcolor=COLORS["card"],
            on_click=self._open_notes,
            ink=True,
            visible=False,
        )

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
                    self._note_card,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=ft.Alignment(0, 0),
            padding=ft.Padding.only(top=40, left=10, right=10, bottom=10),
            visible=False,
        )

        self.task_list = ft.ReorderableListView(
            show_default_drag_handles=False, 
            on_reorder=self._on_reorder, 
            controls=[], 
        ) 

        self.done_list = ft.Column(controls=[], spacing=8)
        self.overdue_list = ft.Column(controls=[], spacing=8)

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
            padding=ft.Padding.symmetric(horizontal=12, vertical=10),
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

        self._today_chip = ft.Container(
            content=ft.Text(t("today"), size=13, weight="bold", color="white"),
            bgcolor=COLORS["accent"],
            border_radius=20,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            on_click=lambda e: self._on_filter_change("today"),
            ink=True,
        )
        self._next_chip = ft.Container(
            content=ft.Text(t("next"), size=13, color=COLORS["done_text"]),
            bgcolor=COLORS["card"],
            border_radius=20,
            padding=ft.Padding.symmetric(horizontal=16, vertical=8),
            on_click=lambda e: self._on_filter_change("next"),
            ink=True,
        )
        self._filter_toggle = ft.Row(
            [self._today_chip, self._next_chip],
            spacing=8,
        )

    def _on_filter_change(self, value: str) -> None:
        """Handle Today/Next chip toggle."""
        if value == "next":
            self.state.task_filter = TaskFilter.NEXT
        else:
            self.state.task_filter = TaskFilter.TODAY
        self._update_chip_styles()
        self.refresh()

    def _update_chip_styles(self) -> None:
        """Sync chip colours with the current filter state."""
        is_today = self.state.task_filter == TaskFilter.TODAY
        self._today_chip.bgcolor = COLORS["accent"] if is_today else COLORS["card"]
        self._today_chip.content.color = "white" if is_today else COLORS["done_text"]
        self._today_chip.content.weight = "bold" if is_today else None
        self._next_chip.bgcolor = COLORS["accent"] if not is_today else COLORS["card"]
        self._next_chip.content.color = "white" if not is_today else COLORS["done_text"]
        self._next_chip.content.weight = "bold" if not is_today else None

    def _open_notes(self, e: ft.ControlEvent) -> None:
        """Navigate to the Notes page."""
        if self._on_open_notes:
            self._on_open_notes()

    def _get_default_due_date(self) -> Optional[date]:
        """Determine default due date based on current navigation view."""
        if self.state.selected_nav == NavItem.TODAY:
            if self.state.task_filter == TaskFilter.NEXT:
                return date.today() + timedelta(days=7)
            return date.today()
        return None

    async def _on_submit(self, e: ft.ControlEvent) -> None:
        """Handle task submission - async for direct DB access."""
        title = self.task_input.value.strip()
        if not title:
            return

        project_id = self.pending_details.get("project_id")
        if project_id is None:
            project_id = (
                list(self.state.selected_projects)[0]
                if len(self.state.selected_projects) == 1 else None
            )

        due_date = self.pending_details.get("due_date")
        if due_date is None:
            due_date = self._get_default_due_date()

        task = await self.service.add_task(
            title=title,
            project_id=project_id,
            estimated_seconds=self.pending_details["estimated_minutes"] * 60,
            due_date=due_date,
        )
        event_bus.emit(AppEvent.TASK_CREATED, task)

        self.pending_details = {
            "estimated_minutes": self.state.default_estimated_minutes,
            "due_date": None,
            "project_id": None,
        }
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
        # --- State for selections within dialog ---
        selected_due: Dict[str, Any] = {"value": self.pending_details.get("due_date")}
        selected_proj: Dict[str, Any] = {"value": self.pending_details.get("project_id")}

        # ── Due date section ──────────────────────────────────────────────
        date_chips_row = ft.Row(wrap=True, spacing=6, run_spacing=6)

        def _due_chip_style(is_selected: bool) -> dict:
            if is_selected:
                return {
                    "bgcolor": COLORS["accent"],
                    "border": ft.Border.all(1, COLORS["accent"]),
                }
            return {
                "bgcolor": COLORS["card"],
                "border": ft.Border.all(1, COLORS["border"]),
            }

        def _make_date_chip(label: str, value: Any, is_selected: bool) -> ft.Container:
            style = _due_chip_style(is_selected)
            text_color = COLORS["white"] if is_selected else None
            return ft.Container(
                content=ft.Text(label, size=13, color=text_color),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=BORDER_RADIUS,
                bgcolor=style["bgcolor"],
                border=style["border"],
                on_click=lambda ev, v=value: _select_date(v),
                ink=True,
            )

        def _rebuild_date_chips() -> None:
            today = date.today()
            cur = selected_due["value"]
            presets = [
                (t("none_date"), "none"),
                (t("today"), today),
                (t("tomorrow"), today + timedelta(days=1)),
                (t("next_week"), today + timedelta(days=7)),
                (t("custom_date"), "custom"),
            ]
            date_chips_row.controls.clear()
            for lbl, val in presets:
                if val == "none":
                    is_sel = cur is None
                elif val == "custom":
                    is_sel = (
                        cur is not None
                        and cur != today
                        and cur != today + timedelta(days=1)
                        and cur != today + timedelta(days=7)
                    )
                    if is_sel:
                        lbl = cur.strftime("%b %d")
                else:
                    is_sel = cur == val
                date_chips_row.controls.append(_make_date_chip(lbl, val, is_sel))

        def _select_date(value: Any) -> None:
            if value == "none":
                selected_due["value"] = None
                _rebuild_date_chips()
                self.page.update()
            elif value == "custom":
                picker = get_date_picker(self.page)
                picker.value = selected_due["value"] or date.today()

                def _on_pick(ev: ft.ControlEvent) -> None:
                    if ev.control.value:
                        selected_due["value"] = ev.control.value.date()
                        _rebuild_date_chips()
                        self.page.update()

                picker.on_change = _on_pick
                picker.open = True
                self.page.update()
            else:
                selected_due["value"] = value
                _rebuild_date_chips()
                self.page.update()

        _rebuild_date_chips()

        # ── Project section ───────────────────────────────────────────────
        project_chips_row = ft.Row(wrap=True, spacing=6, run_spacing=6)

        def _make_project_chip(label: str, pid: Optional[str], color: Optional[str],
                               is_selected: bool) -> ft.Container:
            style = _due_chip_style(is_selected)
            text_color = COLORS["white"] if is_selected else None
            controls = []
            if color:
                controls.append(
                    ft.Container(width=10, height=10, bgcolor=color, border_radius=5)
                )
            controls.append(ft.Text(label, size=13, color=text_color))
            return ft.Container(
                content=ft.Row(controls, spacing=6),
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=BORDER_RADIUS,
                bgcolor=style["bgcolor"],
                border=style["border"],
                on_click=lambda ev, p=pid: _select_project(p),
                ink=True,
            )

        def _rebuild_project_chips() -> None:
            cur = selected_proj["value"]
            project_chips_row.controls.clear()
            project_chips_row.controls.append(
                _make_project_chip(t("no_project"), None, None, cur is None)
            )
            for p in self.state.projects:
                project_chips_row.controls.append(
                    _make_project_chip(p.name, p.id, p.color, cur == p.id)
                )

        def _select_project(pid: Optional[str]) -> None:
            selected_proj["value"] = pid
            _rebuild_project_chips()
            self.page.update()

        # Pre-select: explicit pending value, else sidebar default
        if selected_proj["value"] is None and len(self.state.selected_projects) == 1:
            selected_proj["value"] = list(self.state.selected_projects)[0]
        _rebuild_project_chips()

        # ── Estimated time section (unchanged logic) ──────────────────────
        time_label = ft.Text(
            format_duration(self.pending_details["estimated_minutes"]),
            size=16,
            weight="bold",
        )

        def on_slider(ev: ft.ControlEvent) -> None:
            time_label.value = format_duration(int(ev.control.value) * DURATION_SLIDER_STEP)
            time_label.update()

        slider = ft.Slider(
            min=DURATION_SLIDER_MIN,
            max=DURATION_SLIDER_MAX,
            divisions=DURATION_SLIDER_MAX - DURATION_SLIDER_MIN,
            value=self.pending_details["estimated_minutes"] // DURATION_SLIDER_STEP,
            on_change=on_slider,
        )

        # ── Save handler ──────────────────────────────────────────────────
        def save(ev: ft.ControlEvent) -> None:
            self.pending_details["due_date"] = selected_due["value"]
            self.pending_details["project_id"] = selected_proj["value"]
            self.pending_details["estimated_minutes"] = int(slider.value) * DURATION_SLIDER_STEP
            self.details_btn.content.controls[1].value = t("add_details")
            close()
            self.page.update()

        # ── Dialog content ────────────────────────────────────────────────
        content = ft.Container(
            width=DIALOG_WIDTH_LG,
            content=ft.Column(
                [
                    ft.Text(t("due_date"), weight="bold", size=14),
                    date_chips_row,
                    ft.Divider(height=10, color="transparent"),
                    ft.Text(t("assign_to_project"), weight="bold", size=14),
                    project_chips_row,
                    ft.Divider(height=10, color="transparent"),
                    ft.Text(t("estimated_time"), weight="bold", size=14),
                    ft.Row(
                        [ft.Icon(ft.Icons.TIMER, size=18), time_label],
                        spacing=8,
                    ),
                    slider,
                    ft.Text(
                        t("time_range_hint"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=8,
                tight=True,
                scroll=ft.ScrollMode.AUTO,
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

        # Partition overdue tasks only for TODAY filter
        is_today_view = (
            self.state.selected_nav == NavItem.TODAY
            and self.state.task_filter == TaskFilter.TODAY
        )
        if is_today_view:
            overdue_tasks = [task for task in pending if TaskPresenter.is_overdue(task.due_date)]
            today_tasks = [task for task in pending if not TaskPresenter.is_overdue(task.due_date)]
        else:
            overdue_tasks = []
            today_tasks = pending

        # Populate overdue section
        self.overdue_list.controls.clear()
        for task in overdue_tasks:
            project = self.state.get_project_by_id(task.project_id)
            self.overdue_list.controls.append(TaskTile(task, False, self.state, project).build())

        if self._overdue_section is not None:
            self._overdue_section.visible = len(overdue_tasks) > 0
            if overdue_tasks:
                self._overdue_label.value = t("section_overdue_count").replace(
                    "{count}", str(len(overdue_tasks))
                )

        # Populate today/main task list
        self.task_list.controls.clear()
        for task in today_tasks:
            project = self.state.get_project_by_id(task.project_id)
            tile_container = ft.Container(
                content=TaskTile(task, False, self.state, project).build(),
                data=task.id,
            )
            self.task_list.controls.append(tile_container)

        self.done_list.controls.clear()
        for task in done:
            project = self.state.get_project_by_id(task.project_id)
            self.done_list.controls.append(TaskTile(task, True, self.state, project).build())

        # Show empty state only when there are no pending tasks at all in Today filter
        show_empty = (
            len(pending) == 0
            and self.state.selected_nav == NavItem.TODAY
            and self.state.task_filter == TaskFilter.TODAY
        )
        self.empty_state.visible = show_empty
        self._note_card.visible = show_empty

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
        empty_col = self.empty_state.content
        empty_col.controls[1].value = t("all_caught_up")
        empty_col.controls[2].value = t("enjoy_your_day")

        # Update filter chip labels
        self._today_chip.content.value = t("today")
        self._next_chip.content.value = t("next")

        # Update overdue section label
        if hasattr(self, '_overdue_label') and self._overdue_label is not None:
            self._overdue_label.value = t("section_overdue")

        # Update notes card text
        self._note_card.content.controls[1].value = t("tap_to_write")

    def _get_section_label(self) -> str:
        """Get the appropriate section label based on current navigation."""
        nav = self.state.selected_nav
        if nav == NavItem.TODAY:
            if self.state.task_filter == TaskFilter.NEXT:
                return t("section_next")
            return t("section_today")
        elif nav == NavItem.INBOX:
            return t("section_inbox")
        elif nav == NavItem.PROJECTS:
            return t("section_tasks")
        return t("section_tasks")

    def _should_show_done_section(self) -> bool:
        """Determine if the done section should be visible."""
        # Show done section for all task views
        return True

    def build(self) -> ft.Column:
        self._section_label = ft.Text(self._get_section_label(), color="grey", weight="bold")

        # Sync chip styles with current state
        self._update_chip_styles()

        # Only show filter toggle in Tasks (TODAY) nav
        show_toggle = self.state.selected_nav == NavItem.TODAY
        self._filter_row = ft.Container(
            content=self._filter_toggle,
            visible=show_toggle,
            padding=ft.Padding.only(bottom=8),
        )

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

        self._overdue_label = ft.Text(
            t("section_overdue"),
            color=COLORS["danger"],
            weight="bold",
        )
        self._overdue_section = ft.Column(
            controls=[
                ft.Row(
                    [
                        ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, size=16, color=COLORS["danger"]),
                        self._overdue_label,
                    ],
                    spacing=8,
                ),
                self.overdue_list,
                ft.Divider(height=15, color="transparent"),
            ],
            visible=False,
        )

        return ft.Column(
            alignment=ft.MainAxisAlignment.START,
            controls=[
                ft.Row(
                    controls=[self.task_input, self.details_btn, self.submit_btn],
                    spacing=10,
                ),
                self._filter_row,
                ft.Divider(height=15, color="transparent"),
                self._overdue_section,
                self._section_label,
                self.empty_state,
                self.task_list,
                ft.Divider(height=25, color="transparent"),
                self._done_section,
            ],
            scroll=ft.ScrollMode.AUTO,
        )