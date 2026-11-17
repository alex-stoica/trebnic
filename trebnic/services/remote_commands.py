import asyncio
import json
import math
from datetime import date, datetime

from database import db, _encrypt_field, _decrypt_field
from events import AppEvent, event_bus
from models.entities import Task
from config import RecurrenceFrequency


def recurrence_details(task):
    return {"recurrent": task.recurrent, "recurrence": {
        "frequency": task.recurrence_frequency.value,
        "interval": task.recurrence_interval,
        "weekdays": task.recurrence_weekdays,
        "from_completion": task.recurrence_from_completion,
        "until": task.recurrence_end_date.isoformat() if task.recurrence_end_date else None,
    } if task.recurrent else None}


class RemoteCommands:
    def __init__(self, api, is_locked):
        self.api = api
        self.is_locked = is_locked
        self.lock = asyncio.Lock()

    async def execute(self, command):
        async with self.lock:
            if self.is_locked():
                return {"status": "locked", "error": "Unlock Trebnic to apply this command."}
            command_id = command["id"]
            if not isinstance(command_id, str) or len(command_id) > 100:
                raise ValueError("Invalid command ID")
            key = "remote_command:" + command_id
            previous = await db.get_setting(key, None)
            if previous:
                return json.loads(_decrypt_field(previous))
            unknown = {"status": "uncertain", "error": "Execution was interrupted. Check the task list before retrying."}
            await db.set_setting(key, _encrypt_field(json.dumps(unknown)))
            try:
                result = await self.dispatch(command["name"], command.get("arguments", {}))
            except (ValueError, TypeError, KeyError) as exc:
                result = {"status": "failed", "error": str(exc)}
            except Exception:
                result = unknown
            await db.set_setting(key, _encrypt_field(json.dumps(result)))
            event_bus.emit(AppEvent.REFRESH_UI)
            return result

    async def dispatch(self, name, args):
        if not isinstance(args, dict):
            raise ValueError("Arguments must be an object")
        if name == "get_projects":
            return {"status": "applied", "projects": [
                {"id": p.id, "name": p.name} for p in self.api.projects]}
        if name == "get_project_tasks":
            project_id = args.get("project_id")
            state = args.get("status", "all")
            offset, limit = args.get("offset", 0), args.get("limit", 100)
            if project_id is not None:
                if not isinstance(project_id, str) or not any(p.id == project_id for p in self.api.projects):
                    raise ValueError("Project not found")
            if state not in ("pending", "completed", "all"):
                raise ValueError("Invalid task status")
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise ValueError("Invalid pagination")
            rows = await db.load_tasks_filtered(
                is_done=None if state == "all" else state == "completed",
                project_ids=[project_id] if project_id is not None else None,
            )
            rows = [row for row in rows if row["project_id"] == project_id]
            return {"status": "applied", "project_id": project_id, "total": len(rows),
                    "next_offset": offset + limit if offset + limit < len(rows) else None,
                    "tasks": [{"id": row["id"], "title": row["title"],
                               "project_id": row["project_id"], "is_done": bool(row["is_done"]),
                               "due_date": row["due_date"].isoformat() if row["due_date"] else None,
                               "estimated_minutes": row["estimated_seconds"] / 60,
                               "spent_minutes": row["spent_seconds"] / 60,
                               **recurrence_details(Task.from_dict(row))}
                              for row in rows[offset:offset + limit]]}
        if name == "get_tasks":
            tasks = await self.api.get_tasks()
            return {"status": "applied", "device_time": datetime.now().astimezone().isoformat(),
                    "tasks": [{"id": t.id, "title": t.title, "project_id": t.project_id,
                               "due_date": t.due_date.isoformat() if t.due_date else None,
                               "estimated_minutes": t.estimated_seconds / 60,
                               "spent_minutes": t.spent_seconds / 60,
                               **recurrence_details(t)} for t in tasks[:100]]}
        if name == "add_task":
            title = args.get("title")
            minutes = args.get("estimated_minutes", 15)
            if not isinstance(title, str) or not title.strip() or len(title) > 500:
                raise ValueError("Title must contain 1–500 characters")
            if type(minutes) is not int or not 1 <= minutes <= 10080:
                raise ValueError("Estimated minutes must be an integer from 1 to 10080")
            due = date.fromisoformat(args["due_date"]) if args.get("due_date") else None
            task = await self.api.add_task(title.strip(), estimated_seconds=minutes * 60, due_date=due)
            return {"status": "applied", "task_id": task.id,
                    "due_date": due.isoformat() if due else None, "estimated_minutes": minutes}
        if name not in {"complete_task", "delete_task", "set_due_date", "log_time", "add_task_note", "set_recurrence", "clear_recurrence"}:
            raise ValueError("Unknown tool")
        task_id = args.get("task_id")
        if type(task_id) is not int or task_id < 1:
            raise ValueError("Invalid task ID")
        row = await db.load_task_by_id(task_id)
        if not row:
            raise ValueError("Task not found")
        task = self.api.state.get_task_by_id(task_id) or Task.from_dict(row)
        if name in {"set_recurrence", "clear_recurrence"}:
            if row.get("is_done") or task.is_draft:
                raise ValueError("Recurrence can only be changed on pending tasks")
            if name == "clear_recurrence":
                await self.api.clear_recurrence(task)
            else:
                frequency = RecurrenceFrequency(args.get("frequency"))
                interval = args.get("interval", 1)
                weekdays = args.get("weekdays", [])
                from_completion = args.get("from_completion", False)
                until = args.get("until")
                if type(interval) is not int or not 1 <= interval <= 1000:
                    raise ValueError("Interval must be an integer from 1 to 1000")
                if (not isinstance(weekdays, list) or len(weekdays) > 7
                        or any(type(day) is not int or not 0 <= day <= 6 for day in weekdays)
                        or len(set(weekdays)) != len(weekdays)):
                    raise ValueError("Weekdays must be unique integers: Monday=0 through Sunday=6")
                if weekdays and frequency != RecurrenceFrequency.WEEKS:
                    raise ValueError("Weekdays require weekly recurrence")
                if type(from_completion) is not bool:
                    raise ValueError("from_completion must be a boolean")
                if until is not None:
                    if not isinstance(until, str) or len(until) != 10:
                        raise ValueError("until must be YYYY-MM-DD or null")
                    until = date.fromisoformat(until)
                    if until < date.today():
                        raise ValueError("Recurrence end date cannot be in the past")
                await self.api.set_recurrence(task, frequency, interval, sorted(weekdays), from_completion, until)
            return {"status": "applied", "task_id": task.id,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    **recurrence_details(task)}
        if name == "add_task_note":
            note = args.get("note")
            if not isinstance(note, str) or not note.strip() or len(note) > 4000:
                raise ValueError("Note must contain 1-4000 characters")
            await self.api.add_task_note(task, note.strip())
            return {"status": "applied", "task_id": task.id, "note": note.strip()}
        if name == "log_time":
            amount = args.get("duration")
            unit = args.get("unit")
            if type(amount) not in (int, float) or not math.isfinite(amount) or unit not in ("minutes", "hours"):
                raise ValueError("Use a positive duration in minutes or hours")
            factor = 3600 if unit == "hours" else 60
            if not 0 < amount <= 604800 / factor:
                raise ValueError("Duration must be between one second and seven days")
            seconds = round(amount * factor)
            if not 1 <= seconds <= 604800:
                raise ValueError("Duration must be between one second and seven days")
            entry = await self.api.log_time(task, seconds)
            return {"status": "applied", "task_id": task.id, "entry_id": entry.id,
                    "logged_seconds": seconds, "spent_minutes": task.spent_seconds / 60}
        if name == "complete_task":
            if not row.get("is_done"):
                await self.api.complete_task(task)
        elif name == "delete_task":
            await self.api.delete_task(task)
        else:
            due = date.fromisoformat(args["due_date"]) if args.get("due_date") else None
            await self.api.set_due_date(task, due)
        return {"status": "applied", "task_id": task_id}
