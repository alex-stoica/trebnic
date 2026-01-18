import flet as ft 
import time 
import threading 

from config import COLORS 
from models.entities import Task, TimeEntry 
from services.timer import TimerService 
from services.logic import TaskService 
from ui.helpers import format_timer_display, SnackService 
from ui.components import TimerWidget 
from events import event_bus, AppEvent 


class TimerController: 
    """Controller for timer-related operations, extracted from TrebnicApp.""" 

    def __init__(
        self,
        page: ft.Page,
        timer_svc: TimerService,
        service: TaskService,
        snack: SnackService,
        timer_widget: TimerWidget,
    ) -> None:
        self.page = page
        self.timer_svc = timer_svc
        self.service = service
        self.snack = snack
        self.timer_widget = timer_widget

    def _save_time_entry(self, entry: TimeEntry) -> int: 
        """Save a time entry to the database.""" 
        return self.service.save_time_entry(entry) 

    def start_timer(self, task: Task) -> None: 
        """Start the timer for a task.""" 
        if self.timer_svc.running: 
            self.snack.show("Stop current timer first", COLORS["danger"]) 
            return 

        self.timer_svc.start(task, self.service.persist_task, self._save_time_entry) 
        self.timer_widget.start(task.title) 
        event_bus.emit(AppEvent.TIMER_STARTED, task) 

        def tick() -> None: 
            while self.timer_svc.running: 
                time.sleep(1) 
                if self.timer_svc.running: 
                    self.timer_svc.tick() 
                    self.timer_widget.update_time(self.timer_svc.seconds) 
                    try: 
                        self.page.update() 
                    except Exception: 
                        break 

        threading.Thread(target=tick, daemon=True).start() 
        self.snack.show(f"Timer started for '{task.title}'") 

    def on_timer_stop(self, e: ft.ControlEvent) -> None: 
        """Handle timer stop button click.""" 
        self.stop_timer() 

    def stop_timer(self) -> None: 
        """Stop the current timer.""" 
        if not self.timer_svc.running: 
            return 

        task, elapsed = self.timer_svc.stop() 
        if task and elapsed > 0: 
            self.snack.show( 
                f"Added {format_timer_display(elapsed)} to '{task.title}'" 
            ) 
            event_bus.emit(AppEvent.REFRESH_UI)
            event_bus.emit(AppEvent.TIMER_STOPPED, {"task": task, "elapsed": elapsed}) 

        self.timer_widget.stop() 
        self.page.update()