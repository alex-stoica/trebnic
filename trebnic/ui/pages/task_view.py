import flet as ft
from typing import Dict, Any 

from config import (
    COLORS,
    BORDER_RADIUS,
    NAV_TODAY,
    DURATION_SLIDER_STEP,
    DURATION_SLIDER_MIN,
    DURATION_SLIDER_MAX,
    DIALOG_WIDTH_MD,
) 
from models.entities import AppState
from services.logic import TaskService
from ui.controller import UIController
from ui.helpers import format_duration, accent_btn, SnackService
from ui.components.task_tile import TaskTile
from ui.dialogs.base import open_dialog


class TasksView:
    def __init__(
        self, 
        page: ft.Page, 
        state: AppState, 
        service: TaskService, 
        ctrl: UIController, 
        snack: SnackService, 
    ) -> None: 
        self.page = page
        self.state = state
        self.service = service
        self.ctrl = ctrl
        self.snack = snack
        self.pending_details: Dict[str, Any] = { 
            "estimated_minutes": state.default_estimated_minutes
        } 
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
                        "All caught up!", 
                        size=20, 
                        weight="bold", 
                        color=COLORS["done_text"], 
                    ), 
                    ft.Text( 
                        "Enjoy your day!", 
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
                    ft.Text("Add details", size=13, color=COLORS["accent"]), 
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
            tooltip="Click to add tags, due date, and more",
            on_click=self._open_details,
        ) 

        self.task_input = ft.TextField(
            hint_text="Add a new task...", 
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

    def _on_submit(self, e: ft.ControlEvent) -> None: 
        title = self.task_input.value.strip()
        if not title:
            return

        project_id = (
            list(self.state.selected_projects)[0] 
            if len(self.state.selected_projects) == 1 else None 
        ) 

        self.service.add_task(
            title=title, 
            project_id=project_id, 
            estimated_seconds=self.pending_details["estimated_minutes"] * 60, 
        ) 

        self.pending_details["estimated_minutes"] = self.state.default_estimated_minutes
        self.details_btn.content.controls[1].value = "Add details"
        self.task_input.value = ""
        self.details_btn.visible = False
        self.refresh()

    def _on_change(self, e: ft.ControlEvent) -> None: 
        self.details_btn.visible = bool(self.task_input.value.strip())
        self.page.update()

    def _on_reorder(self, e: ft.OnReorderEvent) -> None: 
        old_idx, new_idx = e.old_index, e.new_index
        if old_idx < new_idx:
            new_idx -= 1

        filtered, _ = self.service.get_filtered_tasks()
        if not filtered or old_idx >= len(filtered):
            return

        task = filtered[old_idx]
        self.state.tasks.remove(task)

        if new_idx == 0:
            self.state.tasks.insert(0, task)
        else:
            temp = list(filtered)
            temp.pop(old_idx)
            temp.insert(new_idx, task)
            anchor = temp[new_idx - 1]
            self.state.tasks.insert(self.state.tasks.index(anchor) + 1, task)

        self.service.persist_task_order()
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
            label="{value}", 
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
                    ft.Text("Estimated time", weight="bold", size=14), 
                    ft.Row( 
                        [ft.Icon(ft.Icons.TIMER, size=18), label], 
                        spacing=8, 
                    ), 
                    slider, 
                    ft.Text( 
                        "5 min - 8 hrs 20 min", 
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
            "Task details", 
            content, 
            lambda c: [ft.TextButton("Cancel", on_click=c), accent_btn("Save", save)], 
        ) 

    def refresh(self) -> None: 
        pending, done = self.service.get_filtered_tasks()

        self.task_list.controls.clear()
        for i, task in enumerate(pending):
            draggable = ft.ReorderableDraggable(
                index=i, 
                content=TaskTile(task, False, self.ctrl).build(), 
            ) 
            self.task_list.controls.append(draggable)

        self.done_list.controls.clear()
        for task in done:
            self.done_list.controls.append(TaskTile(task, True, self.ctrl).build())

        self.empty_state.visible = (
            len(pending) == 0 and self.state.selected_nav == NAV_TODAY 
        ) 
        self.page.update()

    def set_mobile(self, is_mobile: bool) -> None: 
        self.submit_btn.visible = is_mobile

    def build(self) -> ft.Column:
        return ft.Column(
            alignment=ft.MainAxisAlignment.START,
            controls=[
                ft.Row(
                    controls=[self.task_input, self.details_btn, self.submit_btn], 
                    spacing=10, 
                ), 
                ft.Divider(height=15, color="transparent"),
                ft.Text("TODAY", color="grey", weight="bold"),
                self.empty_state,
                self.task_list,
                ft.Divider(height=25, color="transparent"),
                ft.Row(
                    [ 
                        ft.Icon( 
                            ft.Icons.CHECK_CIRCLE, 
                            size=16, 
                            color=COLORS["done_text"], 
                        ), 
                        ft.Text( 
                            "DONE", 
                            color=COLORS["done_text"], 
                            weight="bold", 
                        ), 
                    ], 
                    spacing=8,
                ), 
                ft.Divider(height=10, color="transparent"),
                self.done_list,
            ], 
            scroll=ft.ScrollMode.AUTO,
        ) 