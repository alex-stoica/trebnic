import flet as ft 
from typing import Optional 

from config import NAV_PROJECTS 
from models.entities import Task, AppState 
from services.logic import TaskService 
from ui.helpers import format_due_date 


class UIController: 
    def __init__(self, page: ft.Page, state: AppState, service: TaskService): 
        self.page = page 
        self.state = state 
        self.service = service 
        self._callbacks = {} 

    def wire(self, **callbacks): 
        self._callbacks = callbacks 

    def _call(self, name: str, *args, **kwargs): 
        if name in self._callbacks: 
            return self._callbacks[name](*args, **kwargs) 

    def get_project(self, project_id: Optional[str]) -> Optional[dict]: 
        return self.state.get_project_by_id(project_id) 

    def get_due_date_str(self, task: Task) -> Optional[str]: 
        return format_due_date(task.due_date) 

    def toggle_project(self, project_id: str): 
        if project_id in self.state.selected_projects: 
            self.state.selected_projects.remove(project_id) 
        else: 
            self.state.selected_projects.add(project_id) 
            self.state.selected_nav = NAV_PROJECTS 
        if self.state.is_mobile: 
            self.page.drawer.open = False 
        self._call("update_nav") 

    def navigate_to(self, page_name: str): 
        self.state.current_page = page_name 
        self._call("update_content") 
        self.page.update() 

    def complete(self, task: Task): 
        new_task = self.service.complete_task(task) 
        if new_task: 
            self._call("show_snack", f"Next occurrence scheduled for {new_task.due_date.strftime('%b %d')}") 
        self._call("refresh") 

    def uncomplete(self, task: Task): 
        if self.service.uncomplete_task(task): 
            self._call("refresh") 

    def delete(self, task: Task): 
        self._call("delete_task", task) 

    def duplicate(self, task: Task): 
        self._call("duplicate_task", task) 

    def rename(self, task: Task): 
        self._call("rename_task", task) 

    def assign_project(self, task: Task): 
        self._call("assign_project", task) 

    def date_picker(self, task: Task): 
        self._call("date_picker", task) 

    def start_timer(self, task: Task): 
        self._call("start_timer", task) 

    def postpone(self, task: Task): 
        self._call("postpone_task", task) 

    def recurrence(self, task: Task): 
        self._call("recurrence", task) 

    def stats(self, task: Task): 
        self._call("stats", task) 

    def notes(self, task: Task): 
        self._call("notes", task) 