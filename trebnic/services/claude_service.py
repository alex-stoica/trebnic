"""Claude AI chat service for natural-language task management.

Communicates with the Claude Messages API via httpx. Defines tools that map
to TrebnicAPI methods and handles the tool_use loop internally so callers
receive a final text response.
"""
import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import httpx

from api import TrebnicAPI
from config import PROJECT_COLORS, RecurrenceFrequency
from database import db, _encrypt_field, _decrypt_field
from i18n import t
from models.entities import AppState
from services.stats import stats_service

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
TEMPERATURE = 0.5
TIMEOUT_SECONDS = 30

SETTING_KEY = "claude_api_key"

# ── Tool definitions sent to the Claude API ──────────────────────────────

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "add_task",
        "description": "Create a new task. Returns the created task details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "project_id": {
                    "type": "string",
                    "description": "Project ID to assign to (optional)",
                },
                "estimated_minutes": {
                    "type": "integer",
                    "description": "Estimated time in minutes (default 15)",
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date in YYYY-MM-DD format (optional)",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task as completed. Optionally log time spent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to complete",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Minutes spent (optional, 0 to skip)",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Permanently delete a task and its time entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to delete",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "rename_task",
        "description": "Change a task's title.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to rename",
                },
                "new_title": {
                    "type": "string",
                    "description": "New title for the task",
                },
            },
            "required": ["task_id", "new_title"],
        },
    },
    {
        "name": "postpone_task",
        "description": "Postpone a task by one day. Returns new due date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to postpone",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "set_due_date",
        "description": (
            "Set or clear a task's due date. "
            "Pass null for due_date to remove it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task",
                },
                "due_date": {
                    "type": ["string", "null"],
                    "description": "YYYY-MM-DD or null to clear",
                },
            },
            "required": ["task_id", "due_date"],
        },
    },
    {
        "name": "assign_project",
        "description": (
            "Move a task to a different project. "
            "Pass null for project_id to unassign."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task",
                },
                "project_id": {
                    "type": ["string", "null"],
                    "description": "Target project ID, or null to unassign",
                },
            },
            "required": ["task_id", "project_id"],
        },
    },
    {
        "name": "save_daily_note",
        "description": (
            "Write or update a daily note for a specific date. "
            "Content should use markdown formatting. "
            "Fix typos, avoid em-dashes (use regular dashes), "
            "and avoid unnecessary capitalization "
            "(capitalize only sentence starts and proper nouns)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format",
                },
                "content": {
                    "type": "string",
                    "description": "Note content in markdown",
                },
            },
            "required": ["date", "content"],
        },
    },
    {
        "name": "get_recent_notes",
        "description": "Get recent daily notes (newest first).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max notes to return (default 30)",
                },
            },
        },
    },
    {
        "name": "get_tasks",
        "description": (
            "Get pending (not completed) tasks. "
            "Can filter by project and date range."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Filter by project ID (optional)",
                },
                "due_before": {
                    "type": "string",
                    "description": "Due on or before YYYY-MM-DD (optional)",
                },
                "due_after": {
                    "type": "string",
                    "description": "Due after YYYY-MM-DD (optional)",
                },
            },
        },
    },
    {
        "name": "get_done_tasks",
        "description": "Get completed tasks. Can filter by project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Filter by project ID (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                },
            },
        },
    },
    {
        "name": "get_projects",
        "description": "List all projects with their IDs, icons, and colors.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_project",
        "description": "Create a new project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Project name",
                },
                "icon": {
                    "type": "string",
                    "description": "Emoji icon (default 📁)",
                },
                "color": {
                    "type": "string",
                    "description": "Hex color like #2196f3 (default blue)",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "set_recurrence",
        "description": (
            "Set a recurring schedule on a task "
            "(daily, weekly, or monthly)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task",
                },
                "frequency": {
                    "type": "string",
                    "enum": ["days", "weeks", "months"],
                    "description": "Recurrence frequency",
                },
                "interval": {
                    "type": "integer",
                    "description": "Repeat every N units (default 1)",
                },
                "weekdays": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Days of week 0=Mon..6=Sun (weekly only)",
                },
                "from_completion": {
                    "type": "boolean",
                    "description": "Next date from completion date",
                },
            },
            "required": ["task_id", "frequency"],
        },
    },
    {
        "name": "clear_recurrence",
        "description": "Remove recurrence from a task (stop repeating).",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_time_entries",
        "description": (
            "Get time tracking entries for a task. "
            "Returns each session's start time, end time, and duration in minutes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to get time entries for",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "log_time",
        "description": (
            "Log time spent on a task without completing it. "
            "Creates a time entry and updates the task's tracked time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to log time against",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Minutes spent working on the task",
                },
            },
            "required": ["task_id", "duration_minutes"],
        },
    },
    {
        "name": "add_draft",
        "description": (
            "Create a draft task - an idea or plan that isn't active yet. "
            "Drafts don't appear in the main task list until published."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Draft task title"},
                "project_id": {
                    "type": "string",
                    "description": "Project ID to assign to (optional)",
                },
                "estimated_minutes": {
                    "type": "integer",
                    "description": "Estimated time in minutes (default 15)",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "get_drafts",
        "description": "List all draft tasks that haven't been published yet.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "publish_draft",
        "description": (
            "Promote a draft to an active task. "
            "Sets due date to today and adds it to the task list."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the draft task to publish",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_stats",
        "description": (
            "Get user productivity statistics: tasks completed, time tracked, "
            "estimation accuracy, completion streak, daily breakdown, "
            "and per-project stats. Use this when the user asks about their "
            "productivity, progress, or habits."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days for daily breakdown (default 7)",
                },
            },
        },
    },
]


def _build_system_prompt(state: AppState) -> str:
    """Build a context-rich system prompt for Claude."""
    today = date.today().isoformat()

    project_lines = []
    for p in state.projects:
        project_lines.append(f"  - {p.icon} {p.name} (id: \"{p.id}\")")
    projects_str = "\n".join(project_lines) if project_lines else "  (none)"

    color_names = ", ".join(c["name"] for c in PROJECT_COLORS[:8])

    return (
        "You are an assistant inside Trebnic, a task manager app. "
        f"Today is {today}.\n\n"
        f"The user's projects:\n{projects_str}\n\n"
        f"They have {len(state.tasks)} pending tasks.\n\n"
        "Use the provided tools to manage tasks. When adding tasks, "
        "pick the most relevant project based on the task description. "
        "If unsure about a project, ask the user. "
        "Dates use YYYY-MM-DD format.\n\n"
        f"Available project colors: {color_names}\n\n"
        "Be concise — this is a mobile chat interface."
    )


def _parse_date(s: Optional[str]) -> Optional[date]:
    """Parse a YYYY-MM-DD string to a date, or None."""
    if not s:
        return None
    return date.fromisoformat(s)


def _task_summary(task: Any) -> Dict[str, Any]:
    """Produce a compact JSON-friendly summary of a task."""
    result: Dict[str, Any] = {"id": task.id, "title": task.title}
    if task.due_date:
        d = task.due_date
        result["due_date"] = d.isoformat() if isinstance(d, date) else str(d)
    if task.project_id:
        result["project_id"] = task.project_id
    if task.estimated_seconds:
        result["estimated_minutes"] = task.estimated_seconds // 60
    if task.spent_seconds:
        result["spent_minutes"] = task.spent_seconds // 60
    if task.recurrent:
        result["recurrent"] = True
    if task.is_draft:
        result["is_draft"] = True
    return result


def _time_entry_summary(entry: Any) -> Dict[str, Any]:
    """Produce a compact JSON-friendly summary of a time entry."""
    result: Dict[str, Any] = {
        "id": entry.id,
        "start_time": entry.start_time.isoformat(),
        "duration_minutes": entry.duration_seconds // 60,
    }
    if entry.end_time:
        result["end_time"] = entry.end_time.isoformat()
    else:
        result["running"] = True
    return result


# ── API key helpers (encrypted at rest) ──────────────────────────────────

async def save_api_key(key: str) -> None:
    """Save API key, encrypting it if encryption is enabled."""
    encrypted = _encrypt_field(key) or key
    await db.set_setting(SETTING_KEY, encrypted)


async def load_api_key() -> Optional[str]:
    """Load and decrypt the API key. Returns None if not set."""
    raw = await db.get_setting(SETTING_KEY)
    if not raw:
        return None
    decrypted = _decrypt_field(raw)
    return decrypted


# ── Service ──────────────────────────────────────────────────────────────

class ClaudeService:
    """Handles communication with the Claude Messages API."""

    def __init__(self, api: TrebnicAPI) -> None:
        self._api = api

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        state: AppState,
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Send a conversation to Claude and handle tool_use loops.

        Returns:
            (final_text_response, tool_actions) where tool_actions is a
            list of dicts like {"action": "Created", "detail": "..."}.

        Raises:
            ValueError: If API key is not configured.
            httpx.HTTPStatusError: On API errors (4xx/5xx).
            httpx.TimeoutException: On request timeout.
        """
        api_key = await load_api_key()
        if not api_key:
            raise ValueError(t("api_key_required"))

        system_prompt = _build_system_prompt(state)
        tool_actions: List[Dict[str, str]] = []
        conversation = list(messages)

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            for _ in range(10):  # Safety limit on tool loops
                payload = {
                    "model": MODEL,
                    "max_tokens": MAX_TOKENS,
                    "temperature": TEMPERATURE,
                    "system": system_prompt,
                    "messages": conversation,
                    "tools": TOOLS,
                }

                resp = await client.post(
                    API_URL,
                    json=payload,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                stop_reason = data.get("stop_reason", "end_turn")
                content_blocks = data.get("content", [])

                text_parts = []
                tool_uses = []
                for block in content_blocks:
                    if block["type"] == "text":
                        text_parts.append(block["text"])
                    elif block["type"] == "tool_use":
                        tool_uses.append(block)

                if stop_reason != "tool_use" or not tool_uses:
                    return "\n".join(text_parts), tool_actions

                conversation.append({
                    "role": "assistant", "content": content_blocks,
                })

                tool_results = []
                for tu in tool_uses:
                    result_str, action = await self._execute_tool(
                        tu["name"], tu["input"], state,
                    )
                    if action:
                        tool_actions.append(action)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": result_str,
                    })

                conversation.append({
                    "role": "user", "content": tool_results,
                })

        return "Sorry, I couldn't complete the request.", tool_actions

    async def _execute_tool(
        self,
        name: str,
        args: Dict[str, Any],
        state: AppState,
    ) -> Tuple[str, Optional[Dict[str, str]]]:
        """Execute a tool call. Never raises — errors become tool_result."""
        try:
            return await self._dispatch(name, args, state)
        except Exception as exc:
            logger.exception("Tool execution error: %s", name)
            return json.dumps({"error": str(exc)}), None

    async def _dispatch(
        self,
        name: str,
        args: Dict[str, Any],
        state: AppState,
    ) -> Tuple[str, Optional[Dict[str, str]]]:
        """Route a tool call to the matching TrebnicAPI method."""

        if name == "add_task":
            due = _parse_date(args.get("due_date"))
            est = args.get("estimated_minutes", 15)
            task = await self._api.add_task(
                title=args["title"],
                project_id=args.get("project_id"),
                estimated_seconds=est * 60,
                due_date=due,
            )
            return (
                json.dumps(_task_summary(task)),
                {"action": t("task_created_chat"), "detail": task.title},
            )

        if name == "complete_task":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            dur = args.get("duration_minutes", 0) * 60
            await self._api.complete_task(task, duration_seconds=dur)
            return (
                json.dumps({"completed": task.title}),
                {"action": t("task_completed_chat"), "detail": task.title},
            )

        if name == "delete_task":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            title = task.title
            await self._api.delete_task(task)
            return (
                json.dumps({"deleted": title}),
                {"action": t("task_deleted_chat"), "detail": title},
            )

        if name == "rename_task":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            old = task.title
            await self._api.rename_task(task, args["new_title"])
            return (
                json.dumps({"renamed": old, "new_title": args["new_title"]}),
                {
                    "action": t("task_renamed_chat"),
                    "detail": f"{old} → {args['new_title']}",
                },
            )

        if name == "postpone_task":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            nd = await self._api.postpone_task(task)
            return (
                json.dumps({
                    "postponed": task.title,
                    "new_due_date": nd.isoformat(),
                }),
                {
                    "action": t("task_postponed_chat"),
                    "detail": f"{task.title} → {nd.isoformat()}",
                },
            )

        if name == "set_due_date":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            due = _parse_date(args.get("due_date"))
            await self._api.set_due_date(task, due)
            label = due.isoformat() if due else "none"
            return (
                json.dumps({"task": task.title, "due_date": label}),
                {"action": t("reschedule"), "detail": f"{task.title} → {label}"},
            )

        if name == "assign_project":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            pid = args.get("project_id")
            await self._api.assign_project(task, pid)
            proj = state.get_project_by_id(pid)
            pname = proj.name if proj else "none"
            return (
                json.dumps({"task": task.title, "project": pname}),
                {
                    "action": t("assign_to_project"),
                    "detail": f"{task.title} → {pname}",
                },
            )

        if name == "save_daily_note":
            note_date = date.fromisoformat(args["date"])
            note = await self._api.save_daily_note(note_date, args["content"])
            return (
                json.dumps({
                    "saved": note.date.isoformat(),
                    "length": len(note.content),
                }),
                {
                    "action": t("daily_note_saved"),
                    "detail": note.date.isoformat(),
                },
            )

        if name == "get_recent_notes":
            notes = await self._api.get_recent_notes(
                limit=args.get("limit", 30),
            )
            return json.dumps({
                "notes": notes, "count": len(notes),
            }), None

        if name == "get_tasks":
            tasks = await self._api.get_tasks(
                project_id=args.get("project_id"),
                due_before=_parse_date(args.get("due_before")),
                due_after=_parse_date(args.get("due_after")),
            )
            sums = [_task_summary(tk) for tk in tasks]
            return json.dumps({"tasks": sums, "count": len(sums)}), None

        if name == "get_done_tasks":
            tasks = await self._api.get_done_tasks(
                project_id=args.get("project_id"),
                limit=args.get("limit", 50),
            )
            sums = [_task_summary(tk) for tk in tasks]
            return json.dumps({"tasks": sums, "count": len(sums)}), None

        if name == "get_projects":
            projects = [
                {
                    "id": p.id, "name": p.name,
                    "icon": p.icon, "color": p.color,
                }
                for p in state.projects
            ]
            return json.dumps({"projects": projects}), None

        if name == "create_project":
            proj = await self._api.create_project(
                name=args["name"],
                icon=args.get("icon", "📁"),
                color=args.get("color", "#2196f3"),
            )
            return (
                json.dumps({
                    "id": proj.id, "name": proj.name,
                    "icon": proj.icon, "color": proj.color,
                }),
                {
                    "action": t("task_created_chat"),
                    "detail": f"📁 {proj.name}",
                },
            )

        if name == "set_recurrence":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            freq = RecurrenceFrequency(args["frequency"])
            await self._api.set_recurrence(
                task=task,
                frequency=freq,
                interval=args.get("interval", 1),
                weekdays=args.get("weekdays"),
                from_completion=args.get("from_completion", False),
            )
            return (
                json.dumps({
                    "recurrence_set": task.title,
                    "frequency": args["frequency"],
                }),
                {"action": t("recurrence_set_chat"), "detail": task.title},
            )

        if name == "clear_recurrence":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            await self._api.clear_recurrence(task)
            return (
                json.dumps({"recurrence_cleared": task.title}),
                {"action": t("recurrence_set_chat"), "detail": task.title},
            )

        if name == "get_time_entries":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            entries = await self._api.get_time_entries(args["task_id"])
            summaries = [_time_entry_summary(e) for e in entries]
            total_minutes = sum(e.duration_seconds for e in entries) // 60
            return json.dumps({
                "task": task.title,
                "entries": summaries,
                "count": len(summaries),
                "total_minutes": total_minutes,
            }), None

        if name == "log_time":
            task = state.get_task_by_id(args["task_id"])
            if not task:
                return _not_found(args["task_id"]), None
            dur = args["duration_minutes"] * 60
            entry = await self._api.log_time(task, duration_seconds=dur)
            return (
                json.dumps({
                    "task": task.title,
                    "logged_minutes": args["duration_minutes"],
                    "total_spent_minutes": task.spent_seconds // 60,
                }),
                {
                    "action": t("time_logged_chat"),
                    "detail": f"{task.title} +{args['duration_minutes']}m",
                },
            )

        if name == "add_draft":
            est = args.get("estimated_minutes", 15)
            task = await self._api.add_draft(
                title=args["title"],
                project_id=args.get("project_id"),
                estimated_seconds=est * 60,
            )
            return (
                json.dumps(_task_summary(task)),
                {"action": t("draft_created_chat"), "detail": task.title},
            )

        if name == "get_drafts":
            drafts = await self._api.get_drafts()
            sums = [_task_summary(tk) for tk in drafts]
            return json.dumps({"drafts": sums, "count": len(sums)}), None

        if name == "publish_draft":
            task_id = args["task_id"]
            drafts = await self._api.get_drafts()
            task = next((d for d in drafts if d.id == task_id), None)
            if not task:
                return json.dumps({"error": f"Draft {task_id} not found"}), None
            await self._api.publish_draft(task)
            return (
                json.dumps({"published": task.title, "due_date": task.due_date.isoformat()}),
                {"action": t("draft_published_chat"), "detail": task.title},
            )

        if name == "get_stats":
            days = args.get("days", 7)
            time_entries = await db.load_time_entries()

            overall = stats_service.calculate_overall_stats(
                state.tasks, state.done_tasks, time_entries,
            )
            streak = stats_service.calculate_completion_streak(state.done_tasks)
            daily = stats_service.calculate_daily_stats(
                time_entries, state.done_tasks, state.tasks, days=days,
            )
            project_stats = stats_service.calculate_project_stats(
                state.tasks, state.done_tasks, state.projects,
            )

            result = {
                "overall": {
                    "tasks_completed": overall.total_tasks_completed,
                    "tasks_pending": overall.total_tasks_pending,
                    "total_time_tracked_minutes": overall.total_time_tracked_seconds // 60,
                    "avg_estimation_accuracy_percent": round(overall.avg_estimation_accuracy, 1),
                    "longest_streak_days": streak,
                },
                "daily": [
                    {
                        "date": ds.date.isoformat(),
                        "tracked_minutes": ds.tracked_seconds // 60,
                        "tasks_completed": ds.tasks_completed,
                    }
                    for ds in daily
                ],
                "by_project": [
                    {
                        "project": ps.project_name,
                        "tracked_minutes": ps.tracked_seconds // 60,
                        "completed": ps.tasks_completed,
                        "pending": ps.tasks_pending,
                    }
                    for ps in project_stats
                ],
            }
            return json.dumps(result), None

        return json.dumps({"error": f"Unknown tool: {name}"}), None


def _not_found(task_id: int) -> str:
    return json.dumps({"error": f"Task {task_id} not found"})
