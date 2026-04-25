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
    NotificationType,
    PermissionResult,
)
from database import db, DatabaseError
from events import event_bus, AppEvent, Subscription
from i18n import t
from models.entities import Task
from registry import registry, Services
from formatters import TimeFormatter

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
        """Subscribe to TIMER_STOPPED and to task-mutation events that may change
        the digest contents (so we can rebuild and reschedule on Android, where
        the alarm body is fixed at schedule time)."""
        self._subscriptions.append(
            event_bus.subscribe(AppEvent.TIMER_STOPPED, self._on_timer_event)
        )
        for evt in (
            AppEvent.TASK_CREATED, AppEvent.TASK_UPDATED, AppEvent.TASK_COMPLETED,
            AppEvent.TASK_UNCOMPLETED, AppEvent.TASK_DELETED, AppEvent.TASK_POSTPONED,
        ):
            self._subscriptions.append(event_bus.subscribe(evt, self._on_task_mutation))

    def _unsubscribe_from_events(self) -> None:
        for sub in self._subscriptions:
            sub.unsubscribe()
        self._subscriptions.clear()

    def _on_timer_event(self, data: Any) -> None:
        """Handle timer stop — schedule_timer_complete_notification is called by timer_controller."""
        pass  # Timer complete is handled directly by timer_controller calling the method

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

    # ── Digest builders ───────────────────────────────────────────────

    async def _build_morning_digest(self) -> Optional[tuple]:
        """Build morning digest: tasks due today. Returns (title, body, style)."""
        state = self._get_state() if self._get_state else None
        if state is None:
            return None

        today = date.today()
        due_tasks = [task for task in state.tasks if task.due_date == today]
        if not due_tasks:
            return None

        title = "Trebnic"
        body = t("tasks_due_today").replace("{count}", str(len(due_tasks)))
        style = self._build_inbox_style(due_tasks)
        return title, body, style

    async def _build_evening_preview(self) -> Optional[tuple]:
        """Build evening preview: tasks due tomorrow. Returns (title, body, style)."""
        state = self._get_state() if self._get_state else None
        if state is None:
            return None

        tomorrow = date.today() + timedelta(days=1)
        due_tasks = [task for task in state.tasks if task.due_date == tomorrow]
        if not due_tasks:
            return None

        title = "Trebnic"
        body = t("tasks_due_tomorrow").replace("{count}", str(len(due_tasks)))
        style = self._build_inbox_style(due_tasks)
        return title, body, style

    async def _build_overdue_nudge(self) -> Optional[tuple]:
        """Build overdue nudge: overdue tasks. Returns (title, body, style)."""
        state = self._get_state() if self._get_state else None
        if state is None:
            return None

        today = date.today()
        overdue_tasks = [task for task in state.tasks if task.due_date and task.due_date < today]
        if not overdue_tasks:
            return None

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

    # ── Digest scheduling (Android + reschedule after settings change) ──

    async def _schedule_all_digests(self) -> None:
        """Schedule all enabled digest alarms. Called on startup and after settings save."""
        if not self._is_notifications_enabled():
            return

        state = self._get_state() if self._get_state else None
        if state is None:
            return

        if self._backend == NotificationBackend.FLET_EXTENSION:
            await self._schedule_android_digests(state)
        # Desktop uses the polling loop, no explicit scheduling needed

    async def _schedule_android_digests(self, state: Any) -> None:
        """Schedule daily AlarmManager alarms for each enabled digest.

        The Flet extension exposes no on-fire callback, so the body is whatever
        we set at schedule time. We rebuild from the current task snapshot here
        and reschedule on every meaningful event (settings change, app resume,
        task mutation) so the body stays as fresh as possible.
        """
        # Cancel existing digest alarms first
        for nid in (DIGEST_NOTIFICATION_ID, PREVIEW_NOTIFICATION_ID, OVERDUE_NOTIFICATION_ID):
            await self._cancel_extension_notification(nid)

        digest_actions = [{"id": "open_tasks", "title": t("notif_action_open")}]
        # Skip the daily nudge entirely if the user has no pending tasks at all —
        # otherwise schedule with a neutral fallback so daily reminders keep firing
        # even when the app stays closed for days.
        has_pending = bool(state.tasks)

        async def schedule_digest(nid: int, enabled: bool, target_time: time, builder: Callable) -> None:
            if not enabled:
                return
            if not has_pending:
                return
            built = await builder()
            if built is not None:
                title, body, _style = built
            else:
                title, body = "Trebnic", t("digest_check_app")
            trigger = self._next_trigger_time(target_time)
            await self._schedule_extension_notification(
                nid, title, body, trigger, None,
                match_date_time_components="time",
                actions=digest_actions,
            )

        await schedule_digest(
            DIGEST_NOTIFICATION_ID, state.daily_digest_enabled,
            state.daily_digest_time, self._build_morning_digest,
        )
        await schedule_digest(
            PREVIEW_NOTIFICATION_ID, state.evening_preview_enabled,
            state.evening_preview_time, self._build_evening_preview,
        )
        await schedule_digest(
            OVERDUE_NOTIFICATION_ID, state.overdue_nudge_enabled,
            state.overdue_nudge_time, self._build_overdue_nudge,
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

    # ── Timer complete notification ───────────────────────────────────

    async def schedule_timer_complete_notification(
        self, task: Task, elapsed_seconds: int
    ) -> Optional[int]:
        if not self._is_notifications_enabled():
            return None

        state = self._get_state() if self._get_state else None
        if state is None or not state.notify_timer_complete:
            return None

        trigger_time = datetime.now().isoformat()
        time_str = TimeFormatter.seconds_to_display(elapsed_seconds)
        body = t("tracked_time_on_task").replace("{time}", time_str).replace("{task}", task.title)

        notification = {
            "ntype": NotificationType.TIMER_COMPLETE.value,
            "task_id": task.id,
            "trigger_time": trigger_time,
            "payload": json.dumps({
                "title": t("timer_complete"),
                "body": body,
                "task_id": task.id,
                "elapsed_seconds": elapsed_seconds,
            }),
            "delivered": 0,
            "canceled": 0,
        }

        notification_id = await db.save_notification(notification)
        return notification_id

    async def show_immediate(
        self,
        title: str,
        body: str,
        task_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
        *,
        actions: Optional[List[Dict[str, str]]] = None,
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
        actions: Optional[List[Dict[str, str]]] = None,
        style: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Deliver a notification immediately, handling encryption state."""
        if self._is_app_locked():
            title = t("task_reminder")
            body = t("unlock_to_see_details")

        if self._backend == NotificationBackend.PLYER:
            await self._deliver_plyer_notification(title, body)
        elif self._backend == NotificationBackend.FLET_EXTENSION:
            await self._deliver_extension_notification(title, body, task_id, actions=actions, style=style, payload=payload)

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
        actions: Optional[List[Dict[str, str]]] = None,
        style: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
        channel_id: str = "trebnic_reminders",
        channel_name: str = "Task reminders",
        channel_description: str = "Task reminders from Trebnic",
        importance: str = "high",
        notification_id: Optional[int] = None,
    ) -> bool:
        if self._flet_notifications is None:
            return False
        try:
            nid = notification_id if notification_id else (task_id if task_id else abs(hash(title)) % 100000)
            base_payload = {"task_id": task_id}
            if payload:
                base_payload.update(payload)
            payload_str = json.dumps(base_payload)
            effective_style = style if style is not None else BigTextStyle(big_text=body)
            kwargs: Dict[str, Any] = {
                "notification_id": nid,
                "title": title,
                "body": body,
                "payload": payload_str,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "channel_description": channel_description,
                "importance": importance,
                "group_key": "trebnic_tasks",
                "color": "#4a9eff",
                "style": effective_style,
            }
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
        actions: Optional[List[Dict[str, str]]] = None,
    ) -> bool:
        if self._flet_notifications is None:
            return False
        try:
            payload_str = json.dumps({"task_id": task_id})
            kwargs: Dict[str, Any] = {
                "notification_id": notification_id,
                "title": title,
                "body": body,
                "scheduled_time": scheduled_time,
                "payload": payload_str,
                "channel_id": "trebnic_reminders",
                "channel_name": "Task reminders",
                "channel_description": "Task reminders from Trebnic",
                "schedule_mode": "inexact_allow_while_idle",
                "group_key": "trebnic_tasks",
                "color": "#4a9eff",
                "style": BigTextStyle(big_text=body),
            }
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

        if self._backend != NotificationBackend.FLET_EXTENSION:
            try:
                await db.cancel_all_pending_notifications()
            except DatabaseError as e:
                logger.error(f"Error canceling pending notifications: {e}")

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
