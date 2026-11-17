import asyncio
import pytest
from datetime import date, timedelta
from api import TrebnicAPI
from database import db
from services.remote_commands import RemoteCommands


@pytest.mark.parametrize("frequency,weekdays", [("days", []), ("weeks", [0, 2, 4]), ("months", [])])
async def test_remote_recurrence_round_trip(services, frequency, weekdays):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    task = await handler.api.add_task("Repeat")
    command = {"id": "recur", "name": "set_recurrence", "arguments": {
        "task_id": task.id, "frequency": frequency, "interval": 2,
        "weekdays": weekdays, "from_completion": True,
        "until": (date.today() + timedelta(days=365)).isoformat()}}
    result = await handler.execute(command)
    assert result["status"] == "applied"
    assert result["recurrence"]["frequency"] == frequency
    assert await handler.execute(command) == result
    for name, args in [("get_tasks", {}), ("get_project_tasks", {"project_id": None})]:
        read = await handler.dispatch(name, args)
        assert read["tasks"][0]["recurrence"] == result["recurrence"]
    await handler.dispatch("complete_task", {"task_id": task.id})
    next_task, = await handler.api.get_tasks()
    assert next_task.id != task.id and next_task.recurrent
    due = next_task.due_date
    cleared = await handler.dispatch("clear_recurrence", {"task_id": next_task.id})
    assert cleared["recurrence"] is None
    assert (await db.load_task_by_id(next_task.id))["due_date"] == due
    await handler.dispatch("complete_task", {"task_id": next_task.id})
    assert await handler.api.get_tasks() == []


@pytest.mark.parametrize("invalid", [
    {"frequency": "years"}, {"interval": True}, {"interval": 0}, {"interval": 1001},
    {"weekdays": [True]}, {"weekdays": [7]}, {"weekdays": [1, 1]},
    {"weekdays": "Monday"}, {"frequency": "days", "weekdays": [1]},
    {"from_completion": "false"}, {"until": "2026-02-30"}, {"until": "2000-01-01"},
])
async def test_invalid_recurrence_preserves_task(services, invalid):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    task = await handler.api.add_task("Repeat")
    before = await db.load_task_by_id(task.id)
    result = await handler.execute({"id": "bad-recur", "name": "set_recurrence",
        "arguments": {"task_id": task.id, "frequency": "weeks", **invalid}})
    assert result["status"] == "failed"
    assert await db.load_task_by_id(task.id) == before
    assert not task.recurrent


@pytest.mark.parametrize("name", ["set_recurrence", "clear_recurrence"])
async def test_recurrence_does_not_reopen_completed_task(services, name):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    task = await handler.api.add_task("Done")
    await handler.api.complete_task(task)
    result = await handler.execute({"id": "done-recur", "name": name,
        "arguments": {"task_id": task.id, "frequency": "days"}})
    assert result["status"] == "failed"
    assert (await db.load_task_by_id(task.id))["is_done"]


async def test_duplicate_delivery_creates_one_task(services):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    command = {"id": "duplicate-1", "name": "add_task", "arguments": {
        "title": "Buy milk", "due_date": "2026-11-09", "estimated_minutes": 5}}
    first, second = await asyncio.gather(handler.execute(command), handler.execute(command))
    assert first == second
    assert first["status"] == "applied"
    tasks = await handler.api.get_tasks()
    assert len(tasks) == 1
    assert tasks[0].estimated_seconds == 300
    assert tasks[0].due_date.isoformat() == "2026-11-09"
    restarted = RemoteCommands(TrebnicAPI(services), lambda: False)
    assert await restarted.execute(command) == first
    assert len(await restarted.api.get_tasks()) == 1


async def test_locked_commands_wait_without_writes(services):
    handler = RemoteCommands(TrebnicAPI(services), lambda: True)
    command = {"id": "locked-1", "name": "add_task", "arguments": {"title": "Private"}}
    assert (await handler.execute(command))["status"] == "locked"
    assert await handler.api.get_tasks() == []
    assert await db.get_setting("remote_command:locked-1", None) is None
    handler.is_locked = lambda: False
    assert (await handler.execute(command))["status"] == "applied"


@pytest.mark.parametrize("arguments", [
    {"title": ""}, {"title": "Milk", "estimated_minutes": -1},
    {"title": "Milk", "estimated_minutes": True},
    {"title": "Milk", "due_date": "2026-02-30"},
])
async def test_invalid_commands_do_not_modify_tasks(services, arguments):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    result = await handler.execute({"id": "invalid-1", "name": "add_task", "arguments": arguments})
    assert result["status"] == "failed"
    assert await handler.api.get_tasks() == []


async def test_interrupted_execution_is_not_repeated(services):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    await db.set_setting("remote_command:interrupted", '{"status":"uncertain"}')
    result = await handler.execute({"id": "interrupted", "name": "add_task", "arguments": {"title": "Milk"}})
    assert result["status"] == "uncertain"
    assert await handler.api.get_tasks() == []


async def test_mutations_and_readback(services):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    task = await handler.api.add_task("Test")
    result = await handler.execute({"id":"date", "name":"set_due_date", "arguments":{"task_id":task.id,"due_date":"2026-11-10"}})
    assert result["status"] == "applied"
    read = await handler.execute({"id":"read", "name":"get_tasks"})
    assert read["tasks"][0]["due_date"] == "2026-11-10"
    await handler.execute({"id":"done", "name":"complete_task", "arguments":{"task_id":task.id}})
    assert await handler.api.get_tasks() == []
    await handler.execute({"id":"delete", "name":"delete_task", "arguments":{"task_id":task.id}})
    assert await db.load_task_by_id(task.id) is None


@pytest.mark.parametrize("duration,unit,seconds", [(25,"minutes",1500),(1.5,"hours",5400)])
async def test_log_time_is_persisted_once(services, duration, unit, seconds):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    task = await handler.api.add_task("Reading")
    command = {"id":"time-1", "name":"log_time", "arguments":{
        "task_id":task.id,"duration":duration,"unit":unit}}
    result = await handler.execute(command)
    assert result["status"] == "applied"
    assert result["logged_seconds"] == seconds
    restarted = RemoteCommands(TrebnicAPI(services), lambda: False)
    assert await restarted.execute(command) == result
    row = await db.load_task_by_id(task.id)
    assert row["spent_seconds"] == seconds
    assert not row["is_done"]


@pytest.mark.parametrize("duration,unit", [(True,"hours"),(-1,"minutes"),(float("nan"),"hours"),(200,"hours"),(1,"days"),(1e308,"hours")])
async def test_invalid_logged_time_is_rejected(services, duration, unit):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    task = await handler.api.add_task("Reading")
    result = await handler.execute({"id":"bad-time","name":"log_time","arguments":{
        "task_id":task.id,"duration":duration,"unit":unit}})
    assert result["status"] == "failed"
    assert (await db.load_task_by_id(task.id))["spent_seconds"] == 0


async def test_notes_append_once_and_preserve_task_data(services):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    task = await handler.api.add_task("Reading", estimated_seconds=3600)
    await handler.api.add_task_note(task, "Existing note")
    command = {"id": "note-1", "name": "add_task_note", "arguments": {
        "task_id": task.id, "note": "  Reviewed chapter one  "}}
    first = await handler.execute(command)
    assert first["status"] == "applied"
    restarted = RemoteCommands(TrebnicAPI(services), lambda: False)
    assert await restarted.execute(command) == first
    row = await db.load_task_by_id(task.id)
    assert row["notes"] == "Existing note\n\nReviewed chapter one"
    assert row["estimated_seconds"] == 3600
    assert row["spent_seconds"] == 0
    assert not row["is_done"]


@pytest.mark.parametrize("note", [None, 7, "", "   ", "x" * 4001])
async def test_invalid_notes_do_not_change_task(services, note):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    task = await handler.api.add_task("Reading")
    result = await handler.execute({"id": "bad-note", "name": "add_task_note",
                                    "arguments": {"task_id": task.id, "note": note}})
    assert result["status"] == "failed"
    assert (await db.load_task_by_id(task.id))["notes"] == ""


async def test_project_queries_filter_status_paginate_and_exclude_drafts(services):
    from datetime import date
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    project = await handler.api.create_project("Research")
    other = await handler.api.create_project("Other")
    first = await handler.api.add_task("Pending", project_id=project.id, due_date=date(2026, 11, 10))
    draft = await handler.api.add_task("Draft", project_id=project.id)
    draft.is_draft = True
    await services.task.persist_task(draft)
    done = await handler.api.add_task("Finished", project_id=project.id)
    await handler.api.complete_task(done)
    await handler.api.add_task("Elsewhere", project_id=other.id)
    unassigned = await handler.api.add_task("Unassigned")
    projects = await handler.dispatch("get_projects", {})
    assert {"id": project.id, "name": "Research"} in projects["projects"]
    args = {"project_id": project.id, "status": "all", "limit": 1}
    page = await handler.dispatch("get_project_tasks", args)
    assert page["total"] == 2 and page["next_offset"] == 1
    second = await handler.dispatch("get_project_tasks", dict(args, offset=1))
    assert second["next_offset"] is None
    assert {page["tasks"][0]["id"], second["tasks"][0]["id"]} == {first.id, done.id}
    for status, expected in [("pending", first), ("completed", done)]:
        result = await handler.dispatch("get_project_tasks", {"project_id": project.id, "status": status})
        assert [row["id"] for row in result["tasks"]] == [expected.id]
    result = await handler.dispatch("get_project_tasks", {"project_id": None})
    assert [row["id"] for row in result["tasks"]] == [unassigned.id]
    result = await handler.execute({"id": "dated-project", "name": "get_project_tasks",
                                    "arguments": {"project_id": project.id, "status": "pending"}})
    assert result["tasks"][0]["due_date"] == "2026-11-10"


@pytest.mark.parametrize("args", [{"project_id": "missing"}, {"project_id": 4},
    {"offset": -1}, {"limit": True}, {"limit": 101}, {"status": "unknown"}])
async def test_project_queries_reject_invalid_filters(services, args):
    handler = RemoteCommands(TrebnicAPI(services), lambda: False)
    result = await handler.execute({"id": "bad-project", "name": "get_project_tasks", "arguments": args})
    assert result["status"] == "failed"
