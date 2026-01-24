from enum import Enum, auto
from typing import Callable, Dict, List, Any, Optional
import uuid


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


class Subscription:
    """Represents an event subscription that can be unsubscribed."""

    def __init__(self, event_bus: "EventBus", event: AppEvent, subscription_id: str):
        self._event_bus = event_bus
        self._event = event
        self._subscription_id = subscription_id
        self._active = True

    @property
    def id(self) -> str:
        return self._subscription_id

    @property
    def active(self) -> bool:
        return self._active

    def unsubscribe(self) -> None:
        """Unsubscribe this subscription."""
        if self._active:
            self._event_bus._unsubscribe_by_id(self._event, self._subscription_id)
            self._active = False


class EventBus:
    """Singleton event bus for decoupled component communication."""
    _instance: Optional["EventBus"] = None

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Dict[event -> Dict[subscription_id -> callback]]
            cls._instance._listeners: Dict[AppEvent, Dict[str, Callable[[Any], None]]] = {}
        return cls._instance

    def subscribe(self, event: AppEvent, callback: Callable[[Any], None]) -> Subscription:
        """Subscribe a callback to an event. Returns a Subscription for cleanup."""
        if event not in self._listeners:
            self._listeners[event] = {}

        # Generate unique subscription ID
        subscription_id = str(uuid.uuid4())
        self._listeners[event][subscription_id] = callback

        return Subscription(self, event, subscription_id)

    def _unsubscribe_by_id(self, event: AppEvent, subscription_id: str) -> None:
        """Internal: unsubscribe by subscription ID."""
        if event in self._listeners and subscription_id in self._listeners[event]:
            del self._listeners[event][subscription_id]

    def unsubscribe(self, event: AppEvent, callback: Callable[[Any], None]) -> None:
        """Unsubscribe a callback from an event (legacy method for compatibility)."""
        if event in self._listeners:
            # Find and remove the callback
            to_remove = [
                sub_id for sub_id, cb in self._listeners[event].items()
                if cb == callback
            ]
            for sub_id in to_remove:
                del self._listeners[event][sub_id]

    def emit(self, event: AppEvent, data: Any = None) -> None:
        """Emit an event to all subscribers."""
        if event in self._listeners:
            # Copy to avoid modification during iteration
            callbacks = list(self._listeners[event].values())
            for callback in callbacks:
                try:
                    callback(data)
                except Exception as e:
                    print(f"Error in event handler for {event}: {e}")

    def clear(self) -> None:
        """Clear all event subscriptions.

        Note: This method is primarily used for testing to reset state
        between test cases. Not typically called in production code.
        """
        self._listeners.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance.

        Note: This method is primarily used for testing to ensure
        a fresh EventBus instance between test cases. Not typically
        called in production code.
        """
        if cls._instance is not None:
            cls._instance._listeners.clear()
            cls._instance = None


event_bus = EventBus()
