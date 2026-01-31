"""
Notification service for Trebnic.

This module provides cross-platform notification support using:
- Flet built-in notifications (primary): page.send_notification() available in Flet 0.21+
- plyer (fallback): Cross-platform notifications for desktop
- Android native (via pyjnius): Android-specific notifications (legacy)

The service schedules notifications based on task due dates and timer events,
storing them in the database for crash recovery and rescheduling.

Architecture:
- NotificationService is a singleton managing the scheduler loop
- Notifications are stored in scheduled_notifications table
- Scheduler loop runs every 60 seconds checking for pending notifications
- Task lifecycle events trigger notification rescheduling
"""
import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from config import NotificationType, PermissionResult
from database import db
from events import event_bus, AppEvent, Subscription
from i18n import t
from models.entities import Task
from registry import registry, Services
from ui.formatters.time_formatter import TimeFormatter

logger = logging.getLogger(__name__)

# Android 13 (API 33) requires POST_NOTIFICATIONS permission
ANDROID_13_API_LEVEL = 33

SCHEDULER_INTERVAL_SECONDS = 60


class NotificationBackend(Enum):
    """Available notification backends."""
    PLYER = "plyer"
    ANDROID_NATIVE = "android_native"
    NONE = "none"


# Backend availability detection
PLYER_AVAILABLE = False
ANDROID_NATIVE_AVAILABLE = False

try:
    from plyer import notification as plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    pass


def _detect_android() -> bool:
    """Detect if running on Android."""
    import os
    if os.path.exists("/system/build.prop"):
        return True
    if os.environ.get("ANDROID_ROOT"):
        return True
    try:
        import android
        return True
    except ImportError:
        pass
    return False


_is_android = _detect_android()

if _is_android:
    try:
        from jnius import autoclass
        ANDROID_NATIVE_AVAILABLE = True
    except ImportError:
        pass


def _detect_notification_backend() -> NotificationBackend:
    """Detect the best available notification backend.

    Priority:
    1. plyer (works on desktop and Android)
    2. Android native (pyjnius) for Android
    3. None if nothing available
    """
    if PLYER_AVAILABLE:
        return NotificationBackend.PLYER

    if _is_android and ANDROID_NATIVE_AVAILABLE:
        return NotificationBackend.ANDROID_NATIVE

    return NotificationBackend.NONE


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
        logger.info(f"Notification backend: {self._backend.value}")

        # Dependencies (injected via inject_dependencies)
        self._page = None
        self._schedule_async: Optional[Callable[..., asyncio.Task]] = None
        self._get_state: Optional[Callable[[], Any]] = None

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

    async def request_permission(self) -> PermissionResult:
        """Request notification permission.

        On Android 13+, runtime permission is required. On desktop, permission
        is assumed granted (no runtime permission needed).

        Returns:
            PermissionResult indicating whether permission was granted/denied.
        """
        # Plyer handles permissions - just return granted
        if self._backend == NotificationBackend.PLYER:
            logger.info("Plyer backend - assuming permission granted")
            return PermissionResult.GRANTED

        # Desktop platforms don't need runtime permission
        if not _is_android:
            logger.info("Desktop platform - notification permission not required")
            return PermissionResult.NOT_REQUIRED

        # Android native backend (legacy) - use jnius for permission
        if ANDROID_NATIVE_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self._request_android_permission
                )
                return result
            except Exception as e:
                logger.error(f"Error requesting Android permission: {e}")
                return PermissionResult.DENIED

        return PermissionResult.NOT_REQUIRED

    def _request_android_permission(self) -> PermissionResult:
        """Request POST_NOTIFICATIONS permission on Android 13+ (runs in executor)."""
        try:
            from jnius import autoclass

            Build = autoclass("android.os.Build")
            api_level = Build.VERSION.SDK_INT

            # Android < 13 doesn't require runtime permission
            if api_level < ANDROID_13_API_LEVEL:
                return PermissionResult.NOT_REQUIRED

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity

            # Check if permission is already granted
            Context = autoclass("android.content.Context")
            PackageManager = autoclass("android.content.pm.PackageManager")
            permission = "android.permission.POST_NOTIFICATIONS"

            if activity.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED:
                return PermissionResult.GRANTED

            # Request permission
            ActivityCompat = autoclass("androidx.core.app.ActivityCompat")
            ActivityCompat.requestPermissions(activity, [permission], 1001)

            # Note: This is a simplified synchronous check. In a full implementation,
            # you'd use onRequestPermissionsResult callback. For now, we assume the
            # user will grant/deny and settings will reflect the actual state.
            return PermissionResult.GRANTED

        except Exception as e:
            logger.error(f"Error in Android permission request: {e}")
            return PermissionResult.DENIED

    def start_scheduler(self) -> None:
        """Start the notification scheduler loop.

        Spawns an async loop that checks for pending notifications every 60 seconds.
        """
        if self._running:
            return

        if self._schedule_async is None:
            raise RuntimeError("NotificationService dependencies not injected")

        self._running = True
        self._stop_event.clear()
        self._subscribe_to_events()
        self._schedule_async(self._scheduler_loop())
        logger.info("Notification scheduler started")

    def stop_scheduler(self) -> None:
        """Stop the notification scheduler loop."""
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
            self._schedule_async(self._reschedule_for_task(task_id))

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop - checks for pending notifications."""
        logger.info("Notification scheduler loop started")

        try:
            while self._running and not self._stop_event.is_set():
                await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)

                if self._stop_event.is_set() or not self._running:
                    break

                await self._process_pending_notifications()

        except asyncio.CancelledError:
            logger.info("Notification scheduler loop cancelled")
        except Exception as e:
            logger.error(f"Error in notification scheduler loop: {e}")
            self._running = False

    async def _process_pending_notifications(self) -> None:
        """Process all pending notifications that are due."""
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

        except Exception as e:
            logger.error(f"Error processing pending notifications: {e}")

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
        elif self._backend == NotificationBackend.ANDROID_NATIVE:
            await self._deliver_android_notification(title, body, task_id)

        event_bus.emit(AppEvent.NOTIFICATION_FIRED, {
            "notification_id": notification.get("id"),
            "ntype": ntype,
            "task_id": task_id,
        })

    async def _deliver_android_notification(
        self, title: str, body: str, task_id: Optional[int]
    ) -> None:
        """Deliver notification via Android native APIs."""
        if not ANDROID_NATIVE_AVAILABLE:
            return

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._show_android_notification(title, body, task_id)
            )
        except Exception as e:
            logger.error(f"Error showing Android notification: {e}")

    def _show_android_notification(
        self, title: str, body: str, task_id: Optional[int]
    ) -> None:
        """Show Android notification (runs in executor)."""
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            NotificationBuilder = autoclass("android.app.Notification$Builder")
            NotificationManager = autoclass("android.app.NotificationManager")

            activity = PythonActivity.mActivity
            context = activity.getApplicationContext()

            notification_service = context.getSystemService(Context.NOTIFICATION_SERVICE)

            builder = NotificationBuilder(context)
            builder.setContentTitle(title)
            builder.setContentText(body)
            builder.setSmallIcon(context.getApplicationInfo().icon)
            builder.setAutoCancel(True)

            notification_id = task_id or hash(title) % 100000
            notification_service.notify(notification_id, builder.build())

        except Exception as e:
            logger.error(f"Error in Android notification: {e}")

    async def _deliver_plyer_notification(self, title: str, body: str) -> None:
        """Deliver notification via plyer (desktop fallback)."""
        if not PLYER_AVAILABLE:
            return

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: plyer_notification.notify(
                    title=title,
                    message=body,
                    app_name="Trebnic",
                    timeout=10,
                )
            )
        except Exception as e:
            logger.error(f"Error showing plyer notification: {e}")

    def _on_notification_tapped(self, e: Any) -> None:
        """Handle notification tap (Flet backend only)."""
        try:
            payload = json.loads(e.payload) if e.payload else {}
            task_id = payload.get("task_id")

            event_bus.emit(AppEvent.NOTIFICATION_TAPPED, {
                "task_id": task_id,
                "payload": payload,
            })

        except Exception as ex:
            logger.error(f"Error handling notification tap: {ex}")

    async def _reschedule_for_task(self, task_id: int) -> None:
        """Reschedule notifications for a task.

        Deletes existing unfired notifications and creates new ones based on
        the task's current due_date and reminder settings.
        """
        if not self._is_notifications_enabled():
            return

        state = self._get_state() if self._get_state else None
        if state is None:
            return

        # Delete existing unfired notifications for this task
        await db.delete_notifications_for_task(task_id)

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

        for reminder_minutes in reminder_times:
            trigger_time = due_datetime - timedelta(minutes=reminder_minutes)

            # Only schedule if trigger time is in the future
            if trigger_time <= now:
                continue

            notification = {
                "ntype": NotificationType.DUE_REMINDER.value,
                "task_id": task_id,
                "trigger_time": trigger_time.isoformat(),
                "payload": json.dumps({
                    "title": "Task reminder",
                    "body": task.title,
                    "task_id": task_id,
                }),
                "delivered": 0,
                "canceled": 0,
            }

            notification_id = await db.save_notification(notification)
            event_bus.emit(AppEvent.NOTIFICATION_SCHEDULED, {
                "notification_id": notification_id,
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

        minutes = elapsed_seconds // 60
        body = f"Tracked {minutes} minutes on {task.title}"

        notification = {
            "ntype": NotificationType.TIMER_COMPLETE.value,
            "task_id": task.id,
            "trigger_time": trigger_time,
            "payload": json.dumps({
                "title": "Timer complete",
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
        elif self._backend == NotificationBackend.ANDROID_NATIVE:
            await self._deliver_android_notification(title, body, task_id)

        event_bus.emit(AppEvent.NOTIFICATION_FIRED, {
            "task_id": task_id,
            "ntype": "immediate",
            "payload": payload,
        })

    async def cleanup(self) -> None:
        """Clean up notification service resources.

        Called when app is closing. Cancels scheduler, marks pending
        notifications as canceled, and clears system notifications.
        """
        logger.info("Cleaning up notification service")

        # Stop the scheduler
        self.stop_scheduler()

        # Mark all pending notifications as canceled in database
        try:
            await db.cancel_all_pending_notifications()
        except Exception as e:
            logger.error(f"Error canceling pending notifications: {e}")

        # Clear system notifications (platform-specific)
        if self._backend == NotificationBackend.ANDROID_NATIVE and ANDROID_NATIVE_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._clear_android_notifications)
            except Exception as e:
                logger.error(f"Error clearing Android notifications: {e}")

    def _clear_android_notifications(self) -> None:
        """Clear all Android notifications (runs in executor)."""
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Context = autoclass("android.content.Context")
            NotificationManager = autoclass("android.app.NotificationManager")

            activity = PythonActivity.mActivity
            context = activity.getApplicationContext()
            notification_manager = context.getSystemService(Context.NOTIFICATION_SERVICE)
            notification_manager.cancelAll()
        except Exception as e:
            logger.error(f"Error clearing Android notifications: {e}")

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
