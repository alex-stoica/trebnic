from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional, List

from config import RecurrenceFrequency
from models.entities import Task
from services.recurrence import calculate_next_recurrence_from_date


@dataclass
class RecurrenceState:
    """State for the recurrence dialog."""
    task: Task
    enabled: bool = False
    frequency: RecurrenceFrequency = RecurrenceFrequency.WEEKS
    interval: int = 1
    weekdays: List[bool] = field(default_factory=lambda: [False] * 7)
    end_type: str = "never"
    end_date: Optional[date] = None
    from_completion: bool = False

    @classmethod
    def from_task(cls, task: Task) -> "RecurrenceState":
        """Create state from an existing task."""
        weekdays = [i in task.recurrence_weekdays for i in range(7)]
        freq = (
            task.recurrence_frequency
            if isinstance(task.recurrence_frequency, RecurrenceFrequency)
            else RecurrenceFrequency.WEEKS
        )
        return cls(
            task=task,
            enabled=task.recurrent,
            frequency=freq,
            interval=task.recurrence_interval,
            weekdays=weekdays,
            end_type=task.recurrence_end_type,
            end_date=task.recurrence_end_date,
            from_completion=task.recurrence_from_completion,
        )

    def apply_to_task(self) -> None:
        """Apply state back to the task."""
        self.task.recurrent = self.enabled
        self.task.recurrence_frequency = self.frequency
        self.task.recurrence_interval = self.interval
        self.task.recurrence_weekdays = [i for i, v in enumerate(self.weekdays) if v]
        self.task.recurrence_end_type = self.end_type
        self.task.recurrence_end_date = self.end_date
        self.task.recurrence_from_completion = self.from_completion

        # When recurrence is enabled, update due_date to the next occurrence
        if self.enabled:
            # Calculate next occurrence from yesterday so today can be included if it matches
            base_date = date.today() - timedelta(days=1)
            next_date = calculate_next_recurrence_from_date(self.task, base_date)
            if next_date:
                self.task.due_date = next_date


@dataclass
class IconPickerState:
    """State for the icon picker in project dialog."""
    current_icon: str
    original_icon: str

    @classmethod
    def create(cls, icon: str) -> "IconPickerState":
        """Create a new icon picker state."""
        return cls(current_icon=icon, original_icon=icon)

    def select(self, icon: str) -> None:
        """Select a new icon."""
        self.current_icon = icon

    def confirm(self) -> str:
        """Confirm selection and return the icon."""
        return self.current_icon

    def cancel(self) -> str:
        """Cancel and return original icon."""
        return self.original_icon


@dataclass
class ColorPickerState:
    """State for the color picker in project dialog."""
    current_color: str
    original_color: str

    @classmethod
    def create(cls, color: str) -> "ColorPickerState":
        """Create a new color picker state."""
        return cls(current_color=color, original_color=color)

    def select(self, color: str) -> None:
        """Select a new color."""
        self.current_color = color

    def confirm(self) -> str:
        """Confirm selection and return the color."""
        return self.current_color