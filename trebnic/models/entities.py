from dataclasses import dataclass, field
from typing import Optional, List, Set, Dict, Any
from datetime import date

from config import (
    DEFAULT_ESTIMATED_SECONDS,
    NAV_TODAY,
    PAGE_TASKS,
    RecurrenceFrequency,
)


@dataclass
class Task:
    title: str
    spent_seconds: int
    estimated_seconds: int
    project_id: Optional[str]
    due_date: Optional[date]
    id: Optional[int] = None
    recurrent: bool = False
    recurrence_interval: int = 1
    recurrence_frequency: RecurrenceFrequency = RecurrenceFrequency.WEEKS
    recurrence_weekdays: List[int] = field(default_factory=list)
    notes: str = ""
    sort_order: int = 0
    recurrence_end_type: str = "never"
    recurrence_end_date: Optional[date] = None

    def to_dict(self, is_done: bool = False) -> Dict[str, Any]:
        freq_value = (
            self.recurrence_frequency.value
            if isinstance(self.recurrence_frequency, RecurrenceFrequency)
            else self.recurrence_frequency
        )
        return {
            "id": self.id,
            "title": self.title,
            "spent_seconds": self.spent_seconds,
            "estimated_seconds": self.estimated_seconds,
            "project_id": self.project_id,
            "due_date": self.due_date,
            "is_done": 1 if is_done else 0,
            "recurrent": 1 if self.recurrent else 0,
            "recurrence_interval": self.recurrence_interval,
            "recurrence_frequency": freq_value,
            "recurrence_weekdays": self.recurrence_weekdays,
            "notes": self.notes,
            "sort_order": self.sort_order,
            "recurrence_end_type": self.recurrence_end_type,
            "recurrence_end_date": self.recurrence_end_date,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Task":
        freq_str = d.get("recurrence_frequency", RecurrenceFrequency.WEEKS.value)
        try:
            frequency = RecurrenceFrequency(freq_str)
        except ValueError:
            frequency = RecurrenceFrequency.WEEKS
        return cls(
            id=d.get("id"),
            title=d["title"],
            spent_seconds=d.get("spent_seconds", 0),
            estimated_seconds=d.get("estimated_seconds", DEFAULT_ESTIMATED_SECONDS),
            project_id=d.get("project_id"),
            due_date=d.get("due_date"),
            recurrent=bool(d.get("recurrent", 0)),
            recurrence_interval=d.get("recurrence_interval", 1),
            recurrence_frequency=frequency,
            recurrence_weekdays=d.get("recurrence_weekdays", []),
            notes=d.get("notes", ""),
            sort_order=d.get("sort_order", 0),
            recurrence_end_type=d.get("recurrence_end_type", "never"),
            recurrence_end_date=d.get("recurrence_end_date"),
        )


@dataclass
class AppState:
    tasks: List[Task] = field(default_factory=list)
    done_tasks: List[Task] = field(default_factory=list)
    projects: List[Dict[str, str]] = field(default_factory=list)
    selected_nav: str = NAV_TODAY
    selected_projects: Set[str] = field(default_factory=set)
    projects_expanded: bool = False
    is_mobile: bool = False
    editing_project_id: Optional[str] = None
    default_estimated_minutes: int = 15
    email_weekly_stats: bool = False
    current_page: str = PAGE_TASKS

    def get_project_by_id(self, project_id: Optional[str]) -> Optional[Dict[str, str]]:
        if project_id is None:
            return None
        for p in self.projects:
            if p["id"] == project_id:
                return p
        return None