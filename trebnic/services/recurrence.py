import calendar 
from datetime import date, timedelta 
from typing import Optional 

from models.entities import Task 


def _add_months(base: date, months: int) -> date: 
    total_months = base.year * 12 + base.month - 1 + months 
    new_year = total_months // 12 
    new_month = total_months % 12 + 1 
    last_day = calendar.monthrange(new_year, new_month)[1] 
    return date(new_year, new_month, min(base.day, last_day)) 


def calculate_next_recurrence(task: Task) -> Optional[date]: 
    if not task.recurrent or not task.due_date: 
        return None 
    base = task.due_date 
    if task.recurrence_frequency == "days": 
        return base + timedelta(days=task.recurrence_interval) 
    elif task.recurrence_frequency == "weeks": 
        if task.recurrence_weekdays: 
            for offset in range(1, 8): 
                next_day = base + timedelta(days=offset) 
                if next_day.weekday() in task.recurrence_weekdays: 
                    return next_day 
        return base + timedelta(weeks=task.recurrence_interval) 
    elif task.recurrence_frequency == "months": 
        return _add_months(base, task.recurrence_interval) 
    return base + timedelta(weeks=1) 