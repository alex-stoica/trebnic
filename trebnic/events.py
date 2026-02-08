from enum import Enum, auto
from typing import Callable, Dict, List, Any, Optional
import threading
import uuid
import logging

logger = logging.getLogger(__name__)


class AppEvent(Enum):
    """Application-wide events for the observer pattern."""
    # Task lifecycle events (emitted after action completes)
    TASK_CREATED = auto()
    TASK_COMPLETED = auto()
    TASK_UNCOMPLETED = auto()
    TASK_DELETED = auto()
    TASK_DUPLICATED = auto()
    TASK_RENAMED = auto()
    TASK_UPDATED = auto()
    TASK_POSTPONED = auto()

    # Task action requests (emitted by UI, handled by app layer)
    TASK_COMPLETE_REQUESTED = auto()
    TASK_UNCOMPLETE_REQUESTED = auto()
    TASK_DELETE_REQUESTED = auto()
    TASK_DUPLICATE_REQUESTED = auto()
    TASK_RENAME_REQUESTED = auto()
    TASK_ASSIGN_PROJECT_REQUESTED = auto()
    TASK_DATE_PICKER_REQUESTED = auto()
    TASK_START_TIMER_REQUESTED = auto()
    TASK_POSTPONE_REQUESTED = auto()
    TASK_RECURRENCE_REQUESTED = auto()
    TASK_STATS_REQUESTED = auto()
    TASK_NOTES_REQUESTED = auto()

    # Project events
    PROJECT_CREATED = auto()
    PROJECT_UPDATED = auto()
    PROJECT_DELETED = auto()

    # Timer events
    TIMER_STARTED = auto()
    TIMER_STOPPED = auto()
    TIMER_TICK = auto()

    # Navigation and UI events
    NAV_CHANGED = auto()
    SETTINGS_CHANGED = auto()
    DATA_RESET = auto()
    REFRESH_UI = auto()
    SIDEBAR_REBUILD = auto()
    LANGUAGE_CHANGED = auto()

    # Notification events
    NOTIFICATION_SCHEDULED = auto()
    NOTIFICATION_FIRED = auto()
    NOTIFICATION_TAPPED = auto()


class Subscription:
    """Represents an event subscription that can be unsubscribed.

    The subscriber is responsible for calling unsubscribe() when done.
    Failing to unsubscribe will keep the callback alive and may cause
    handlers to be called on destroyed objects.
    """

    def __init__(
        self,
        event_bus: "EventBus",
        event: AppEvent,
        subscription_id: str,
        callback: Callable[[Any], None],
    ):
        self._event_bus = event_bus
        self._event = event
        self._subscription_id = subscription_id
        self._callback = callback
        self._active = True

    @property
    def id(self) -> str:
        return self._subscription_id

    @property
    def active(self) -> bool:
        return self._active

    def unsubscribe(self) -> None:
        """Unsubscribe this subscription. Subscriber is responsible for calling this."""
        if self._active:
            self._event_bus._unsubscribe_by_id(self._event, self._subscription_id)
            self._active = False
            self._callback = None


class EventBus:
    """Simple event bus for decoupled component communication.

    Subscribers must store the returned Subscription and call unsubscribe()
    when they no longer need to receive events. This is the subscriber's
    responsibility - failing to do so will cause memory leaks and handlers
    being called on destroyed objects.

    Example:
        class MyComponent:
            def __init__(self):
                self._sub = event_bus.subscribe(AppEvent.REFRESH_UI, self._on_refresh)

            def _on_refresh(self, data):
                # Handle event
                pass

            def cleanup(self):
                self._sub.unsubscribe()
    """
    _instance: Optional["EventBus"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._listeners: Dict[AppEvent, Dict[str, Callable[[Any], None]]] = {}
        return cls._instance

    def subscribe(
        self,
        event: AppEvent,
        callback: Callable[[Any], None],
    ) -> Subscription:
        """Subscribe a callback to an event.

        Args:
            event: The event to subscribe to
            callback: Function to call when event is emitted

        Returns:
            Subscription object - caller must store this and call unsubscribe() when done
        """
        if event not in self._listeners:
            self._listeners[event] = {}

        subscription_id = str(uuid.uuid4())
        self._listeners[event][subscription_id] = callback

        return Subscription(self, event, subscription_id, callback)

    def _unsubscribe_by_id(self, event: AppEvent, subscription_id: str) -> None:
        """Internal: unsubscribe by subscription ID."""
        if event in self._listeners and subscription_id in self._listeners[event]:
            del self._listeners[event][subscription_id]

    def unsubscribe(self, event: AppEvent, callback: Callable[[Any], None]) -> None:
        """Unsubscribe a callback from an event (legacy method for compatibility)."""
        if event in self._listeners:
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
                except Exception as e:  # Intentionally broad: dispatcher must survive any handler failure
                    logger.error(f"Error in event handler for {event}: {e}")

    def clear(self) -> None:
        """Clear all event subscriptions. Used for testing."""
        self._listeners.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance. Used for testing."""
        if cls._instance is not None:
            cls._instance._listeners.clear()
            cls._instance = None


event_bus = EventBus()
