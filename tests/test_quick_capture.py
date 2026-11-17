from datetime import date, timedelta
from unittest.mock import Mock, AsyncMock

import flet as ft
import pytest

from config import NavItem, TaskFilter
from events import event_bus
from formatters import TimeFormatter
from models.entities import AppState, Task, Project
from ui.pages.task_view import TasksView
from ui.components.task_tile import TaskTile
from ui.components.timer_widget import TimerWidget
from ui.navigation import NavigationManager


@pytest.fixture
def view():
    event_bus.clear()
    state = AppState()
    state.is_mobile = True
    state.selected_nav = NavItem.TODAY
    state.task_filter = TaskFilter.TODAY
    state.projects = [Project("work", "Work", "folder", "blue")]
    svc = Mock()
    svc.get_filtered_tasks = AsyncMock(return_value=([], []))
    svc.add_task = AsyncMock(return_value=Task("Example",0,900,None,None,id=1))
    page, snack = Mock(), Mock()
    result = TasksView(page, state, svc, snack)
    result.build()
    yield result
    event_bus.clear()


async def test_no_date_and_no_project_override_view_defaults(view):
    view.state.selected_projects = {"work"}
    assert view._resolved_due_date() is None
    assert view._resolved_project() == "work"
    view._set_quick_due(None)
    view._set_quick_project(None)
    view.task_input.value = "Example"
    await view._on_submit(None)
    kwargs = view.service.add_task.await_args.kwargs
    assert kwargs["due_date"] is None
    assert kwargs["project_id"] is None
    view.snack.show.assert_called_once()


def test_upcoming_capture_does_not_invent_a_due_date(view):
    view._on_filter_change("next")
    assert view._resolved_due_date() is None
    assert view._quick_due_text.value == view._quick_due_label()
    assert view.pending_details["estimated_minutes"] == 0


def test_typing_keeps_input_row_full_width(view):
    controls = view.build().controls
    assert controls[0].controls == [view.task_input, view.submit_btn]
    assert not view._capture_options.visible
    view.task_input.value = "Example"
    view._on_change(None)
    assert view._capture_options.visible
    assert view.details_btn in view._quick_chips.controls


async def test_empty_done_section_is_hidden_and_filter_can_be_cleared(view):
    view.state.selected_projects = {"work"}
    await view._refresh_async()
    assert "Work" in view._section_label.value
    assert view._clear_filter_button.visible
    assert not view._done_section.visible
    view._clear_project_filter()
    assert not view.state.selected_projects


def test_navigation_drops_hidden_project_filter(view):
    view.state.selected_projects = {"work"}
    nav = NavigationManager(view.page,view.state)
    nav.select_nav(NavItem.TODAY)
    assert not view.state.selected_projects


def test_mobile_task_has_direct_play_and_no_redundant_tags(view):
    task = Task("Example",0,900,None,date.today(),id=1)
    tile = TaskTile(task,False,view.state).build()
    row,summary = tile.content.controls
    assert "15 min" in summary.value
    assert any(isinstance(c,ft.IconButton) and c.icon == ft.Icons.PLAY_ARROW for c in row.controls)
    assert TaskTile(task, False, view.state).display.due_date_display not in summary.value


def test_stop_is_an_explicit_button_and_short_time_is_visible():
    handler = Mock()
    widget = TimerWidget(handler)
    assert widget.on_click is None
    assert widget.stop_button.on_click is handler
    assert widget.stop_button.icon == ft.Icons.STOP
    assert TimeFormatter.seconds_to_display(20) == "20 s"


def test_timer_retains_native_position_across_ticks_and_restart():
    widget = TimerWidget(Mock())
    widget.movable.x, widget.movable.y = 48, 120
    surface = widget.movable
    widget.start("First task")
    widget.update_time(65)
    assert widget.display.value == "01:05"
    widget.stop()
    assert not widget.visible
    widget.start("Second task")
    assert widget.visible and widget.task_text.value == "Second task"
    assert widget.movable is surface
    assert (surface.x, surface.y) == (48, 120)
    assert surface.haptic and surface.long_press_duration == 0.5
    assert (surface.left, surface.top, surface.right, surface.bottom) == (0, 0, 0, 0)


def test_timer_tick_only_updates_text():
    from services.timer import TimerService
    from ui.timer_controller import TimerController

    widget = TimerWidget(Mock())
    widget.display.update = Mock()
    widget.update = Mock()
    controller = TimerController(Mock(), TimerService(), Mock(), widget)
    try:
        controller._on_tick(125)
        assert widget.display.value == "02:05"
        widget.display.update.assert_called_once_with()
        widget.update.assert_not_called()
    finally:
        controller.cleanup()
