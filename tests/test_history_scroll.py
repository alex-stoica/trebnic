from datetime import date, datetime, timedelta
from unittest.mock import Mock
import flet as ft
from models.entities import AppState, Task
from ui.pages.calendar_view import CalendarView
from ui.pages.task_view import TasksView


def test_busy_day_uses_bounded_scroll_and_actual_completion_day():
    today = date.today()
    state = AppState()
    state.is_mobile = True
    state.done_tasks = [Task(f"Done {n}", 0, 0, None, today - timedelta(days=1),
                            id=n, completed_at=datetime.now()) for n in range(80)]
    view = CalendarView(Mock(), state, Mock(), Mock())
    assert len(view._get_tasks_for_date(today)[1]) == 80
    assert not view._get_tasks_for_date(today - timedelta(days=1))[1]
    day = view._create_day_column(today, today, True)
    viewport = day.content.controls[1]
    assert viewport.expand and isinstance(viewport.content, ft.ListView)
    assert len(viewport.content.controls) == 80
    assert viewport.on_click is None  # Dragging history must not open the notes dialog.
    root = view.build()
    assert root.expand and root.controls[1].content.vertical_alignment == ft.CrossAxisAlignment.STRETCH


def test_task_history_has_one_expanding_scroll_viewport():
    state = AppState()
    view = TasksView(Mock(), state, Mock(), Mock())
    view.done_list.controls = [ft.Text(f"Done {i}") for i in range(80)]
    root = view.build()
    assert root.expand and root.scroll == ft.ScrollMode.AUTO
    assert view._done_section.visible
    assert view.done_list.scroll is None
