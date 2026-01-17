from typing import Callable, Optional, Tuple 

from models.entities import Task 


class TimerService: 
    def __init__(self): 
        self.active_task: Optional[Task] = None 
        self.seconds: int = 0 
        self.running: bool = False 
        self._persist_fn: Optional[Callable] = None 

    def start(self, task: Task, persist_fn: Callable = None): 
        self.active_task, self.seconds, self.running, self._persist_fn = task, 0, True, persist_fn 

    def stop(self) -> Tuple[Optional[Task], int]: 
        self.running = False 
        task, elapsed = self.active_task, self.seconds 
        if task and elapsed > 0: 
            task.spent_seconds += elapsed 
            if self._persist_fn: 
                self._persist_fn(task) 
        self.active_task, self.seconds = None, 0 
        return task, elapsed 

    def tick(self): 
        if self.running: 
            self.seconds += 1 