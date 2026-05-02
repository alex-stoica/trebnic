"""
Notification service for Trebnic.

Daily digest model: instead of per-task reminders, schedules up to 3 daily
notifications (morning digest, evening preview, overdue nudge) plus immediate
timer-complete notifications.

On Android: uses AlarmManager via flet_android_notifications for scheduled digests.
On desktop: a scheduler loop checks every 60 seconds if a digest is due.
"""
import asyncio
import json
import logging
import threading
from datetime import date, datetime, timedelta, time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from config import (
    DIGEST_NOTIFICATION_ID,
    PREVIEW_NOTIFICATION_ID,
    OVERDUE_NOTIFICATION_ID,
    TASK_NUDGE_NOTIFICATION_ID,
    TASK_NUDGE_SUMMARY_NOTIFICATION_ID,
    NOTIFICATION_HORIZON_DAYS,
    NOTIFICATION_HORIZON_STRIDE,
    TASK_NUDGE_MAX_PER_DAY,
    PermissionResult,
)
from database import db, DatabaseError
from events import event_bus, AppEvent, Subscription
from i18n import t
from models.entities import Task
from registry import registry, Services

logger = logging.getLogger(__name__)

ANDROID_13_API_LEVEL = 33
SCHEDULER_INTERVAL_SECONDS = 60


class NotificationBackend(Enum):
    """Available notification backends."""
    FLET_EXTENSION = "flet_extension"
    PLYER = "plyer"
    NONE = "none"


PLYER_AVAILABLE = False
FLET_EXTENSION_AVAILABLE = False

try:
    from flet_android_notifications import FletAndroidNotifications, NotificationError, BigTextStyle, InboxStyle
    FLET_EXTENSION_AVAILABLE = True
    logger.info("Flet Android notifications extension available")
except ImportError:
    logger.info("flet_android_notifications not available")

if not FLET_EXTENSION_AVAILABLE:
    try:
        from plyer import notification as plyer_notification
        PLYER_AVAILABLE = True
        logger.info("plyer available for desktop")
    except ImportError:
        logger.info("plyer not available")


def _detect_notification_backend() -> NotificationBackend:
    if FLET_EXTENSION_AVAILABLE:
        return NotificationBackend.FLET_EXTENSION
    if PLYER_AVAILABLE:
        return NotificationBackend.PLYER
    return NotificationBackend.NONE


class NotificationService:
    """Manages daily digest notifications and immediate timer-complete alerts."""

    _instance: Optional["NotificationService"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "NotificationService":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._backend = _detect_notification_backend()
        logger.warning(f"[NOTIF] Backend detected: {self._backend.value}")

        self._page = None
        self._schedule_async: Optional[Callable[..., asyncio.Task]] = None
        self._get_state: Optional[Callable[[], Any]] = None

        self._flet_notifications = None
        self._running = False
        self._stop_event: asyncio.Event = asyncio.Event()
        self._subscriptions: List[Subscription] = []

        self._initialized = True

    def inject_dependencies(
        self,
        page: Any,
        async_scheduler: Callable[..., asyncio.Task],
        get_state: Callable[[], Any],
    ) -> None:
        self._page = page
        self._schedule_async = async_scheduler
        self._get_state = get_state

        if self._backend == NotificationBackend.FLET_EXTENSION and FLET_EXTENSION_AVAILABLE:
            self._flet_notifications = FletAndroidNotifications(on_notification_tap=self._on_notification_tapped)
            logger.warning(f"[NOTIF] FletAndroidNotifications created: {self._flet_notifications is not None}")

    # ── Permission handling ───────────────────────────────────────────

    async def request_permission(self) -> PermissionResult:
        if self._backend == NotificationBackend.PLYER:
            return PermissionResult.GRANTED

        if self._backend == NotificationBackend.FLET_EXTENSION and self._flet_notifications is not None:
            try:
                result = await self._flet_notifications.request_permissions()
                logger.warning(f"[NOTIF] request_permissions raw result: {result!r}")
                granted = str(result).lower() == "true"
                return PermissionResult.GRANTED if granted else PermissionResult.DENIED
            except NotificationError as e:
                logger.error(f"[NOTIF] Error requesting notification permission: {e}")
                return PermissionResult.DENIED

        return PermissionResult.NOT_REQUIRED

    async def request_exact_alarm_permission(self) -> PermissionResult:
        if self._backend != NotificationBackend.FLET_EXTENSION:
            return PermissionResult.GRANTED
        if self._flet_notifications is None:
            return PermissionResult.NOT_REQUIRED
        try:
            result = await self._flet_notifications.request_exact_alarm_permission()
            granted = str(result).lower() == "true"
            return PermissionResult.GRANTED if granted else PermissionResult.DENIED
        except NotificationError as e:
            logger.error(f"Error requesting exact alarm permission: {e}")
            return PermissionResult.DENIED

    # ── Scheduler lifecycle ───────────────────────────────────────────

    def start_scheduler(self) -> None:
        if self._running:
            return
        if self._schedule_async is None:
            raise RuntimeError("NotificationService dependencies not injected")

        self._running = True
        self._stop_event.clear()
        self._subscribe_to_events()

        # Desktop needs a polling loop; Android uses AlarmManager
        if self._backend != NotificationBackend.FLET_EXTENSION:
            self._schedule_async(self._scheduler_loop)

        # Schedule digest alarms on startup
        self._schedule_async(self._schedule_all_digests)
        logger.info("Notification scheduler started")

    def stop_scheduler(self) -> None:
        self._running = False
        self._stop_event.set()
        self._unsubscribe_from_events()
        logger.info("Notification scheduler stopped")

    def _subscribe_to_events(self) -> None:
        """Subscribe to every event that can change digest content, count, or language.

        The Android backend bakes body+style into the alarm at schedule time, so any
        mutation that affects what tomorrow's digest *would* say has to trigger a
        full reschedule.
        """
        for evt in (
            AppEvent.TASK_CREATED, AppEvent.TASK_UPDATED, AppEvent.TASK_COMPLETED,
            AppEvent.TASK_UNCOMPLETED, AppEvent.TASK_DELETED, AppEvent.TASK_POSTPONED,
            AppEvent.TASK_DUPLICATED, AppEvent.TASK_RENAMED,
            AppEvent.DATA_RESET, AppEvent.LANGUAGE_CHANGED,
        ):
            self._subscriptions.append(event_bus.subscribe(evt, self._on_task_mutation))

    def _unsubscribe_from_events(self) -> None:
        for sub in self._subscriptions:
            sub.unsubscribe()
        self._subscriptions.clear()

    def _on_task_mutation(self, data: Any) -> None:
        """Reschedule digests so Android alarm body reflects the latest task list."""
        if not self._running or self._schedule_async is None:
            return
        self._schedule_async(self._schedule_all_digests)

    # ── Desktop polling loop ──────────────────────────────────────────

    async def _scheduler_loop(self) -> None:
        """Desktop: poll every 60s, fire digests when their scheduled time passes."""
        logger.info("Notification scheduler loop started")
        try:
            while self._running and not self._stop_event.is_set():
                await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)
                if self._stop_event.is_set() or not self._running:
                    break
                await self._check_and_fire_digests()
        except asyncio.CancelledError:
            logger.info("Notification scheduler loop cancelled")
        except (DatabaseError, OSError, RuntimeError) as e:
            logger.error(f"Error in notification scheduler loop: {e}")
            self._running = False

    async def _check_and_fire_digests(self) -> None:
        """Desktop: check if any digest notification should fire now."""
        if not self._is_notifications_enabled():
            return

        state = self._get_state() if self._get_state else None
        if state is None:
            return

        now = datetime.now()
        today_str = date.today().isoformat()

        # Morning digest
        if state.daily_digest_enabled:
            await self._fire_digest_if_due(
                "daily_digest", state.daily_digest_time, today_str, now,
                self._build_morning_digest,
            )

        # Evening preview
        if state.evening_preview_enabled:
            await self._fire_digest_if_due(
                "evening_preview", state.evening_preview_time, today_str, now,
                self._build_evening_preview,
            )

        # Overdue nudge
        if state.overdue_nudge_enabled:
            await self._fire_digest_if_due(
                "overdue_nudge", state.overdue_nudge_time, today_str, now,
                self._build_overdue_nudge,
            )

        # Actionable per-task nudges
        if state.task_nudges_enabled:
            await self._fire_task_nudges_if_due(state.task_nudge_time, today_str, now)

    async def _fire_digest_if_due(
        self,
        digest_key: str,
        scheduled_time: time,
        today_str: str,
        now: datetime,
        builder: Callable,
    ) -> None:
        """Fire a digest if it's past scheduled time and hasn't fired today."""
        if now.time() < scheduled_time:
            return

        setting_key = f"last_{digest_key}_date"
        last_fired = await db.get_setting(setting_key, "")
        if last_fired == today_str:
            return

        if self._is_in_quiet_hours():
            return

        result = await builder()
        if result is None:
            # No tasks to report — mark as fired so we don't check again today
            await db.set_setting(setting_key, today_str)
            return

        title, body, style = result
        digest_actions = [{"id": "open_tasks", "title": t("notif_action_open")}]
        await self._deliver_immediate(title, body, actions=digest_actions, style=style)
        await db.set_setting(setting_key, today_str)

    async def _fire_task_nudges_if_due(self, scheduled_time: time, today_str: str, now: datetime) -> None:
        """Desktop: fire actionable task nudges once per day when due."""
        if now.time() < scheduled_time:
            return

        setting_key = "last_task_nudges_date"
        last_fired = await db.get_setting(setting_key, "")
        if last_fired == today_str:
            return

        if self._is_in_quiet_hours():
            return

        target = date.today()
        candidates = await self._load_task_nudge_candidates(target)
        if not candidates:
            await db.set_setting(setting_key, today_str)
            return

        await self._deliver_task_nudges_now(candidates, target)
        await db.set_setting(setting_key, today_str)

    # ── Digest builders ───────────────────────────────────────────────
    # Each builder accepts an optional ``target_date`` so the caller can prebuild
    # a future day's digest (used by the Android rolling-horizon scheduler). The
    # query goes straight to the DB rather than ``state.tasks`` because the UI
    # mutation paths persist to SQLite without refreshing AppState in lockstep.

    async def _build_morning_digest(self, target_date: Optional[date] = None) -> Optional[tuple]:
        """Build morning digest: tasks due on target_date. Returns (title, body, style)."""
        target = target_date if target_date is not None else date.today()
        try:
            rows = await db.load_tasks_filtered(is_done=False, due_date_eq=target)
        except DatabaseError:
            return None
        if not rows:
            return None

        due_tasks = [Task.from_dict(r) for r in rows]
        title = "Trebnic"
        body = t("tasks_due_today").replace("{count}", str(len(due_tasks)))
        style = self._build_inbox_style(due_tasks)
        return title, body, style

    async def _build_evening_preview(self, target_date: Optional[date] = None) -> Optional[tuple]:
        """Build evening preview: tasks due the day after target_date."""
        target = target_date if target_date is not None else date.today()
        tomorrow = target + timedelta(days=1)
        try:
            rows = await db.load_tasks_filtered(is_done=False, due_date_eq=tomorrow)
        except DatabaseError:
            return None
        if not rows:
            return None

        due_tasks = [Task.from_dict(r) for r in rows]
        title = "Trebnic"
        body = t("tasks_due_tomorrow").replace("{count}", str(len(due_tasks)))
        style = self._build_inbox_style(due_tasks)
        return title, body, style

    async def _build_overdue_nudge(self, target_date: Optional[date] = None) -> Optional[tuple]:
        """Build overdue nudge: tasks with due_date strictly before target_date."""
        target = target_date if target_date is not None else date.today()
        # ``due_date_lte`` is inclusive; subtract one day to get strict-less-than.
        cutoff = target - timedelta(days=1)
        try:
            rows = await db.load_tasks_filtered(is_done=False, due_date_lte=cutoff)
        except DatabaseError:
            return None
        if not rows:
            return None

        overdue_tasks = [Task.from_dict(r) for r in rows]
        title = "Trebnic"
        body = t("tasks_overdue").replace("{count}", str(len(overdue_tasks)))
        style = self._build_inbox_style(overdue_tasks)
        return title, body, style

    def _build_inbox_style(self, tasks: List[Task]) -> Any:
        """Build InboxStyle from task list. Returns BigTextStyle fallback if locked or extension unavailable."""
        if not FLET_EXTENSION_AVAILABLE:
            return None

        if self._is_app_locked():
            lines = [t("tasks_list_locked")]
            return InboxStyle(lines=lines)

        max_lines = 5
        lines = [task.title for task in tasks[:max_lines]]
        summary_text = None
        if len(tasks) > max_lines:
            summary_text = t("and_n_more").replace("{count}", str(len(tasks) - max_lines))
        return InboxStyle(lines=lines, summary_text=summary_text)

    async def _load_task_nudge_candidates(self, target_date: date, limit: Optional[int] = None) -> List[Task]:
        """Load pending dated tasks that should receive actionable nudges."""
        try:
            rows = await db.load_tasks_filtered(is_done=False, due_date_lte=target_date)
        except DatabaseError:
            return []

        tasks = [Task.from_dict(r) for r in rows if r.get("due_date") is not None]
        tasks.sort(key=lambda task: (task.due_date or date.max, task.sort_order, task.id or 0))
        return tasks[:limit] if limit is not None else tasks

    def _task_nudge_payload(self, task: Task, target_date: date) -> Dict[str, Any]:
        return {
            "kind": "task_nudge",
            "task_id": task.id,
            "target_date": target_date.isoformat(),
        }

    def _task_nudge_actions(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "task_done",
                "title": t("notif_action_done"),
                "shows_user_interface": True,
                "cancel_notification": True,
            },
            {
                "id": "task_postpone_1d",
                "title": t("notif_action_postpone"),
                "shows_user_interface": True,
                "cancel_notification": True,
            },
            {
                "id": "open_task",
                "title": t("notif_action_open"),
                "shows_user_interface": True,
                "cancel_notification": True,
            },
        ]

    def _task_nudge_text(self, task: Task, target_date: date) -> tuple[str, str]:
        if self._is_app_locked():
            return t("task_reminder"), t("unlock_to_see_details")

        title = task.title
        if task.due_date and task.due_date < target_date:
            body = t("task_nudge_overdue_body").replace("{date}", task.due_date.strftime("%b %d"))
        else:
            body = t("task_nudge_due_today_body")
        return title, body

    def _task_nudge_summary(self, candidates: List[Task]) -> tuple[str, str, Any]:
        count = len(candidates)
        title = t("task_nudges_summary_title").replace("{count}", str(count))
        body = t("task_nudges_summary_body")
        style = self._build_inbox_style(candidates)
        return title, body, style

    async def _deliver_task_nudges_now(self, candidates: List[Task], target_date: date) -> None:
        """Deliver today's task nudges immediately for desktop or manual firing."""
        shown = candidates[:TASK_NUDGE_MAX_PER_DAY]
        for slot, task in enumerate(shown):
            title, body = self._task_nudge_text(task, target_date)
            await self._deliver_immediate(
                title,
                body,
                task_id=task.id,
                payload=self._task_nudge_payload(task, target_date),
                actions=self._task_nudge_actions(),
                notification_id=TASK_NUDGE_NOTIFICATION_ID + slot,
                channel_id="trebnic_task_nudges",
                channel_name="Task nudges",
                group_key="trebnic_task_nudges",
                visibility="private",
                category="reminder",
            )

        if len(candidates) > TASK_NUDGE_MAX_PER_DAY:
            title, body, style = self._task_nudge_summary(candidates)
            await self._deliver_immediate(
                title,
                body,
                payload={"kind": "task_nudge_summary", "target_date": target_date.isoformat()},
                actions=[{"id": "open_tasks", "title": t("notif_action_open")}],
                style=style,
                notification_id=TASK_NUDGE_SUMMARY_NOTIFICATION_ID,
                channel_id="trebnic_task_nudges",
                channel_name="Task nudges",
                group_key="trebnic_task_nudges",
                set_as_group_summary=True,
                group_alert_behavior="summary",
                visibility="private",
                category="reminder",
            )

    # ── Digest scheduling (Android + reschedule after settings change) ──

    async def _cancel_all_digest_alarms(self) -> None:
        """Cancel every digest alarm across the rolling horizon.

        Called before every reschedule and whenever notifications are disabled,
        so the device never holds an alarm whose schedule no longer reflects
        user intent. Sweeps the full ID grid (base + offset*stride) without
        needing to track which slots were actually filled.
        """
        if self._backend != NotificationBackend.FLET_EXTENSION:
            return
        for base_nid in (DIGEST_NOTIFICATION_ID, PREVIEW_NOTIFICATION_ID, OVERDUE_NOTIFICATION_ID):
            for offset in range(NOTIFICATION_HORIZON_DAYS):
                await self._cancel_extension_notification(base_nid + offset * NOTIFICATION_HORIZON_STRIDE)

    async def _cancel_all_task_nudge_alarms(self) -> None:
        """Cancel every task nudge child and summary notification across the horizon."""
        if self._backend != NotificationBackend.FLET_EXTENSION:
            return
        for offset in range(NOTIFICATION_HORIZON_DAYS):
            day_base = TASK_NUDGE_NOTIFICATION_ID + offset * NOTIFICATION_HORIZON_STRIDE
            for slot in range(TASK_NUDGE_MAX_PER_DAY):
                await self._cancel_extension_notification(day_base + slot)
            await self._cancel_extension_notification(
                TASK_NUDGE_SUMMARY_NOTIFICATION_ID + offset * NOTIFICATION_HORIZON_STRIDE
            )

    async def _schedule_all_digests(self) -> None:
        """Cancel any prior schedule, then re-schedule if notifications are enabled.

        The cancel step runs unconditionally so toggling notifications off
        actually silences the device — previously it short-circuited before
        cancellation, leaving stale alarms armed.
        """
        await self._cancel_all_digest_alarms()
        await self._cancel_all_task_nudge_alarms()

        if not self._is_notifications_enabled():
            return

        state = self._get_state() if self._get_state else None
        if state is None:
            return

        if self._backend == NotificationBackend.FLET_EXTENSION:
            await self._schedule_android_digests(state)
        # Desktop uses the polling loop, no explicit scheduling needed

    async def _schedule_android_digests(self, state: Any) -> None:
        """Schedule a rolling 7-day horizon of one-shot AlarmManager alarms per digest.

        The extension has no on-fire callback, so the body and style are baked in
        at schedule time. Instead of one daily-repeat alarm whose payload goes
        stale immediately, we schedule one one-shot per day with content built
        for *that* trigger date. Mutation events refill the horizon; users who
        leave the app closed past 7 days simply stop getting reminders.
        """
        try:
            has_pending_rows = await db.load_tasks_filtered(is_done=False, limit=1)
        except DatabaseError:
            has_pending_rows = []
        if not has_pending_rows:
            return

        digest_actions = [{"id": "open_tasks", "title": t("notif_action_open")}]

        async def schedule_horizon(
            base_nid: int, enabled: bool, target_time: time, builder: Callable,
        ) -> None:
            if not enabled:
                return
            first_trigger = self._next_trigger_time(target_time)
            for offset in range(NOTIFICATION_HORIZON_DAYS):
                trigger = first_trigger + timedelta(days=offset)
                built = await builder(target_date=trigger.date())
                if built is not None:
                    title, body, style = built
                else:
                    title, body, style = "Trebnic", t("digest_check_app"), None
                nid = base_nid + offset * NOTIFICATION_HORIZON_STRIDE
                await self._schedule_extension_notification(
                    nid, title, body, trigger, None,
                    actions=digest_actions,
                    style=style,
                )

        await schedule_horizon(
            DIGEST_NOTIFICATION_ID, state.daily_digest_enabled,
            state.daily_digest_time, self._build_morning_digest,
        )
        await schedule_horizon(
            PREVIEW_NOTIFICATION_ID, state.evening_preview_enabled,
            state.evening_preview_time, self._build_evening_preview,
        )
        await schedule_horizon(
            OVERDUE_NOTIFICATION_ID, state.overdue_nudge_enabled,
            state.overdue_nudge_time, self._build_overdue_nudge,
        )
        await self._schedule_android_task_nudges(state)

    async def _schedule_android_task_nudges(self, state: Any) -> None:
        """Schedule actionable per-task nudges across the Android horizon."""
        if not state.task_nudges_enabled:
            return

        first_trigger = self._next_trigger_time(state.task_nudge_time)
        for offset in range(NOTIFICATION_HORIZON_DAYS):
            trigger = first_trigger + timedelta(days=offset)
            target = trigger.date()
            candidates = await self._load_task_nudge_candidates(target)
            if not candidates:
                continue

            has_summary = len(candidates) > TASK_NUDGE_MAX_PER_DAY
            group_alert_behavior = "summary" if has_summary else "all"
            day_base = TASK_NUDGE_NOTIFICATION_ID + offset * NOTIFICATION_HORIZON_STRIDE

            for slot, task in enumerate(candidates[:TASK_NUDGE_MAX_PER_DAY]):
                title, body = self._task_nudge_text(task, target)
                await self._schedule_extension_notification(
                    day_base + slot,
                    title,
                    body,
                    trigger,
                    task.id,
                    actions=self._task_nudge_actions(),
                    style=BigTextStyle(big_text=body) if FLET_EXTENSION_AVAILABLE else None,
                    payload=self._task_nudge_payload(task, target),
                    channel_id="trebnic_task_nudges",
                    channel_name="Task nudges",
                    channel_description="Actionable task nudges from Trebnic",
                    group_key="trebnic_task_nudges",
                    group_alert_behavior=group_alert_behavior,
                    visibility="private",
                    category="reminder",
                )

            if has_summary:
                title, body, style = self._task_nudge_summary(candidates)
                await self._schedule_extension_notification(
                    TASK_NUDGE_SUMMARY_NOTIFICATION_ID + offset * NOTIFICATION_HORIZON_STRIDE,
                    title,
                    body,
                    trigger,
                    None,
                    actions=[{"id": "open_tasks", "title": t("notif_action_open")}],
                    style=style,
                    payload={"kind": "task_nudge_summary", "target_date": target.isoformat()},
                    channel_id="trebnic_task_nudges",
                    channel_name="Task nudges",
                    channel_description="Actionable task nudges from Trebnic",
                    group_key="trebnic_task_nudges",
                    set_as_group_summary=True,
                    group_alert_behavior="summary",
                    visibility="private",
                    category="reminder",
                )

    def _next_trigger_time(self, target: time) -> datetime:
        """Compute next datetime for a given time-of-day (today or tomorrow)."""
        now = datetime.now()
        candidate = datetime.combine(now.date(), target)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    async def reschedule_digests(self) -> None:
        """Public method to reschedule digests after settings change."""
        await self._schedule_all_digests()

    async def send_overdue_digest_now(self) -> bool:
        """Build and immediately deliver the overdue digest using current state.

        Exercises the real overdue path (builder + delivery) instead of the bare
        delivery-only test. Returns False when there are no overdue tasks so the
        UI can show a "nothing to send" message rather than an empty notification.
        """
        if self._backend == NotificationBackend.NONE:
            return False
        built = await self._build_overdue_nudge()
        if built is None:
            return False
        title, body, style = built
        digest_actions = [{"id": "open_tasks", "title": t("notif_action_open")}]
        await self._deliver_immediate(title, body, actions=digest_actions, style=style)
        return True

    async def show_immediate(
        self,
        title: str,
        body: str,
        task_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
        *,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if not self._is_notifications_enabled():
            return
        if self._is_in_quiet_hours():
            logger.info("Skipping immediate notification - in quiet hours")
            return
        await self._deliver_immediate(title, body, task_id, actions=actions, payload=payload)
        event_bus.emit(AppEvent.NOTIFICATION_FIRED, {
            "task_id": task_id,
            "ntype": "immediate",
            "payload": payload,
        })

    # ── Notification delivery ─────────────────────────────────────────

    async def _deliver_immediate(
        self,
        title: str,
        body: str,
        task_id: Optional[int] = None,
        *,
        actions: Optional[List[Dict[str, Any]]] = None,
        style: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
        notification_id: Optional[int] = None,
        channel_id: str = "trebnic_reminders",
        channel_name: str = "Task reminders",
        channel_description: str = "Task reminders from Trebnic",
        group_key: str = "trebnic_tasks",
        set_as_group_summary: bool = False,
        group_alert_behavior: str = "all",
        visibility: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        """Deliver a notification immediately, handling encryption state."""
        if self._is_app_locked():
            title = t("task_reminder")
            body = t("unlock_to_see_details")

        if self._backend == NotificationBackend.PLYER:
            await self._deliver_plyer_notification(title, body)
        elif self._backend == NotificationBackend.FLET_EXTENSION:
            await self._deliver_extension_notification(
                title,
                body,
                task_id,
                actions=actions,
                style=style,
                payload=payload,
                notification_id=notification_id,
                channel_id=channel_id,
                channel_name=channel_name,
                channel_description=channel_description,
                group_key=group_key,
                set_as_group_summary=set_as_group_summary,
                group_alert_behavior=group_alert_behavior,
                visibility=visibility,
                category=category,
            )

    def _is_app_locked(self) -> bool:
        crypto = registry.get(Services.CRYPTO)
        if crypto is None:
            return False
        if crypto.is_available:
            return not crypto.is_unlocked
        return False

    async def _deliver_extension_notification(
        self,
        title: str,
        body: str,
        task_id: Optional[int] = None,
        *,
        actions: Optional[List[Dict[str, Any]]] = None,
        style: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
        channel_id: str = "trebnic_reminders",
        channel_name: str = "Task reminders",
        channel_description: str = "Task reminders from Trebnic",
        importance: str = "high",
        notification_id: Optional[int] = None,
        group_key: str = "trebnic_tasks",
        set_as_group_summary: bool = False,
        group_alert_behavior: str = "all",
        visibility: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        if self._flet_notifications is None:
            return False
        try:
            nid = notification_id if notification_id else (task_id if task_id else abs(hash(title)) % 100000)
            base_payload = {"task_id": task_id}
            if payload:
                base_payload.update(payload)
            payload_str = json.dumps(base_payload)
            effective_style = style
            if effective_style is None and FLET_EXTENSION_AVAILABLE:
                effective_style = BigTextStyle(big_text=body)
            kwargs: Dict[str, Any] = {
                "notification_id": nid,
                "title": title,
                "body": body,
                "payload": payload_str,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "channel_description": channel_description,
                "importance": importance,
                "group_key": group_key,
                "set_as_group_summary": set_as_group_summary,
                "group_alert_behavior": group_alert_behavior,
                "color": "#4a9eff",
            }
            if effective_style is not None:
                kwargs["style"] = effective_style
            if visibility:
                kwargs["visibility"] = visibility
            if category:
                kwargs["category"] = category
            if actions:
                kwargs["actions"] = actions
            result = await self._flet_notifications.show_notification(**kwargs)
            success = str(result).lower() == "ok"
            logger.warning(f"[NOTIF] show_notification: id={nid}, success={success}")
            return success
        except NotificationError as e:
            logger.error(f"[NOTIF] show_notification failed: {e}")
            return False

    async def _schedule_extension_notification(
        self,
        notification_id: int,
        title: str,
        body: str,
        scheduled_time: datetime,
        task_id: Optional[int],
        *,
        match_date_time_components: Optional[str] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        style: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
        channel_id: str = "trebnic_reminders",
        channel_name: str = "Task reminders",
        channel_description: str = "Task reminders from Trebnic",
        group_key: str = "trebnic_tasks",
        set_as_group_summary: bool = False,
        group_alert_behavior: str = "all",
        visibility: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        if self._flet_notifications is None:
            return False
        try:
            base_payload = {"task_id": task_id}
            if payload:
                base_payload.update(payload)
            payload_str = json.dumps(base_payload)
            effective_style = style
            if effective_style is None and FLET_EXTENSION_AVAILABLE:
                effective_style = BigTextStyle(big_text=body)
            kwargs: Dict[str, Any] = {
                "notification_id": notification_id,
                "title": title,
                "body": body,
                "scheduled_time": scheduled_time,
                "payload": payload_str,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "channel_description": channel_description,
                "schedule_mode": "inexact_allow_while_idle",
                "group_key": group_key,
                "set_as_group_summary": set_as_group_summary,
                "group_alert_behavior": group_alert_behavior,
                "color": "#4a9eff",
            }
            if effective_style is not None:
                kwargs["style"] = effective_style
            if visibility:
                kwargs["visibility"] = visibility
            if category:
                kwargs["category"] = category
            if match_date_time_components:
                kwargs["match_date_time_components"] = match_date_time_components
            if actions:
                kwargs["actions"] = actions
            result = await self._flet_notifications.schedule_notification(**kwargs)
            success = str(result).lower() == "ok"
            logger.warning(f"[NOTIF] schedule_notification: id={notification_id}, at={scheduled_time}, ok={success}")
            return success
        except NotificationError as e:
            logger.error(f"[NOTIF] schedule_notification failed: {e}")
            return False

    async def _cancel_extension_notification(self, notification_id: int) -> None:
        if self._flet_notifications is None:
            return
        try:
            await self._flet_notifications.cancel(notification_id)
        except NotificationError as e:
            logger.error(f"Failed to cancel notification {notification_id}: {e}")

    async def _deliver_plyer_notification(self, title: str, body: str) -> bool:
        if not PLYER_AVAILABLE:
            return False
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: plyer_notification.notify(
                    title=title,
                    message=body,
                    app_name="Trebnic",
                    timeout=10,
                )
            )
            return True
        except (OSError, RuntimeError) as e:
            logger.error(f"Error showing plyer notification: {e}")
            return False

    async def handle_task_notification_action(self, action_id: str, task_id: Optional[int]) -> str:
        """Apply a task notification action after Android opens/resumes Trebnic."""
        if action_id not in {"task_done", "task_postpone_1d"}:
            return "unsupported"
        if task_id is None:
            return "missing"
        if self._is_app_locked():
            return "locked"

        try:
            row = await db.load_task_by_id(int(task_id))
        except (DatabaseError, TypeError, ValueError):
            return "missing"

        if row is None:
            await self._cancel_all_task_nudge_alarms()
            return "missing"
        if row.get("is_done"):
            await self._cancel_all_task_nudge_alarms()
            return "noop"

        task_service = registry.get(Services.TASK)
        if task_service is None:
            return "missing"

        task = Task.from_dict(row)

        if action_id == "task_done":
            next_task = await task_service.complete_task(task)
            await task_service.refresh_state_tasks()
            event_bus.emit(AppEvent.TASK_COMPLETED, task)
            if next_task:
                event_bus.emit(AppEvent.TASK_CREATED, next_task)
            result = "done"
        else:
            await task_service.postpone_task(task)
            await task_service.refresh_state_tasks()
            event_bus.emit(AppEvent.TASK_UPDATED, task)
            event_bus.emit(AppEvent.TASK_POSTPONED, task)
            result = "postponed"

        event_bus.emit(AppEvent.REFRESH_UI)
        await self._cancel_all_task_nudge_alarms()
        if self._running:
            await self._schedule_all_digests()
        return result

    def _on_notification_tapped(self, e: Any) -> None:
        try:
            data_str = e.data if hasattr(e, "data") else ""
            outer = json.loads(data_str) if data_str else {}
            payload_str = outer.get("payload", "")
            payload = json.loads(payload_str) if payload_str else {}
            task_id = payload.get("task_id")
            action_id = outer.get("action_id")

            event_bus.emit(AppEvent.NOTIFICATION_TAPPED, {
                "task_id": task_id,
                "payload": payload,
                "action_id": action_id,
            })
        except (OSError, RuntimeError, ValueError) as ex:
            logger.error(f"Error handling notification tap: {ex}")

    # ── Cleanup ───────────────────────────────────────────────────────

    async def cleanup(self) -> None:
        logger.info("Cleaning up notification service")
        self.stop_scheduler()
        self._flet_notifications = None

    # ── Utility ───────────────────────────────────────────────────────

    def _is_notifications_enabled(self) -> bool:
        state = self._get_state() if self._get_state else None
        return state is not None and state.notifications_enabled

    def _is_in_quiet_hours(self) -> bool:
        state = self._get_state() if self._get_state else None
        if state is None:
            return False
        quiet_start = state.quiet_hours_start
        quiet_end = state.quiet_hours_end
        if quiet_start is None or quiet_end is None:
            return False
        now = datetime.now().time()
        if quiet_start > quiet_end:
            return now >= quiet_start or now <= quiet_end
        return quiet_start <= now <= quiet_end

    @property
    def backend(self) -> NotificationBackend:
        return self._backend

    @property
    def is_available(self) -> bool:
        return self._backend != NotificationBackend.NONE

    @property
    def is_running(self) -> bool:
        return self._running

    async def test_notification(self, title: str, body: str) -> bool:
        logger.warning(f"[NOTIF] test_notification: backend={self._backend.value}")
        if self._backend == NotificationBackend.FLET_EXTENSION:
            perm = await self.request_permission()
            logger.warning(f"[NOTIF] test_notification: permission result={perm}")
            if perm == PermissionResult.DENIED:
                return False

        result = False
        if self._backend == NotificationBackend.PLYER:
            result = await self._deliver_plyer_notification(title, body)
        elif self._backend == NotificationBackend.FLET_EXTENSION:
            result = await self._deliver_extension_notification(title, body, None)
        logger.warning(f"[NOTIF] test_notification: delivery result={result}")
        return result

    @classmethod
    def reset_instance(cls) -> None:
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.stop_scheduler()
                cls._instance._initialized = False
                cls._instance = None


notification_service = NotificationService()
