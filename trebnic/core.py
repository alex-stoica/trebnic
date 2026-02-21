"""Headless bootstrap for Trebnic services.

Initializes the service layer without any Flet dependency, suitable for
MCP servers, CLI tools, scripts, and testing.

Usage:
    from core import bootstrap, shutdown

    svc = await bootstrap(db_path=Path("my.db"))
    task = await svc.task.add_task("Test", due_date=date.today())
    pending, done = await svc.task.get_filtered_tasks(nav=NavItem.TODAY)
    await shutdown()
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from database import db, configure_db_path
from events import event_bus
from models.entities import AppState
from registry import registry, Services
from services.logic import TaskService
from services.project_service import ProjectService
from services.settings_service import SettingsService
from services.time_entry_service import TimeEntryService
from services.timer import TimerService


@dataclass
class ServiceContainer:
    """Container holding all initialized services for headless use."""
    state: AppState
    task: TaskService
    project: ProjectService
    time_entry: TimeEntryService
    settings: SettingsService
    timer: TimerService


async def bootstrap(
    db_path: Optional[Path] = None,
    register_crypto: bool = True,
) -> ServiceContainer:
    """Initialize the service layer without Flet.

    Args:
        db_path: Custom database path. Uses default ("trebnic.db") if None.
        register_crypto: Whether to register the crypto service. Set False
            if encryption is not needed or crypto dependencies are unavailable.

    Returns:
        ServiceContainer with all services ready to use.
    """
    if db_path is not None:
        configure_db_path(db_path)

    # Register core services in registry
    registry.register(Services.EVENT_BUS, event_bus)

    if register_crypto:
        try:
            from services.crypto import crypto
            registry.register(Services.CRYPTO, crypto)
        except ImportError:
            pass

    # Load state from database (initializes schema, seeds if empty)
    state = await TaskService.load_state_async()

    # Create services
    task_service = TaskService(state)
    project_service = ProjectService(state)
    time_entry_service = TimeEntryService()
    settings_service = SettingsService(state)
    timer_service = TimerService()

    # Register in registry for cross-service access
    registry.register(Services.TASK, task_service)
    registry.register(Services.PROJECT, project_service)
    registry.register(Services.TIME_ENTRY, time_entry_service)
    registry.register(Services.SETTINGS, settings_service)
    registry.register(Services.TIMER, timer_service)

    return ServiceContainer(
        state=state,
        task=task_service,
        project=project_service,
        time_entry=time_entry_service,
        settings=settings_service,
        timer=timer_service,
    )


async def shutdown() -> None:
    """Clean up resources (close database connection)."""
    await db.close()
