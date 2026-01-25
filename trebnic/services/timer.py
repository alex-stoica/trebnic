from datetime import datetime
from typing import Awaitable, Callable, Optional, Tuple, Union

from config import MIN_TIMER_SECONDS
from models.entities import Task, TimeEntry

# Callback types - support both sync and async
PersistFn = Callable[[Task], Union[None, Awaitable[None]]]
SaveEntryFn = Callable[[TimeEntry], Union[int, Awaitable[int]]]
DeleteEntryFn = Callable[[int], Union[None, Awaitable[None]]]


class TimerService:
    """Timer service for tracking time spent on tasks.

    Note: This service is sync-only and manages timer state. The actual
    async DB operations are handled by TimerController which wraps
    the service calls in async contexts.
    """

    def __init__(self) -> None:
        self.active_task: Optional[Task] = None
        self.seconds: int = 0
        self.running: bool = False
        self.current_entry: Optional[TimeEntry] = None
        self.start_time: Optional[datetime] = None

    def start(self, task: Task) -> None:
        """Start the timer for a task.

        Creates a TimeEntry in memory. The caller (TimerController) is
        responsible for persisting it to the database.
        """
        self.active_task = task
        self.seconds = 0
        self.running = True
        self.start_time = datetime.now()

        if task.id is not None:
            self.current_entry = TimeEntry(
                task_id=task.id,
                start_time=self.start_time,
            )

    def stop(self) -> Tuple[Optional[Task], int, bool]:
        """Stop the timer and finalize the time entry.

        Returns:
            Tuple of (task, elapsed_seconds, should_save).
            should_save is False if elapsed time was below MIN_TIMER_SECONDS.

        Note: This method does NOT persist to DB. The caller (TimerController)
        is responsible for async persistence after receiving the result.
        """
        self.running = False
        task, elapsed = self.active_task, self.seconds
        should_save = elapsed >= MIN_TIMER_SECONDS

        if should_save:
            if self.current_entry is not None:
                self.current_entry.end_time = datetime.now()

            if task and elapsed > 0:
                task.spent_seconds += elapsed

        # Store values for caller to use before clearing
        entry_to_delete = None
        if not should_save and self.current_entry is not None and self.current_entry.id is not None:
            entry_to_delete = self.current_entry.id

        # Clear state
        self.active_task = None
        self.seconds = 0
        self.current_entry = None
        self.start_time = None

        return task, elapsed, should_save, entry_to_delete

    def get_entry_to_delete(self) -> Optional[int]:
        """Get the entry ID to delete if timer was stopped early."""
        if self.current_entry is not None and self.current_entry.id is not None:
            if self.seconds < MIN_TIMER_SECONDS:
                return self.current_entry.id
        return None

    def tick(self) -> None:
        if self.running:
            self.seconds += 1

    def get_current_entry(self) -> Optional[TimeEntry]:  
        """Get the current running time entry."""
        return self.current_entry