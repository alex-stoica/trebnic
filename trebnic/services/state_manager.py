"""Centralized manager for AppState list mutations.

All mutations to state.tasks, state.done_tasks, and state.projects go through
this class. This makes it easy to reason about state transitions, enforce
invariants, and add cross-cutting concerns (logging, validation) in one place.
"""
from typing import List

from models.entities import AppState, Project, Task


class StateManager:
    """Owns all list mutations on AppState."""

    def __init__(self, state: AppState) -> None:
        self._state = state

    # -- single-item task mutations --

    def add_task(self, task: Task) -> None:
        self._state.tasks.append(task)

    def add_done_task(self, task: Task) -> None:
        self._state.done_tasks.append(task)

    def remove_task(self, task: Task) -> None:
        try:
            self._state.tasks.remove(task)
        except ValueError:
            pass

    def remove_done_task(self, task: Task) -> None:
        try:
            self._state.done_tasks.remove(task)
        except ValueError:
            pass

    def remove_task_from_any(self, task: Task) -> None:
        self.remove_task(task)
        self.remove_done_task(task)

    def move_to_done(self, task: Task) -> None:
        self.remove_task(task)
        self.add_done_task(task)

    # -- single-item project mutations --

    def add_project(self, project: Project) -> None:
        self._state.projects.append(project)

    # -- bulk replacements --

    def replace_tasks(self, tasks: List[Task], done_tasks: List[Task]) -> None:
        self._state.tasks[:] = tasks
        self._state.done_tasks[:] = done_tasks

    def replace_projects(self, projects: List[Project]) -> None:
        self._state.projects[:] = projects

    def replace_all(
        self,
        tasks: List[Task],
        done_tasks: List[Task],
        projects: List[Project],
    ) -> None:
        self._state.tasks[:] = tasks
        self._state.done_tasks[:] = done_tasks
        self._state.projects[:] = projects

    def clear_all(self) -> None:
        self._state.tasks.clear()
        self._state.done_tasks.clear()
        self._state.projects.clear()
