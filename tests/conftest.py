"""Shared fixtures for Trebnic tests."""
import asyncio
from pathlib import Path

import pytest
import pytest_asyncio

import database as db_module
from core import ServiceContainer
from database import db
from events import event_bus
from registry import registry, Services
from services.logic import TaskService
from services.project_service import ProjectService
from services.settings_service import SettingsService
from services.time_entry_service import TimeEntryService
from services.timer import TimerService


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the whole test session.

    This avoids issues with aiosqlite connections being tied to one loop
    while pytest-asyncio creates a new loop per test by default.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def services() -> ServiceContainer:
    """Provide a fresh ServiceContainer backed by an in-memory database.

    Reuses the module-level singletons (db, event_bus, registry) but
    resets their internal state between tests for isolation.
    """
    # Close any existing DB connection and force re-init
    await db.close()
    db._initialized = False
    db._conn_lock = None

    # Clear event subscriptions and service registrations
    event_bus.clear()
    registry.clear()

    # Point to a fresh in-memory database
    db_module.DB_PATH = Path(":memory:")

    # Register core services
    registry.register(Services.EVENT_BUS, event_bus)

    # Bootstrap: init schema, load state, create services
    state = await TaskService.load_state_async()

    task_service = TaskService(state)
    project_service = ProjectService(state)
    time_entry_service = TimeEntryService()
    settings_service = SettingsService(state)
    timer_service = TimerService()

    registry.register(Services.TASK, task_service)
    registry.register(Services.PROJECT, project_service)
    registry.register(Services.TIME_ENTRY, time_entry_service)
    registry.register(Services.SETTINGS, settings_service)
    registry.register(Services.TIMER, timer_service)

    svc = ServiceContainer(
        state=state,
        task=task_service,
        project=project_service,
        time_entry=time_entry_service,
        settings=settings_service,
        timer=timer_service,
    )

    yield svc

    await db.close()
    event_bus.clear()
    registry.clear()
