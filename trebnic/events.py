from enum import Enum, auto
from typing import Callable, Dict, List, Any, Optional


class AppEvent(Enum):
    """Application-wide events for the observer pattern."""
    TASK_CREATED = auto()
    TASK_COMPLETED = auto()
    TASK_UNCOMPLETED = auto()
    TASK_DELETED = auto()
    TASK_DUPLICATED = auto()
    TASK_RENAMED = auto()
    TASK_UPDATED = auto()
    TASK_POSTPONED = auto()
    PROJECT_CREATED = auto()
    PROJECT_UPDATED = auto()
    PROJECT_DELETED = auto()
    TIMER_STARTED = auto()
    TIMER_STOPPED = auto()
    NAV_CHANGED = auto()
    SETTINGS_CHANGED = auto()
    DATA_RESET = auto()
    REFRESH_UI = auto()
    SIDEBAR_REBUILD = auto()


class EventBus:
    """Singleton event bus for decoupled component communication."""
    _instance: Optional["EventBus"] = None

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._listeners: Dict[AppEvent, List[Callable[[Any], None]]] = {} # type: ignore
        return cls._instance

    def subscribe(self, event: AppEvent, callback: Callable[[Any], None]) -> None:
        """Subscribe a callback to an event."""
        if event not in self._listeners:
            self._listeners[event] = []
        if callback not in self._listeners[event]:
            self._listeners[event].append(callback)

    def unsubscribe(self, event: AppEvent, callback: Callable[[Any], None]) -> None:
        """Unsubscribe a callback from an event."""
        if event in self._listeners:
            self._listeners[event] = [
                cb for cb in self._listeners[event] if cb != callback
            ]

    def emit(self, event: AppEvent, data: Any = None) -> None:
        """Emit an event to all subscribers."""
        if event in self._listeners:
            for callback in self._listeners[event]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"Error in event handler for {event}: {e}")

    def clear(self) -> None:
        """Clear all event subscriptions."""
        self._listeners.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        if cls._instance is not None:
            cls._instance._listeners.clear()
            cls._instance = None


event_bus = EventBus()