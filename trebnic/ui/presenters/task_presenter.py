from dataclasses import dataclass 
from typing import Optional 
from datetime import date 

from config import COLORS 
from models.entities import Task, Project 


@dataclass 
class TaskDisplayData: 
    """Computed display data for a task, separating logic from presentation.""" 
    title: str 
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
    def get_display_title(task: Task) -> str: 
        """Get the display title with recurrence prefix if applicable.""" 
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
        minutes = seconds // 60 
        if minutes < 60: 
            return f"{minutes} min" 
        h, m = divmod(minutes, 60) 
        return f"{h}h" if m == 0 else f"{h}h {m}m" 

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
        return TaskDisplayData( 
            title=cls.get_display_title(task), 
            is_recurrent=task.recurrent, 
            project_name=project.name if project else None, 
            project_icon=project.icon if project else None, 
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