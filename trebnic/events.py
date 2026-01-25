from enum import Enum, auto
from typing import Callable, Dict, List, Any, Optional
import threading
import uuid
import weakref
import inspect
import logging

logger = logging.getLogger(__name__)


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
    """Represents an event subscription that can be unsubscribed.

    When using strong=True in subscribe(), the Subscription object holds
    a strong reference to the callback. You MUST store the Subscription
    object to keep the callback alive, and call unsubscribe() when done.
    """

    def __init__(
        self,
        event_bus: "EventBus",
        event: AppEvent,
        subscription_id: str,
        strong_ref: Optional[Callable[[Any], None]] = None,
    ):
        self._event_bus = event_bus
        self._event = event
        self._subscription_id = subscription_id
        self._active = True
        # Strong reference to keep callback alive (only when strong=True)
        self._strong_ref = strong_ref

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
            self._strong_ref = None  # Release strong reference


class _CallbackRef:
    """Wrapper for weak references to callbacks (methods or functions).

    WARNING: Lambdas and temporary function objects will be garbage collected
    immediately if nothing else holds a reference to them. This will cause
    the subscription to silently stop working.

    Solutions:
    1. Use bound methods (self.method_name) instead of lambdas
    2. Use strong=True in subscribe() and store the Subscription object
    3. Store lambdas as class attributes before subscribing
    """

    def __init__(
        self,
        callback: Callable[[Any], None],
        on_dead: Optional[Callable[[], None]] = None,
        event_name: str = "unknown",
    ):
        self._on_dead = on_dead
        self._event_name = event_name
        self._callback_repr = repr(callback)

        if inspect.ismethod(callback):
            # Bound method - use WeakMethod
            self._ref = weakref.WeakMethod(callback, self._invoke_on_dead)
            self._is_strong = False
        else:
            # Regular function or lambda - use regular ref
            # Note: lambdas/closures may keep objects alive; prefer methods
            try:
                self._ref = weakref.ref(callback, self._invoke_on_dead)
                self._is_strong = False
            except TypeError:
                # Built-in functions can't be weakly referenced, store strongly
                self._ref = lambda: callback
                self._is_strong = True

    def _invoke_on_dead(self, _ref) -> None:
        """Called when the weak reference dies."""
        logger.debug(
            f"EventBus: Subscription to {self._event_name} was garbage collected. "
            f"Callback was: {self._callback_repr}. "
            f"If unintentional, use strong=True or bound methods instead of lambdas."
        )
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
    _instance_lock = threading.Lock()

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            with cls._instance_lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # Dict[event -> Dict[subscription_id -> weak callback ref]]
                    cls._instance._listeners: Dict[AppEvent, Dict[str, _CallbackRef]] = {}
        return cls._instance

    def subscribe(
        self,
        event: AppEvent,
        callback: Callable[[Any], None],
        strong: bool = False,
    ) -> Subscription:
        """Subscribe a callback to an event. Returns a Subscription for cleanup.

        Args:
            event: The event to subscribe to
            callback: Function to call when event is emitted
            strong: If True, holds a strong reference to the callback.
                    You MUST store the returned Subscription object to keep
                    the callback alive, and call unsubscribe() when done to
                    avoid memory leaks.

        Returns:
            Subscription object for managing the subscription

        Note:
            Lambdas are automatically stored with strong references to prevent
            the common bug where subscriptions silently vanish after garbage
            collection. You MUST store the returned Subscription object and
            call unsubscribe() when done to avoid memory leaks.

            For bound methods (self.handler), weak references are used by default
            which auto-cleanup when the object is destroyed.

        Example (bound method - auto-cleanup when object is destroyed):
            event_bus.subscribe(AppEvent.REFRESH_UI, self.on_refresh)

        Example (lambda - auto-strong, must store and unsubscribe):
            self._sub = event_bus.subscribe(AppEvent.REFRESH_UI, lambda data: ...)
            # Later: self._sub.unsubscribe()
        """
        if event not in self._listeners:
            self._listeners[event] = {}

        # Generate unique subscription ID
        subscription_id = str(uuid.uuid4())

        # Auto-detect lambdas and closures - force strong=True to prevent silent GC
        # Lambdas have __name__ == '<lambda>', closures may have __closure__ set
        is_lambda = getattr(callback, '__name__', '') == '<lambda>'
        is_closure = not inspect.ismethod(callback) and getattr(callback, '__closure__', None) is not None
        force_strong = is_lambda or is_closure

        if force_strong and not strong:
            logger.debug(
                f"EventBus: Auto-enabling strong reference for {'lambda' if is_lambda else 'closure'} "
                f"subscribed to {event.name}. Store the Subscription and call unsubscribe() to avoid leaks."
            )
            strong = True

        # Create cleanup callback for when weak ref dies
        def on_dead():
            if event in self._listeners and subscription_id in self._listeners[event]:
                del self._listeners[event][subscription_id]

        self._listeners[event][subscription_id] = _CallbackRef(callback, on_dead, event.name)

        # Return Subscription with optional strong reference
        return Subscription(
            self, event, subscription_id,
            strong_ref=callback if strong else None
        )

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
