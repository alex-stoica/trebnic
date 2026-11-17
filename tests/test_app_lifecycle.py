import asyncio
from concurrent.futures import Future
from unittest.mock import Mock, AsyncMock

from database import db
from services.logic import TaskService
from ui.app_initializer import AppInitializer


async def test_database_close_waits_for_existing_query(services):
    async with db._get_connection() as conn:
        closing = asyncio.create_task(db.close())
        await asyncio.sleep(0)
        assert not closing.done()
        async with conn.execute("SELECT 1") as cursor:
            assert (await cursor.fetchone())[0] == 1
    await closing
    assert db._conn is None
    async with db._get_connection() as conn:
        async with conn.execute("SELECT 2") as cursor:
            assert (await cursor.fetchone())[0] == 2


async def test_initialization_loads_on_current_loop(services, monkeypatch):
    loop = asyncio.get_running_loop()
    original = TaskService.load_state_async
    async def load():
        assert asyncio.get_running_loop() is loop
        return await original()
    monkeypatch.setattr(TaskService, "load_state_async", load)
    monkeypatch.setattr(TaskService, "load_state", Mock(side_effect=AssertionError("secondary loop")))
    initializer = AppInitializer(Mock())
    await initializer._init_services()
    assert initializer.components.pending_error is None
    assert initializer.components.state.projects


async def test_reopen_waits_for_old_page_cleanup(monkeypatch):
    import app
    cleanup = Future()
    monkeypatch.setattr(app, "_pending_cleanup", cleanup)
    initializer = Mock()
    initializer.initialize = AsyncMock(return_value="components")
    monkeypatch.setattr(app, "AppInitializer", Mock(return_value=initializer))
    constructor = Mock()
    monkeypatch.setattr(app, "TrebnicApp", constructor)
    page = Mock()
    opening = asyncio.create_task(app.create_app(page))
    await asyncio.sleep(0)
    initializer.initialize.assert_not_awaited()
    cleanup.set_result(None)
    await opening
    initializer.initialize.assert_awaited_once()
    constructor.assert_called_once_with(page, "components")
