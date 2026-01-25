"""
Central service registry for dependency injection.

This module provides a single point of access for shared services,
eliminating circular imports that occur when modules need to reference
each other. Services are registered during app initialization and can
be accessed from anywhere.

Usage:
    # At app initialization (in app_initializer.py or similar):
    from registry import registry
    from services.crypto import CryptoService
    from events import EventBus

    registry.register('crypto', CryptoService())
    registry.register('event_bus', EventBus())

    # In any module that needs a service:
    from registry import registry

    crypto = registry.get('crypto')
    event_bus = registry.get('event_bus')

Design:
    - Registry is a simple dict-based container
    - Services are registered by string keys
    - Type hints via generics for better IDE support
    - Thread-safe access via lock
"""
import threading
from typing import TypeVar, Optional, Dict, Any

T = TypeVar('T')


class ServiceRegistry:
    """Thread-safe registry for application services.

    Provides dependency injection without circular imports by serving
    as a central lookup point for shared services.
    """
    _instance: Optional["ServiceRegistry"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "ServiceRegistry":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._services: Dict[str, Any] = {}
                    cls._instance._lock = threading.Lock()
        return cls._instance

    def register(self, name: str, service: Any) -> None:
        """Register a service by name.

        Args:
            name: Unique identifier for the service
            service: The service instance to register
        """
        with self._lock:
            self._services[name] = service

    def get(self, name: str) -> Optional[Any]:
        """Get a registered service by name.

        Args:
            name: The service identifier

        Returns:
            The service instance, or None if not registered
        """
        with self._lock:
            return self._services.get(name)

    def require(self, name: str) -> Any:
        """Get a registered service, raising if not found.

        Args:
            name: The service identifier

        Returns:
            The service instance

        Raises:
            KeyError: If the service is not registered
        """
        with self._lock:
            if name not in self._services:
                raise KeyError(f"Service '{name}' not registered. "
                              f"Ensure it's registered during app initialization.")
            return self._services[name]

    def is_registered(self, name: str) -> bool:
        """Check if a service is registered."""
        with self._lock:
            return name in self._services

    def clear(self) -> None:
        """Clear all registered services. Used primarily for testing."""
        with self._lock:
            self._services.clear()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance. Used primarily for testing."""
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance._services.clear()
                cls._instance = None


# Module-level singleton
registry = ServiceRegistry()


# Convenience constants for service names to avoid typos
class Services:
    """Service name constants for type-safe registry access."""
    CRYPTO = "crypto"
    EVENT_BUS = "event_bus"
    DATABASE = "database"
