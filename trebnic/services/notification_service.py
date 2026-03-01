"""
Notification service for Trebnic.

This module provides cross-platform notification support using:
- Flet local notifications extension (Android): native notifications via flutter_local_notifications
- plyer (desktop): cross-platform notifications for Windows/Linux/Mac

On Android (0.2.0+), notifications are scheduled via AlarmManager using
schedule_notification(). They fire at exact future times even if the app
is killed or the device restarts. No polling loop is needed.

On desktop, a scheduler loop polls the database every 60 seconds.

Architecture:
- NotificationService is a singleton managing notification scheduling
- On Android: schedule_notification() registers alarms with the OS
- On desktop: notifications are stored in scheduled_notifications table
  and a scheduler loop checks for pending ones every 60 seconds
- Task lifecycle events trigger notification rescheduling on both platforms
"""
import asyncio
import json
import logging
import threading
from datetime import date, datetime, timedelta, time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from config import NotificationAction, NotificationType, PermissionResult
from database import db, DatabaseError
from events import event_bus, AppEvent, Subscription
from i18n import t
from models.entities import Task
from registry import registry, Services
from formatters import TimeFormatter

logger = logging.getLogger(__name__)

# Android 13 (API 33) requires POST_NOTIFICATIONS permission
ANDROID_13_API_LEVEL = 33

SCHEDULER_INTERVAL_SECONDS = 60

# Each task gets up to MAX_REMINDER_SLOTS notification IDs.
# Notification ID = task_id * MAX_REMINDER_SLOTS + slot_index.
MAX_REMINDER_SLOTS = 10


class NotificationBackend(Enum):
    """Available notification backends."""
    FLET_EXTENSION = "flet_extension"
    PLYER = "plyer"
    NONE = "none"


# Backend availability detection — try extension first (Android), then plyer (desktop)
PLYER_AVAILABLE = False
FLET_EXTENSION_AVAILABLE = False

try:
    from flet_android_notifications import FletAndroidNotifications, NotificationError
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
    """Detect the best available notification backend.

    Priority:
    1. Flet extension (Android — pip-installed via dev_packages)
    2. plyer for desktop (Windows/Linux/Mac)
    3. None if nothing available
    """
    if FLET_EXTENSION_AVAILABLE:
        return NotificationBackend.FLET_EXTENSION

    if PLYER_AVAILABLE:
        return NotificationBackend.PLYER

    return NotificationBackend.NONE


def _notification_id_for_task(task_id: int, slot: int) -> int:
    """Compute a stable notification ID for a task + reminder slot.

    Each task gets MAX_REMINDER_SLOTS consecutive IDs so they can be
    individually canceled without tracking state.
    """
    return task_id * MAX_REMINDER_SLOTS + slot


class NotificationService:
    """Service for managing scheduled notifications.

    Singleton pattern following TimerService/CryptoService conventions.
    Manages notification scheduling, delivery, and event subscriptions.
    """
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

        # Backend detection
        self._backend = _detect_notification_backend()
        logger.warning(f"[NOTIF] Backend detected: {self._backend.value}")

        # Dependencies (injected via inject_dependencies)
        self._page = None
        self._schedule_async: Optional[Callable[..., asyncio.Task]] = None
        self._get_state: Optional[Callable[[], Any]] = None

        # Flet extension instance (Android only)
        self._flet_notifications = None

        # Async control
        self._running = False
        self._stop_event: asyncio.Event = asyncio.Event()

        # Event subscriptions
        self._subscriptions: List[Subscription] = []

        self._initialized = True

    def inject_dependencies(
        self,
        page: Any,
        async_scheduler: Callable[..., asyncio.Task],
        get_state: Callable[[], Any],
    ) -> None:
        """Inject dependencies after construction.

        Args:
            page: Flet page for notification tap handling
            async_scheduler: Function to schedule async work (page.run_task)
            get_state: Function returning AppState for settings access
        """
        self._page = page
        self._schedule_async = async_scheduler
        self._get_state = get_state

        # Instantiate Flet extension on Android.
        # Service auto-registers via Service.init() → context.page._services.register_service().
        # Do NOT add to page.overlay or page.services manually.
        if self._backend == NotificationBackend.FLET_EXTENSION and FLET_EXTENSION_AVAILABLE:
            self._flet_notifications = FletAndroidNotifications(on_notification_tap=self._on_notification_tapped)
            logger.warning(f"[NOTIF] FletAndroidNotifications created: {self._flet_notifications is not None}")

    async def request_permission(self) -> PermissionResult:
        """Request notification permission.

        On Android 13+, runtime permission is required via the extension.
        On desktop, permission is assumed granted (no runtime permission needed).

        Returns:
            PermissionResult indicating whether permission was granted/denied.
        """
        if self._backend == NotificationBackend.PLYER:
            logger.info("Plyer backend - assuming permission granted")
            return PermissionResult.GRANTED

        if self._backend == NotificationBackend.FLET_EXTENSION and self._flet_notifications is not None:
            try:
                result = await self._flet_notifications.request_permissions()
                logger.warning(f"[NOTIF] request_permissions raw result: {result!r} (type={type(result).__name__})")
                granted = str(result).lower() == "true"
                return PermissionResult.GRANTED if granted else PermissionResult.DENIED
            except NotificationError as e:
                logger.error(f"[NOTIF] Error requesting notification permission: {e}")
                return PermissionResult.DENIED

        return PermissionResult.NOT_REQUIRED

    async def request_exact_alarm_permission(self) -> PermissionResult:
        """Request SCHEDULE_EXACT_ALARM permission (Android 14+).

        Required before using exact schedule modes. Inexact modes (the default)
        do not need this permission. On desktop, always returns GRANTED.

        Returns:
            PermissionResult indicating whether exact alarm permission was granted.
        """
        if self._backend != NotificationBackend.FLET_EXTENSION:
            return PermissionResult.GRANTED

        if self._flet_notifications is None:
            return PermissionResult.NOT_REQUIRED

        try:
            result = await self._flet_notifications.request_exact_alarm_permission()
            granted = str(result).lower() == "true"
            logger.info(f"Exact alarm permission result: {granted}")
            return PermissionResult.GRANTED if granted else PermissionResult.DENIED
        except NotificationError as e:
            logger.error(f"Error requesting exact alarm permission: {e}")
            return PermissionResult.DENIED

    def start_scheduler(self) -> None:
        """Start the notification scheduler.

        On Android: subscribes to events and schedules all tasks via AlarmManager.
        On desktop: also starts a polling loop that checks the DB every 60 seconds.
        """
        if self._running:
            return

        if self._schedule_async is None:
            raise RuntimeError("NotificationService dependencies not injected")

        self._running = True
        self._stop_event.clear()
        self._subscribe_to_events()

        # Desktop needs a polling loop; Android uses AlarmManager (no polling)
        if self._backend != NotificationBackend.FLET_EXTENSION:
            self._schedule_async(self._scheduler_loop)

        # Reschedule all tasks on startup (both platforms)
        self._schedule_async(self._reschedule_all_tasks)
        logger.info("Notification scheduler started")

    def stop_scheduler(self) -> None:
        """Stop the notification scheduler."""
        self._running = False
        self._stop_event.set()
        self._unsubscribe_from_events()
        logger.info("Notification scheduler stopped")

    def _subscribe_to_events(self) -> None:
        """Subscribe to task lifecycle events for notification rescheduling."""
        events_to_subscribe = [
            AppEvent.TASK_CREATED,
            AppEvent.TASK_UPDATED,
            AppEvent.TASK_DELETED,
            AppEvent.TASK_COMPLETED,
            AppEvent.TASK_UNCOMPLETED,
            AppEvent.TASK_POSTPONED,
            AppEvent.TIMER_STOPPED,
        ]
        for event in events_to_subscribe:
            sub = event_bus.subscribe(event, self._on_task_event)
            self._subscriptions.append(sub)

    def _unsubscribe_from_events(self) -> None:
        """Unsubscribe from all events."""
        for sub in self._subscriptions:
            sub.unsubscribe()
        self._subscriptions.clear()

    def _on_task_event(self, data: Any) -> None:
        """Handle task lifecycle events.

        Reschedules notifications when tasks are created, updated, or deleted.
        """
        if self._schedule_async is None:
            return

        task_id = None
        if isinstance(data, Task):
            task_id = data.id
        elif isinstance(data, dict):
            task = data.get("task")
            if isinstance(task, Task):
                task_id = task.id
            else:
                task_id = data.get("task_id")
        elif isinstance(data, int):
            task_id = data

        if task_id is not None:
            # Flet 0.80 requires coroutine function, not coroutine object
            async def reschedule_wrapper() -> None:
                await self._reschedule_for_task(task_id)
            self._schedule_async(reschedule_wrapper)

    # ── Desktop-only polling loop ──────────────────────────────────────

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - checks for pending notifications (desktop only)."""
        logger.info("Notification scheduler loop started")

        try:
            while self._running and not self._stop_event.is_set():
                await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)

                if self._stop_event.is_set() or not self._running:
                    break

                await self._process_pending_notifications()
                await self._check_overdue_tasks()

        except asyncio.CancelledError:
            logger.info("Notification scheduler loop cancelled")
        except (DatabaseError, OSError, RuntimeError) as e:
            logger.error(f"Error in notification scheduler loop: {e}")
            self._running = False

    async def _process_pending_notifications(self) -> None:
        """Process all pending notifications that are due (desktop only)."""
        if not self._is_notifications_enabled():
            return

        now = datetime.now().isoformat()

        try:
            pending = await db.load_pending_notifications(now)

            for notification in pending:
                if self._is_in_quiet_hours():
                    continue

                await self._deliver_notification(notification)
                await db.mark_notification_delivered(notification["id"])

        except (DatabaseError, OSError) as e:
            logger.error(f"Error processing pending notifications: {e}")

    # ── Notification delivery ──────────────────────────────────────────

    def _is_app_locked(self) -> bool:
        """Check if the app is locked (encryption enabled but not unlocked)."""
        crypto = registry.get(Services.CRYPTO)
        if crypto is None:
            return False
        # If encryption is available and set up, but not unlocked
        if crypto.is_available:
            # Check if encryption is configured by looking for verification hash
            state = self._get_state() if self._get_state else None
            if state is not None:
                # If crypto service exists and is not unlocked, app is locked
                return not crypto.is_unlocked
        return False

    async def _deliver_notification(self, notification: Dict[str, Any]) -> None:
        """Deliver a single notification using the appropriate backend.

        Handles encryption state - if app is locked, shows generic message
        instead of potentially sensitive task details.
        """
        ntype = notification.get("ntype", "")
        payload = notification.get("payload")
        payload_dict = json.loads(payload) if payload else {}
        task_id = notification.get("task_id")

        # Handle encryption state - show generic message if locked
        if self._is_app_locked():
            title = t("task_reminder")
            body = t("unlock_to_see_details")
        else:
            title = payload_dict.get("title", "Trebnic")
            body = payload_dict.get("body", "")

        logger.info(f"Delivering notification: {ntype} - {title}")

        if self._backend == NotificationBackend.PLYER:
            await self._deliver_plyer_notification(title, body)
        elif self._backend == NotificationBackend.FLET_EXTENSION:
            await self._deliver_extension_notification(title, body, task_id)

        event_bus.emit(AppEvent.NOTIFICATION_FIRED, {
            "notification_id": notification.get("id"),
            "ntype": ntype,
            "task_id": task_id,
        })

    async def _deliver_extension_notification(
        self, title: str, body: str, task_id: Optional[int]
    ) -> bool:
        """Deliver notification via Flet local notifications extension (Android).

        Returns:
            True if notification was delivered successfully, False otherwise.
        """
        if self._flet_notifications is None:
            return False

        try:
            notification_id = task_id if task_id else abs(hash(title)) % 100000
            payload_str = json.dumps({"task_id": task_id})
            result = await self._flet_notifications.show_notification(
                notification_id=notification_id,
                title=title,
                body=body,
                payload=payload_str,
                channel_id="trebnic_reminders",
                channel_name="Task reminders",
                channel_description="Task reminders from Trebnic",
            )
            success = str(result).lower() == "ok"
            logger.warning(
                f"[NOTIF] show_notification raw result: {result!r} (type={type(result).__name__}), "
                f"id={notification_id}, success={success}"
            )
            return success
        except NotificationError as e:
            logger.error(f"[NOTIF] show_notification failed: {e}")
            return False

    def _build_due_reminder_actions(self) -> list:
        """Build action buttons for due reminder notifications (Android only)."""
        return [
            {"id": NotificationAction.COMPLETE, "title": t("notif_action_complete")},
            {"id": NotificationAction.POSTPONE, "title": t("notif_action_postpone")},
        ]

    async def _schedule_extension_notification(
        self,
        notification_id: int,
        title: str,
        body: str,
        scheduled_time: datetime,
        task_id: Optional[int],
        actions: Optional[list] = None,
    ) -> bool:
        """Schedule a future notification via AlarmManager (Android only).

        Uses inexact_allow_while_idle by default so SCHEDULE_EXACT_ALARM
        permission is not required. Fires even if app is killed or device restarts.

        Returns:
            True if scheduled successfully, False otherwise.
        """
        if self._flet_notifications is None:
            return False

        try:
            payload_str = json.dumps({"task_id": task_id})
            result = await self._flet_notifications.schedule_notification(
                notification_id=notification_id,
                title=title,
                body=body,
                scheduled_time=scheduled_time,
                payload=payload_str,
                channel_id="trebnic_reminders",
                channel_name="Task reminders",
                channel_description="Task reminders from Trebnic",
                schedule_mode="inexact_allow_while_idle",
                actions=actions or [],
            )
            success = str(result).lower() == "ok"
            logger.warning(
                f"[NOTIF] schedule_notification raw result: {result!r} (type={type(result).__name__}), "
                f"id={notification_id}, at={scheduled_time}, success={success}"
            )
            return success
        except NotificationError as e:
            logger.error(f"[NOTIF] schedule_notification failed: {e}")
            return False

    async def _cancel_extension_notification(self, notification_id: int) -> None:
        """Cancel a scheduled notification by ID (Android only)."""
        if self._flet_notifications is None:
            return
        try:
            await self._flet_notifications.cancel(notification_id)
        except NotificationError as e:
            logger.error(f"Failed to cancel notification {notification_id}: {e}")

    async def _deliver_plyer_notification(self, title: str, body: str) -> bool:
        """Deliver notification via plyer (desktop fallback).

        Returns:
            True if notification was delivered successfully, False otherwise.
        """
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
        """Handle notification tap from the Flet extension.

        The new extension sends e.data as JSON: {"payload": "...", "action_id": "..."}.
        The inner payload is itself a JSON string containing task_id.
        """
        try:
            data_str = e.data if hasattr(e, "data") else ""
            outer = json.loads(data_str) if data_str else {}

            # Extract and parse the inner payload
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

    # ── Scheduling logic ───────────────────────────────────────────────

    async def _reschedule_all_tasks(self) -> None:
        """Reschedule notifications for all tasks with due dates on startup."""
        if not self._is_notifications_enabled():
            return
        state = self._get_state() if self._get_state else None
        if state is None:
            return
        for task in state.tasks:
            if task.due_date and task.id:
                await self._reschedule_for_task(task.id)
        logger.info(f"Startup reschedule complete for {len(state.tasks)} tasks")

        await self._check_overdue_tasks()

    async def _check_overdue_tasks(self) -> None:
        """Check for overdue tasks and send a daily notification if any exist.

        Tracks last_overdue_notification_date in settings to avoid spamming.
        Called on startup and in the desktop scheduler loop.
        """
        if not self._is_notifications_enabled():
            return

        state = self._get_state() if self._get_state else None
        if state is None or not state.notify_overdue:
            return

        today_str = date.today().isoformat()
        last_notified = await db.get_setting("last_overdue_notification_date", "")
        if last_notified == today_str:
            return

        # Query overdue tasks: not done, due before today
        yesterday = date.today() - timedelta(days=1)
        try:
            overdue_dicts = await db.load_tasks_filtered(is_done=False, due_date_lte=yesterday)
        except DatabaseError as e:
            logger.error(f"Error checking overdue tasks: {e}")
            return

        count = len(overdue_dicts)
        if count == 0:
            return

        title = t("overdue_notification_title")
        if count == 1:
            body = t("overdue_notification_body_one")
        else:
            body = t("overdue_notification_body_many").replace("{count}", str(count))

        await self.show_immediate(title, body)
        await db.set_setting("last_overdue_notification_date", today_str)

    async def _cancel_all_for_task(self, task_id: int) -> None:
        """Cancel all notification slots for a task.

        On Android: cancels AlarmManager alarms via the extension.
        On both platforms: deletes unfired DB records.
        """
        if self._backend == NotificationBackend.FLET_EXTENSION and self._flet_notifications is not None:
            for slot in range(MAX_REMINDER_SLOTS):
                await self._cancel_extension_notification(_notification_id_for_task(task_id, slot))

        await db.delete_notifications_for_task(task_id)

    async def _reschedule_for_task(self, task_id: int) -> None:
        """Reschedule notifications for a task.

        Cancels existing notifications and creates new ones based on
        the task's current due_date and reminder settings.

        On Android: registers alarms via schedule_notification().
        On desktop: saves to DB for the polling loop to pick up.
        """
        if not self._is_notifications_enabled():
            return

        state = self._get_state() if self._get_state else None
        if state is None:
            return

        # Cancel existing notifications for this task (both native alarms and DB)
        await self._cancel_all_for_task(task_id)

        # Find the task in state
        task = state.get_task_by_id(task_id)
        if task is None or task.due_date is None:
            return

        # Build list of enabled reminder times in minutes
        reminder_times = []
        if state.remind_1h_before:
            reminder_times.append(60)  # 1 hour
        if state.remind_6h_before:
            reminder_times.append(360)  # 6 hours
        if state.remind_12h_before:
            reminder_times.append(720)  # 12 hours
        if state.remind_24h_before:
            reminder_times.append(1440)  # 24 hours
        # Custom reminder from slider
        if state.reminder_minutes_before > 0:
            reminder_times.append(state.reminder_minutes_before)

        if not reminder_times:
            return

        due_datetime = datetime.combine(task.due_date, time(9, 0))  # Default 9 AM
        now = datetime.now()

        for slot, reminder_minutes in enumerate(reminder_times):
            trigger_time = due_datetime - timedelta(minutes=reminder_minutes)

            # Only schedule if trigger time is in the future
            if trigger_time <= now:
                continue

            if reminder_minutes < 60:
                time_desc = f"{reminder_minutes}min"
            elif reminder_minutes < 1440:
                time_desc = f"{reminder_minutes // 60}h"
            else:
                time_desc = f"{reminder_minutes // 1440}d"

            title = t("task_reminder")
            body = t("task_due_in").replace("{time}", time_desc).replace("{task}", task.title)

            if self._backend == NotificationBackend.FLET_EXTENSION:
                # Android: schedule via AlarmManager — fires even if app is killed
                nid = _notification_id_for_task(task_id, slot)
                actions = self._build_due_reminder_actions()
                await self._schedule_extension_notification(nid, title, body, trigger_time, task_id, actions=actions)
            else:
                # Desktop: save to DB for the polling loop
                notification = {
                    "ntype": NotificationType.DUE_REMINDER.value,
                    "task_id": task_id,
                    "trigger_time": trigger_time.isoformat(),
                    "payload": json.dumps({
                        "title": title,
                        "body": body,
                        "task_id": task_id,
                    }),
                    "delivered": 0,
                    "canceled": 0,
                }
                await db.save_notification(notification)

            event_bus.emit(AppEvent.NOTIFICATION_SCHEDULED, {
                "notification_id": _notification_id_for_task(task_id, slot),
                "task_id": task_id,
                "ntype": NotificationType.DUE_REMINDER.value,
            })

    async def schedule_timer_complete_notification(
        self, task: Task, elapsed_seconds: int
    ) -> Optional[int]:
        """Schedule a timer completion notification.

        Called when a timer stops to notify the user.

        Returns:
            Notification ID if scheduled, None otherwise
        """
        if not self._is_notifications_enabled():
            return None

        state = self._get_state() if self._get_state else None
        if state is None or not state.notify_timer_complete:
            return None

        # Schedule immediate notification
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
    ) -> None:
        """Show a notification immediately without scheduling.

        Used for timer completion and other immediate notifications.
        Respects quiet hours setting.

        Args:
            title: Notification title
            body: Notification body text
            task_id: Optional task ID for tap handling
            payload: Optional additional payload data
        """
        if not self._is_notifications_enabled():
            return

        if self._is_in_quiet_hours():
            logger.info("Skipping immediate notification - in quiet hours")
            return

        # Handle encryption state
        if self._is_app_locked():
            title = t("task_reminder")
            body = t("unlock_to_see_details")

        if self._backend == NotificationBackend.PLYER:
            await self._deliver_plyer_notification(title, body)
        elif self._backend == NotificationBackend.FLET_EXTENSION:
            await self._deliver_extension_notification(title, body, task_id)

        event_bus.emit(AppEvent.NOTIFICATION_FIRED, {
            "task_id": task_id,
            "ntype": "immediate",
            "payload": payload,
        })

    async def cleanup(self) -> None:
        """Clean up notification service resources.

        Called when app is closing. On Android, AlarmManager alarms are intentionally
        preserved so scheduled due reminders fire even after the app is killed or
        the device restarts. On desktop, marks pending DB notifications as canceled.
        """
        logger.info("Cleaning up notification service")

        # Stop the scheduler
        self.stop_scheduler()

        # NOTE: Do NOT call cancel_all() on Android — AlarmManager alarms must persist
        # through app close so due reminders can fire while the app is not running.
        # _reschedule_all_tasks() on next startup will re-sync if needed.

        # Desktop only: mark pending DB notifications as canceled (no AlarmManager)
        if self._backend != NotificationBackend.FLET_EXTENSION:
            try:
                await db.cancel_all_pending_notifications()
            except DatabaseError as e:
                logger.error(f"Error canceling pending notifications: {e}")

        self._flet_notifications = None

    def _is_notifications_enabled(self) -> bool:
        """Check if notifications are enabled in settings."""
        state = self._get_state() if self._get_state else None
        return state is not None and state.notifications_enabled

    def _is_in_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours."""
        state = self._get_state() if self._get_state else None
        if state is None:
            return False

        quiet_start = state.quiet_hours_start
        quiet_end = state.quiet_hours_end

        if quiet_start is None or quiet_end is None:
            return False

        now = datetime.now().time()

        # Handle overnight quiet hours (e.g., 22:00 - 07:00)
        if quiet_start > quiet_end:
            return now >= quiet_start or now <= quiet_end
        else:
            return quiet_start <= now <= quiet_end

    @property
    def backend(self) -> NotificationBackend:
        """Get the detected notification backend."""
        return self._backend

    @property
    def is_available(self) -> bool:
        """Check if any notification backend is available."""
        return self._backend != NotificationBackend.NONE

    @property
    def is_running(self) -> bool:
        """Check if the scheduler is running."""
        return self._running

    async def test_notification(self, title: str, body: str) -> bool:
        """Send a test notification and return whether it was delivered.

        This method bypasses enabled checks and is meant for testing notification
        delivery in the UI. On Android 13+, requests POST_NOTIFICATIONS permission
        first — without it the OS silently drops notifications.

        Returns:
            True if notification was delivered successfully, False otherwise.
        """
        logger.warning(f"[NOTIF] test_notification: backend={self._backend.value}")

        # On Android 13+, POST_NOTIFICATIONS must be granted or notifications are silently dropped
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
        """Reset the singleton instance. Used for testing."""
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.stop_scheduler()
                cls._instance._initialized = False
                cls._instance = None


# Module-level singleton
notification_service = NotificationService()
