from dataclasses import dataclass, field
from datetime import datetime  
from typing import Optional, List, Set, Dict, Any
from datetime import date

from config import (
    DEFAULT_ESTIMATED_SECONDS,
    NavItem,  
    PageType, 
    RecurrenceFrequency,
)


@dataclass 
class Project: 
    """Project entity representing a task category.""" 
    id: str 
    name: str 
    icon: str 
    color: str 

    def to_dict(self) -> Dict[str, str]: 
        """Convert to dictionary for database storage.""" 
        return { 
            "id": self.id, 
            "name": self.name, 
            "icon": self.icon, 
            "color": self.color, 
        } 

    @classmethod 
    def from_dict(cls, d: Dict[str, str]) -> "Project": 
        """Create Project from dictionary.""" 
        return cls( 
            id=d["id"], 
            name=d["name"], 
            icon=d["icon"], 
            color=d["color"], 
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
    recurrence_from_completion: bool = False

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
            "recurrence_from_completion": 1 if self.recurrence_from_completion else 0,
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
            recurrence_from_completion=bool(d.get("recurrence_from_completion", 0)),
        )

    def create_next_occurrence(self, next_due_date: date) -> "Task":
        """Create the next occurrence of a recurring task.

        Creates a new Task with the same recurrence settings but reset spent_seconds
        and the provided next due date.
        """
        return Task(
            title=self.title,
            spent_seconds=0,
            estimated_seconds=self.estimated_seconds,
            project_id=self.project_id,
            due_date=next_due_date,
            recurrent=True,
            recurrence_interval=self.recurrence_interval,
            recurrence_frequency=self.recurrence_frequency,
            recurrence_weekdays=list(self.recurrence_weekdays),
            notes=self.notes,
            sort_order=self.sort_order,
            recurrence_end_type=self.recurrence_end_type,
            recurrence_end_date=self.recurrence_end_date,
            recurrence_from_completion=self.recurrence_from_completion,
        )


@dataclass  
class TimeEntry:
    """Time entry entity representing a tracked time period for a task."""
    task_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    id: Optional[int] = None

    @property
    def duration_seconds(self) -> int:
        """Calculate duration in seconds."""
        if self.end_time is None:
            return int((datetime.now() - self.start_time).total_seconds())
        return int((self.end_time - self.start_time).total_seconds())

    @property
    def is_running(self) -> bool:
        """Check if this entry is still running."""
        return self.end_time is None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimeEntry":
        """Create TimeEntry from dictionary."""
        start = d.get("start_time")
        end = d.get("end_time")
        return cls(
            id=d.get("id"),
            task_id=d["task_id"],
            start_time=datetime.fromisoformat(start) if start else datetime.now(),
            end_time=datetime.fromisoformat(end) if end else None,
        )


@dataclass
class AppState:
    tasks: List[Task] = field(default_factory=list)
    done_tasks: List[Task] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    selected_nav: NavItem = NavItem.TODAY
    selected_projects: Set[str] = field(default_factory=set)
    projects_expanded: bool = False
    is_mobile: bool = False
    editing_project_id: Optional[str] = None
    default_estimated_minutes: int = 15
    email_weekly_stats: bool = False
    current_page: PageType = PageType.TASKS
    viewing_task_id: Optional[int] = None
    calendar_week_offset: int = 0
    recovered_timer_entry: Optional["TimeEntry"] = None 

    def get_project_by_id(self, project_id: Optional[str]) -> Optional[Project]: 
        if project_id is None:
            return None
        for p in self.projects:
            if p.id == project_id: 
                return p
        return None

    def get_task_by_id(self, task_id: Optional[int]) -> Optional[Task]:
        """Get a task by its ID from either tasks or done_tasks."""
        if task_id is None:
            return None
        for t in self.tasks + self.done_tasks:
            if t.id == task_id:
                return t
        return None