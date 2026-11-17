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
    SPACING_XS,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    SPACING_2XL,
    SPACING_3XL,
)
from i18n import t
from models.entities import AppState
from services.logic import TaskService
from ui.helpers import format_duration, accent_btn, SnackService
from ui.components.task_tile import TaskTile
from ui.presenters.task_presenter import TaskPresenter
from ui.dialogs.base import open_dialog, create_option_item
from ui.dialogs.task_dialogs import get_date_picker
from events import event_bus, AppEvent


_UNSET = object()


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
            "estimated_minutes": 0,
            "due_date": _UNSET,
            "project_id": _UNSET,
        }
        self._section_label: ft.Text = None  # Will be set in _build_controls
        self._done_section: ft.Column = None  # Will be set in _build_controls
        self._quick_chips: Optional[ft.Row] = None
        self._quick_due_text: Optional[ft.Text] = None
        self._quick_project_text: Optional[ft.Text] = None
        self._build_controls()

    def _build_controls(self) -> None:
        # Tappable card linking to Notes page — shown in empty state
        self._note_card_text = ft.Text(t("tap_to_write"), size=14, color=COLORS["done_text"])
        self._note_card = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.EDIT_NOTE, color=COLORS["accent"], size=20),
                    self._note_card_text,
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

        self._empty_icon = ft.Icon(
            ft.Icons.CHECK_CIRCLE_OUTLINE,
            size=64,
            color=COLORS["done_text"],
        )
        self._empty_title = ft.Text(
            t("all_caught_up"),
            size=20,
            weight="bold",
            color=COLORS["done_text"],
        )
        self._empty_subtitle = ft.Text(
            t("enjoy_your_day"),
            size=14,
            color=COLORS["done_text"],
        )
        self.empty_state = ft.Container(
            content=ft.Column(
                [
                    self._empty_icon,
                    self._empty_title,
                    self._empty_subtitle,
                    self._note_card,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_LG,
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

        self.done_list = ft.Column(controls=[], spacing=SPACING_MD)
        self.overdue_list = ft.Column(controls=[], spacing=SPACING_MD)

        self.details_btn = ft.IconButton(
            icon=ft.Icons.TUNE,
            tooltip=t("add_details"),
            on_click=self._open_details,
            visible=False,
        )

        self.task_input = ft.TextField(
            dense=self.state.is_mobile,
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
            spacing=SPACING_MD,
        )

    def _on_filter_change(self, value: str) -> None:
        """Handle Today/Next chip toggle."""
        if value == "next":
            self.state.task_filter = TaskFilter.NEXT
        else:
            self.state.task_filter = TaskFilter.TODAY
        self._update_chip_styles()
        self._refresh_quick_labels()
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
        """Capturing a title does not silently schedule it."""
        return None

    async def _on_submit(self, e: ft.ControlEvent) -> None:
        """Handle task submission - async for direct DB access."""
        title = self.task_input.value.strip()
        if not title:
            return

        project_id = self._resolved_project()
        due_date = self._resolved_due_date()

        task = await self.service.add_task(
            title=title,
            project_id=project_id,
            estimated_seconds=self.pending_details["estimated_minutes"] * 60,
            due_date=due_date,
        )
        event_bus.emit(AppEvent.TASK_CREATED, task)
        if due_date is None and self.state.selected_nav != NavItem.INBOX:
            self.snack.show(t("task_moved_to_draft"))

        self.pending_details = {
            "estimated_minutes": 0,
            "due_date": _UNSET,
            "project_id": _UNSET,
        }
        self.task_input.value = ""
        self.details_btn.visible = False
        if self._quick_chips is not None:
            self._quick_chips.visible = False
            self._capture_options.visible = False
        self._refresh_quick_labels()
        self.refresh()

    def _on_change(self, e: ft.ControlEvent) -> None:
        has_text = bool(self.task_input.value.strip())
        self.details_btn.visible = has_text
        if self._quick_chips is not None:
            self._quick_chips.visible = has_text
            self._capture_options.visible = has_text
        self.page.update()

    # ── Inline quick chips (Due / Project) on the add bar ────────────────────
    def _resolved_due_date(self):
        value = self.pending_details.get("due_date", _UNSET)
        return self._get_default_due_date() if value is _UNSET else value

    def _resolved_project(self):
        value = self.pending_details.get("project_id", _UNSET)
        if value is _UNSET:
            return next(iter(self.state.selected_projects), None)
        return value

    def _quick_due_label(self) -> str:
        d = self._resolved_due_date()
        if d is None:
            return t("none_date")
        today = date.today()
        if d == today:
            return t("today")
        if d == today + timedelta(days=1):
            return t("tomorrow")
        if d == today + timedelta(days=7):
            return t("next_week")
        return d.strftime("%b %d")

    def _quick_project_label(self) -> str:
        pid = self._resolved_project()
        if pid is None:
            return t("no_project")
        p = self.state.get_project_by_id(pid)
        return p.name if p else t("quick_project")

    def _refresh_quick_labels(self) -> None:
        if self._quick_due_text is not None:
            self._quick_due_text.value = self._quick_due_label()
        if self._quick_project_text is not None:
            self._quick_project_text.value = self._quick_project_label()

    def _set_quick_due(self, value: Any) -> None:
        if value == "custom":
            picker = get_date_picker(self.page)
            picker.value = self._resolved_due_date() or date.today()

            def _on_pick(ev: ft.ControlEvent) -> None:
                v = ev.control.value
                if v is not None:
                    self.pending_details["due_date"] = v.date() if hasattr(v, "date") else v
                    self._refresh_quick_labels()
                    self.page.update()

            picker.on_change = _on_pick
            picker.open = True
            self.page.update()
            return
        self.pending_details["due_date"] = value  # None or a date
        self._refresh_quick_labels()
        self.page.update()

    def _set_quick_project(self, pid: Optional[str]) -> None:
        self.pending_details["project_id"] = pid
        self._refresh_quick_labels()
        self.page.update()

    def _chip(self, icon: str, text_ctrl: ft.Text, items: list) -> ft.PopupMenuButton:
        chip = ft.Container(
            content=ft.Row(
                [ft.Icon(icon, size=14, color=COLORS["accent"]), text_ctrl,
                 ft.Icon(ft.Icons.ARROW_DROP_DOWN, size=14, color=COLORS["accent"])],
                spacing=SPACING_XS, tight=True,
            ),
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=BORDER_RADIUS,
            bgcolor=COLORS["card"],
        )
        return ft.PopupMenuButton(content=chip, items=items, menu_position=ft.PopupMenuPosition.UNDER)

    def _build_quick_chips(self) -> ft.Row:
        today = date.today()
        self._quick_due_text = ft.Text(self._quick_due_label(), size=12, color=COLORS["accent"])
        self._quick_project_text = ft.Text(self._quick_project_label(), size=12, color=COLORS["accent"])

        due_items = [
            create_option_item(ft.Icons.BLOCK, t("none_date"), lambda e: self._set_quick_due(None), as_popup=True),
            create_option_item(ft.Icons.TODAY, t("today"), lambda e: self._set_quick_due(today), as_popup=True),
            create_option_item(ft.Icons.CALENDAR_TODAY, t("tomorrow"),
                               lambda e: self._set_quick_due(today + timedelta(days=1)), as_popup=True),
            create_option_item(ft.Icons.DATE_RANGE, t("next_week"),
                               lambda e: self._set_quick_due(today + timedelta(days=7)), as_popup=True),
            create_option_item(ft.Icons.CALENDAR_MONTH, t("custom_date"),
                               lambda e: self._set_quick_due("custom"), as_popup=True),
        ]
        proj_items = [
            create_option_item(ft.Icons.CLOSE, t("no_project"), lambda e: self._set_quick_project(None), as_popup=True),
        ]
        for p in self.state.projects:
            proj_items.append(
                create_option_item(ft.Icons.FOLDER, p.name,
                                   lambda e, pid=p.id: self._set_quick_project(pid), as_popup=True)
            )

        return ft.Row(
            [self._chip(ft.Icons.EVENT, self._quick_due_text, due_items),
             self._chip(ft.Icons.FOLDER_OUTLINED, self._quick_project_text, proj_items),
             self.details_btn],
            spacing=SPACING_SM, wrap=True,
        )

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

        # Apply the reorder to get the desired visible order
        moved_id = ui_task_ids.pop(old_idx)
        ui_task_ids.insert(new_idx, moved_id)

        # Persist globally so hidden tasks can't collide with this view's order.
        await self.service.reorder_visible_tasks(ui_task_ids)

        # Refresh UI from DB
        self.refresh()

    def _open_details(self, e: ft.ControlEvent) -> None:
        # --- State for selections within dialog ---
        selected_due: Dict[str, Any] = {"value": self._resolved_due_date()}
        selected_proj: Dict[str, Any] = {"value": self._resolved_project()}

        # ── Due date section ──────────────────────────────────────────────
        date_chips_row = ft.Row(wrap=True, spacing=SPACING_SM, run_spacing=SPACING_SM)

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
                        value = ev.control.value
                        selected_due["value"] = value.date() if hasattr(value, "date") else value
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
        project_chips_row = ft.Row(wrap=True, spacing=SPACING_SM, run_spacing=SPACING_SM)

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
                content=ft.Row(controls, spacing=SPACING_SM),
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

        _rebuild_project_chips()

        # ── Estimated time section (unchanged logic) ──────────────────────
        time_label = ft.Text(
            format_duration(self.pending_details["estimated_minutes"]) if self.pending_details["estimated_minutes"] else t("not_estimated"),
            size=16,
            weight="bold",
        )

        def on_slider(ev: ft.ControlEvent) -> None:
            time_label.value = format_duration(int(ev.control.value) * DURATION_SLIDER_STEP) if ev.control.value else t("not_estimated")
            time_label.update()

        slider = ft.Slider(
            min=0,
            max=DURATION_SLIDER_MAX,
            divisions=DURATION_SLIDER_MAX,
            value=self.pending_details["estimated_minutes"] // DURATION_SLIDER_STEP,
            on_change=on_slider,
        )

        # ── Save handler ──────────────────────────────────────────────────
        def save(ev: ft.ControlEvent) -> None:
            self.pending_details["due_date"] = selected_due["value"]
            self.pending_details["project_id"] = selected_proj["value"]
            self.pending_details["estimated_minutes"] = int(slider.value) * DURATION_SLIDER_STEP
            self._refresh_quick_labels()
            close()
            self.page.update()

        # ── Dialog content ────────────────────────────────────────────────
        content = ft.Container(
            width=DIALOG_WIDTH_LG,
            content=ft.Column(
                [
                    ft.Text(t("due_date"), weight="bold", size=14),
                    date_chips_row,
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    ft.Text(t("assign_to_project"), weight="bold", size=14),
                    project_chips_row,
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    ft.Text(t("estimated_time"), weight="bold", size=14),
                    ft.Row(
                        [ft.Icon(ft.Icons.TIMER, size=18), time_label],
                        spacing=SPACING_MD,
                    ),
                    slider,
                    ft.Text(
                        t("time_range_hint"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                ],
                spacing=SPACING_MD,
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
        self._refresh_quick_labels()

        # Update section label based on current navigation
        if self._section_label is not None:
            self._section_label.value = self._get_section_label()
            self._clear_filter_button.visible = bool(self.state.selected_projects)

        # Update done section visibility
        if self._done_section is not None:
            self._done_section.visible = bool(done)

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

        # Show empty state when there are no pending tasks in any view
        show_empty = len(pending) == 0
        self.empty_state.visible = show_empty

        if show_empty:
            icon, title, subtitle = self._get_empty_state_content()
            self._empty_icon.name = icon
            self._empty_title.value = title
            self._empty_subtitle.value = subtitle

        is_today = (
            self.state.selected_nav == NavItem.TODAY
            and self.state.task_filter == TaskFilter.TODAY
        )
        self._note_card.visible = show_empty and is_today

        self.page.update()

    def set_mobile(self, is_mobile: bool) -> None:
        self.submit_btn.visible = is_mobile

    def update_translations(self) -> None:
        """Update all translatable text in the view."""
        # Update task input hint
        self.task_input.hint_text = t("add_new_task")

        # Update details button text and tooltip
        self.details_btn.tooltip = t("add_details_tooltip")

        # Update empty state text (context-dependent, refresh will set the right values)
        if self.empty_state.visible:
            icon, title, subtitle = self._get_empty_state_content()
            self._empty_icon.name = icon
            self._empty_title.value = title
            self._empty_subtitle.value = subtitle

        # Update filter chip labels
        self._today_chip.content.value = t("today")
        self._next_chip.content.value = t("next")

        # Update overdue section label
        if hasattr(self, '_overdue_label') and self._overdue_label is not None:
            self._overdue_label.value = t("section_overdue")

        # Update notes card text
        self._note_card_text.value = t("tap_to_write")

    def _get_empty_state_content(self) -> tuple:
        """Return (icon_name, title, subtitle) for the empty state based on current nav."""
        nav = self.state.selected_nav
        if nav == NavItem.INBOX:
            return ft.Icons.DRAFTS_OUTLINED, t("inbox_empty"), t("inbox_empty_hint")
        if nav == NavItem.PROJECTS:
            return ft.Icons.FOLDER_OUTLINED, t("project_empty"), t("project_empty_hint")
        return ft.Icons.CHECK_CIRCLE_OUTLINE, t("all_caught_up"), t("enjoy_your_day")

    def _get_section_label(self) -> str:
        if self.state.selected_nav == NavItem.TODAY:
            label = t("section_next") if self.state.task_filter == TaskFilter.NEXT else t("section_today")
        elif self.state.selected_nav == NavItem.INBOX:
            label = t("section_inbox")
        else:
            label = t("section_tasks")
        projects = [p.name for p in self.state.projects if p.id in self.state.selected_projects]
        return " · ".join([label, *projects])

    def _should_show_done_section(self) -> bool:
        """Hide empty completion sections."""
        return bool(self.done_list.controls)

    def _clear_project_filter(self, e=None) -> None:
        self.state.selected_projects.clear()
        event_bus.emit(AppEvent.SIDEBAR_REBUILD)
        self.refresh()

    def build(self) -> ft.Column:
        self._section_label = ft.Text(self._get_section_label(), color=COLORS["grey"], weight="bold")
        self._clear_filter_button = ft.IconButton(
            ft.Icons.CLOSE, tooltip=t("clear_project_filter"),
            on_click=self._clear_project_filter,
            visible=bool(self.state.selected_projects),
        )

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
                    spacing=SPACING_MD,
                ),
                ft.Divider(height=SPACING_LG, color="transparent"),
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
                    spacing=SPACING_MD,
                ),
                self.overdue_list,
                ft.Divider(height=SPACING_2XL, color="transparent"),
            ],
            visible=False,
        )

        # Inline quick chips (Due / Project), shown only while typing a new task.
        self._quick_chips = self._build_quick_chips()
        self._quick_chips.visible = bool(self.task_input.value.strip())
        self._capture_options = ft.Container(
            content=self._quick_chips,
            visible=bool(self.task_input.value.strip()),
            padding=ft.Padding.only(top=6, bottom=2),
        )

        return ft.Column(
            alignment=ft.MainAxisAlignment.START,
            controls=[
                ft.Row(
                    controls=[self.task_input, self.submit_btn],
                    spacing=SPACING_LG,
                ),
                self._capture_options,
                self._filter_row,
                ft.Divider(height=SPACING_XS, color="transparent"),
                self._overdue_section,
                ft.Row([self._section_label, self._clear_filter_button],
                    visible=not (self.state.is_mobile and show_toggle)),
                self.empty_state,
                self.task_list,
                ft.Divider(height=SPACING_SM, color="transparent"),
                self._done_section,
            ],
            scroll=ft.ScrollMode.AUTO,
            spacing=6 if self.state.is_mobile else 10,
            expand=True,
        )
