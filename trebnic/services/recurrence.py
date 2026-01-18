import calendar
from datetime import date, timedelta
from typing import Optional, List

from config import RecurrenceFrequency
from models.entities import Task


def _add_months(base: date, months: int) -> date:
    """Add months to a date, handling month-end edge cases.
    """
    total_months = base.year * 12 + base.month - 1 + months
    new_year = total_months // 12
    new_month = total_months % 12 + 1
    last_day_of_month = calendar.monthrange(new_year, new_month)[1]
    clamped_day = min(base.day, last_day_of_month)
    return date(new_year, new_month, clamped_day)


def _find_next_weekday(base: date, weekdays: List[int]) -> Optional[date]:
    if not weekdays:
        return None
    
    for offset in range(1, 8):  # Check next 7 days
        candidate = base + timedelta(days=offset)
        if candidate.weekday() in weekdays:
            return candidate
    return None


def _calculate_by_frequency(
    base: date,
    frequency: RecurrenceFrequency,
    interval: int,
    weekdays: List[int],
) -> date:
    """Calculate next date based on recurrence frequency.
    """
    if frequency == RecurrenceFrequency.DAYS:
        return base + timedelta(days=interval)
    
    if frequency == RecurrenceFrequency.WEEKS:
        next_weekday = _find_next_weekday(base, weekdays)
        if next_weekday:
            return next_weekday
        # Otherwise, just add weeks
        return base + timedelta(weeks=interval)
    
    if frequency == RecurrenceFrequency.MONTHS:
        return _add_months(base, interval)
    
    # Fallback for unknown frequency
    return base + timedelta(weeks=1)


def _has_recurrence_ended(next_date: date, task: Task) -> bool:
    if task.recurrence_end_type != "on_date":
        return False
    if task.recurrence_end_date is None:
        return False
    return next_date > task.recurrence_end_date


def calculate_next_recurrence(task: Task) -> Optional[date]:
    if not task.recurrent:
        return None
    if not task.due_date:
        return None
 
    next_date = _calculate_by_frequency(
        base=task.due_date,
        frequency=task.recurrence_frequency,
        interval=task.recurrence_interval,
        weekdays=task.recurrence_weekdays,
    )
 
    if _has_recurrence_ended(next_date, task):
        return None

    return next_date