import re 
from datetime import date, timedelta 
from typing import Optional, List, Tuple 

from config import COLORS, NAV_INBOX, NAV_TODAY, NAV_UPCOMING 
from database import db 
from models.entities import Task, AppState 
from services.recurrence import calculate_next_recurrence

class TaskService: 
    def __init__(self, state: AppState): 
        self.state = state 

    @staticmethod
    def load_state() -> AppState: 
        state = AppState( 
            default_estimated_minutes=db.get_setting("default_estimated_minutes", 15), 
            email_weekly_stats=db.get_setting("email_weekly_stats", False), 
        ) 
        if db.is_empty(): 
            TaskService._init_defaults(state) 
        else: 
            TaskService._load_from_db(state) 
        return state 

    @staticmethod
    def _init_defaults(state: AppState): 
        defaults = [{"id": "sport", "name": "Sport", "icon": "🏃", "color": COLORS["green"]}, 
                    {"id": "work", "name": "Work", "icon": "💼", "color": COLORS["blue"]}, 
                    {"id": "chores", "name": "Chores", "icon": "🧹", "color": COLORS["orange"]}] 
        for p in defaults: 
            db.save_project(p) 
            state.projects.append(p) 
        tasks = [Task(title="Design dashboard", spent_seconds=45, estimated_seconds=120, project_id="work", due_date=date.today()), 
                 Task(title="Refactor auth", spent_seconds=10, estimated_seconds=90, project_id=None, due_date=date.today() + timedelta(days=1)), 
                 Task(title="Gym", spent_seconds=0, estimated_seconds=60, project_id="sport", due_date=date.today(), recurrent=True)] 
        for i, t in enumerate(tasks): 
            t.sort_order = i 
            t.id = db.save_task(t.to_dict()) 
            state.tasks.append(t) 

    @staticmethod
    def _load_from_db(state: AppState): 
        state.projects = db.load_projects() 
        for row in db.load_tasks(): 
            task = Task.from_dict(row) 
            (state.done_tasks if row["is_done"] else state.tasks).append(task) 

    def persist_task(self, task: Task): 
        is_done = task in self.state.done_tasks 
        task.id = db.save_task(task.to_dict(is_done)) 

    def persist_task_order(self): 
        for i, task in enumerate(self.state.tasks): 
            task.sort_order = i 
            self.persist_task(task) 

    def save_settings(self): 
        db.set_setting("default_estimated_minutes", self.state.default_estimated_minutes) 
        db.set_setting("email_weekly_stats", self.state.email_weekly_stats) 

    def complete_task(self, task: Task) -> Optional[Task]: 
        if task not in self.state.tasks: 
            return None 
        self.state.tasks.remove(task) 
        self.state.done_tasks.append(task) 
        db.save_task(task.to_dict(is_done=True)) 
        if task.recurrent: 
            next_date = calculate_next_recurrence(task) 
            if next_date: 
                new_task = Task(title=task.title, spent_seconds=0, estimated_seconds=task.estimated_seconds, 
                                project_id=task.project_id, due_date=next_date, recurrent=True, 
                                recurrence_interval=task.recurrence_interval, 
                                recurrence_frequency=task.recurrence_frequency, 
                                recurrence_weekdays=task.recurrence_weekdays.copy()) 
                new_task.id = db.save_task(new_task.to_dict()) 
                self.state.tasks.append(new_task) 
                return new_task 
        return None 

    def uncomplete_task(self, task: Task) -> bool: 
        if task in self.state.done_tasks: 
            self.state.done_tasks.remove(task) 
            self.state.tasks.append(task) 
            db.save_task(task.to_dict(is_done=False)) 
            return True 
        return False 

    def delete_task(self, task: Task) -> bool: 
        for lst in (self.state.tasks, self.state.done_tasks): 
            if task in lst: 
                lst.remove(task) 
                if task.id: 
                    db.delete_task(task.id) 
                return True 
        return False 

    def postpone_task(self, task: Task) -> date: 
        task.due_date = (task.due_date or date.today()) + timedelta(days=1) 
        self.persist_task(task) 
        return task.due_date 

    def duplicate_task(self, task: Task) -> Task: 
        base_name = self._get_base_name(task.title) 
        next_num = self._get_next_copy_number(base_name) 
        new_task = Task(title=f"{base_name} ({next_num})", spent_seconds=0, 
                        estimated_seconds=task.estimated_seconds, project_id=task.project_id, 
                        due_date=task.due_date, recurrent=task.recurrent, 
                        recurrence_interval=task.recurrence_interval, 
                        recurrence_frequency=task.recurrence_frequency, 
                        recurrence_weekdays=task.recurrence_weekdays.copy() if task.recurrence_weekdays else []) 
        new_task.id = db.save_task(new_task.to_dict()) 
        self.state.tasks.append(new_task) 
        return new_task 

    def _get_base_name(self, title: str) -> str: 
        match = re.match(r'^(.*?)\s*\((\d+)\)$', title) 
        return match.group(1).strip() if match else title 

    def _get_next_copy_number(self, base_name: str) -> int: 
        max_num = 1 
        for t in self.state.tasks + self.state.done_tasks: 
            if t.title == base_name: 
                max_num = max(max_num, 1) 
            match = re.match(r'^(.*?)\s*\((\d+)\)$', t.title) 
            if match and match.group(1).strip() == base_name: 
                max_num = max(max_num, int(match.group(2))) 
        return max_num + 1 

    def task_name_exists(self, name: str, exclude: Task = None) -> bool: 
        for t in self.state.tasks + self.state.done_tasks: 
            if t != exclude and t.title.lower() == name.lower(): 
                return True 
        return False 

    def add_task(self, title: str, project_id: Optional[str] = None, due_date: Optional[date] = None, 
                 estimated_seconds: int = None) -> Task: 
        if estimated_seconds is None: 
            estimated_seconds = self.state.default_estimated_minutes * 60 
        if due_date is None: 
            if self.state.selected_nav == NAV_INBOX: 
                due_date = None 
            elif self.state.selected_nav == NAV_UPCOMING: 
                due_date = date.today() + timedelta(days=1) 
            else: 
                due_date = date.today() 
        max_order = max((t.sort_order for t in self.state.tasks), default=-1) 
        new_task = Task(title=title, spent_seconds=0, estimated_seconds=estimated_seconds, 
                        project_id=project_id, due_date=due_date, sort_order=max_order + 1) 
        new_task.id = db.save_task(new_task.to_dict()) 
        self.state.tasks.append(new_task) 
        return new_task 

    def assign_project(self, task: Task, project_id: Optional[str]): 
        task.project_id = project_id 
        self.persist_task(task) 

    def delete_project(self, project_id: str) -> int: 
        self.state.projects = [p for p in self.state.projects if p["id"] != project_id] 
        count = 0 
        for lst in (self.state.tasks, self.state.done_tasks): 
            to_remove = [t for t in lst if t.project_id == project_id] 
            count += len(to_remove) 
            for t in to_remove: 
                lst.remove(t) 
        self.state.selected_projects.discard(project_id) 
        db.delete_project(project_id) 
        return count 

    def get_filtered_tasks(self) -> Tuple[List[Task], List[Task]]: 
        s = self.state 
        if s.selected_nav == NAV_INBOX: 
            pending = [t for t in s.tasks if t.project_id is None and t.due_date is None] 
            done = [t for t in s.done_tasks if t.project_id is None and t.due_date is None] 
        elif s.selected_nav == NAV_TODAY: 
            today = date.today() 
            pending = [t for t in s.tasks if t.due_date and t.due_date <= today] 
            done = [t for t in s.done_tasks if t.due_date and t.due_date <= today] 
        elif s.selected_nav == NAV_UPCOMING: 
            today = date.today() 
            pending = [t for t in s.tasks if t.due_date and t.due_date > today] 
            done = [t for t in s.done_tasks if t.due_date and t.due_date > today] 
        elif not s.selected_projects: 
            return s.tasks[:], s.done_tasks[:] 
        else: 
            pending = [t for t in s.tasks if t.project_id in s.selected_projects] 
            done = [t for t in s.done_tasks if t.project_id in s.selected_projects] 
        return pending, done 

    def reset(self): 
        db.clear_all() 
        is_mobile = self.state.is_mobile 
        new_state = TaskService.load_state() 
        for key, value in vars(new_state).items(): 
            setattr(self.state, key, value) 
        self.state.is_mobile = is_mobile 