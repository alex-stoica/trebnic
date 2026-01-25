from enum import Enum, auto
from typing import Callable, Dict, List, Any, Optional
import uuid
import weakref
import inspect


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


class _CallbackRef:
    """Wrapper for weak references to callbacks (methods or functions)."""

    def __init__(self, callback: Callable[[Any], None], on_dead: Optional[Callable[[], None]] = None):
        self._on_dead = on_dead
        if inspect.ismethod(callback):
            # Bound method - use WeakMethod
            self._ref = weakref.WeakMethod(callback, self._invoke_on_dead)
        else:
            # Regular function or lambda - use regular ref
            # Note: lambdas/closures may keep objects alive; prefer methods
            try:
                self._ref = weakref.ref(callback, self._invoke_on_dead)
            except TypeError:
                # Built-in functions can't be weakly referenced, store strongly
                self._ref = lambda: callback

    def _invoke_on_dead(self, _ref) -> None:
        """Called when the weak reference dies."""
        if self._on_dead:
            self._on_dead()

    def __call__(self) -> Optional[Callable[[Any], None]]:
        """Get the callback, or None if it was garbage collected."""
        return self._ref()


class EventBus:
    """Singleton event bus for decoupled component communication.

    Uses weak references for callbacks to prevent memory leaks when
    UI components are destroyed without explicit unsubscription.
    """
    _instance: Optional["EventBus"] = None

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Dict[event -> Dict[subscription_id -> weak callback ref]]
            cls._instance._listeners: Dict[AppEvent, Dict[str, _CallbackRef]] = {}
        return cls._instance

    def subscribe(self, event: AppEvent, callback: Callable[[Any], None]) -> Subscription:
        """Subscribe a callback to an event. Returns a Subscription for cleanup.

        Callbacks are stored as weak references to prevent memory leaks.
        Note: Avoid using lambdas as callbacks - they may be garbage collected
        immediately. Use bound methods instead.
        """
        if event not in self._listeners:
            self._listeners[event] = {}

        # Generate unique subscription ID
        subscription_id = str(uuid.uuid4())

        # Create cleanup callback for when weak ref dies
        def on_dead():
            if event in self._listeners and subscription_id in self._listeners[event]:
                del self._listeners[event][subscription_id]

        self._listeners[event][subscription_id] = _CallbackRef(callback, on_dead)

        return Subscription(self, event, subscription_id)

    def _unsubscribe_by_id(self, event: AppEvent, subscription_id: str) -> None:
        """Internal: unsubscribe by subscription ID."""
        if event in self._listeners and subscription_id in self._listeners[event]:
            del self._listeners[event][subscription_id]

    def unsubscribe(self, event: AppEvent, callback: Callable[[Any], None]) -> None:
        """Unsubscribe a callback from an event (legacy method for compatibility)."""
        if event in self._listeners:
            # Find and remove the callback by comparing dereferenced values
            to_remove = []
            for sub_id, cb_ref in self._listeners[event].items():
                cb = cb_ref()
                if cb is None or cb == callback:
                    to_remove.append(sub_id)
            for sub_id in to_remove:
                del self._listeners[event][sub_id]

    def emit(self, event: AppEvent, data: Any = None) -> None:
        """Emit an event to all subscribers.

        Dead weak references are automatically cleaned up during emission.
        """
        if event in self._listeners:
            # Copy to avoid modification during iteration
            items = list(self._listeners[event].items())
            dead_refs = []

            for sub_id, cb_ref in items:
                callback = cb_ref()
                if callback is None:
                    # Weak reference died - mark for cleanup
                    dead_refs.append(sub_id)
                    continue
                try:
                    callback(data)
                except Exception as e:
                    print(f"Error in event handler for {event}: {e}")

            # Clean up dead references
            for sub_id in dead_refs:
                if sub_id in self._listeners[event]:
                    del self._listeners[event][sub_id]

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
