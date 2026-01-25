from dataclasses import dataclass
from typing import Optional
from datetime import date

from config import COLORS
from models.entities import Task, Project
from services.crypto import LOCKED_PLACEHOLDER
from ui.formatters import TimeFormatter


@dataclass
class TaskDisplayData:
    """Computed display data for a task, separating logic from presentation."""
    title: str
    is_locked: bool
    is_recurrent: bool
    project_name: Optional[str]
    project_icon: Optional[str]
    project_color: str
    due_date_display: Optional[str]
    is_overdue: bool
    spent_display: str
    estimated_display: str
    progress_percent: float
    remaining_seconds: int


class TaskPresenter:
    """Computes display values for tasks without rendering."""

    @staticmethod
    def is_locked(task: Task) -> bool:
        """Check if the task title is locked (encrypted but app not unlocked)."""
        return task.title == LOCKED_PLACEHOLDER

    @staticmethod
    def get_display_title(task: Task) -> str:
        """Get the display title with recurrence prefix if applicable."""
        if task.title == LOCKED_PLACEHOLDER:
            return task.title  # Don't add recurrence prefix to locked placeholder
        return f"↻ {task.title}" if task.recurrent else task.title

    @staticmethod
    def format_due_date(due_date: Optional[date]) -> Optional[str]:
        """Format due date for display with appropriate emoji."""
        if due_date is None:
            return None
        delta = (due_date - date.today()).days
        date_str = due_date.strftime("%b %d")
        if delta < 0:
            return f"🔴 {date_str}"
        elif delta == 0:
            return "📅 Today"
        elif delta == 1:
            return "📆 Tomorrow"
        elif delta <= 7:
            return f"🗓️ {date_str}"
        return f"📋 {date_str}"

    @staticmethod
    def is_overdue(due_date: Optional[date]) -> bool:
        """Check if task is overdue."""
        if due_date is None:
            return False
        return (due_date - date.today()).days < 0

    @staticmethod
    def seconds_to_display(seconds: int) -> str:
        """Convert seconds to human-readable display string."""
        return TimeFormatter.seconds_to_display(seconds)

    @staticmethod
    def calculate_progress(spent: int, estimated: int) -> float:
        """Calculate progress percentage."""
        if estimated <= 0:
            return 0.0
        return min(100.0, (spent / estimated) * 100)

    @classmethod
    def create_display_data(
        cls,
        task: Task,
        project: Optional[Project],
    ) -> TaskDisplayData:
        """Create complete display data for a task."""
        is_task_locked = cls.is_locked(task)
        # Project name may also be locked
        is_project_locked = project and project.name == LOCKED_PLACEHOLDER
        return TaskDisplayData(
            title=cls.get_display_title(task),
            is_locked=is_task_locked,
            is_recurrent=task.recurrent,
            project_name=project.name if project else None,
            project_icon=project.icon if project and not is_project_locked else None,
            project_color=project.color if project else COLORS["unassigned"],
            due_date_display=cls.format_due_date(task.due_date),
            is_overdue=cls.is_overdue(task.due_date),
            spent_display=cls.seconds_to_display(task.spent_seconds),
            estimated_display=cls.seconds_to_display(task.estimated_seconds),
            progress_percent=cls.calculate_progress(
                task.spent_seconds, task.estimated_seconds
            ),
            remaining_seconds=max(0, task.estimated_seconds - task.spent_seconds),
        )