from datetime import datetime
from typing import Callable, Optional, Tuple

from models.entities import Task, TimeEntry


class TimerService:
    def __init__(self) -> None:
        self.active_task: Optional[Task] = None
        self.seconds: int = 0
        self.running: bool = False
        self._persist_fn: Optional[Callable[[Task], None]] = None
        self._save_entry_fn: Optional[Callable[[TimeEntry], int]] = None
        self.current_entry: Optional[TimeEntry] = None
        self.start_time: Optional[datetime] = None

    def start(
        self,
        task: Task,
        persist_fn: Optional[Callable[[Task], None]] = None,
        save_entry_fn: Optional[Callable[[TimeEntry], int]] = None,
    ) -> None:
        self.active_task = task
        self.seconds = 0
        self.running = True
        self._persist_fn = persist_fn
        self._save_entry_fn = save_entry_fn
        self.start_time = datetime.now()
        
        if task.id is not None:
            self.current_entry = TimeEntry(
                task_id=task.id,
                start_time=self.start_time,
            ) 
            if self._save_entry_fn:
                self.current_entry.id = self._save_entry_fn(self.current_entry)

    def stop(self) -> Tuple[Optional[Task], int]:
        self.running = False
        task, elapsed = self.active_task, self.seconds
 
        if self.current_entry is not None:
            self.current_entry.end_time = datetime.now()
            if self._save_entry_fn:
                self._save_entry_fn(self.current_entry)

        if task and elapsed > 0:
            task.spent_seconds += elapsed
            if self._persist_fn:
                self._persist_fn(task)

        self.active_task = None
        self.seconds = 0
        self.current_entry = None 
        self.start_time = None 

        return task, elapsed

    def tick(self) -> None:
        if self.running:
            self.seconds += 1

    def get_current_entry(self) -> Optional[TimeEntry]:  
        """Get the current running time entry."""
        return self.current_entry