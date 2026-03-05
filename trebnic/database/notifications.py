import sqlite3
import logging
from typing import Any, Dict, List

from database.helpers import DatabaseError

logger = logging.getLogger(__name__)


class NotificationsMixin:
    """Scheduled notification operations mixin."""

    async def save_notification(self, notification: Dict[str, Any]) -> int:
        """Save a scheduled notification to the database."""
        try:
            async with self._get_connection() as conn:
                if notification.get("id") is None:
                    cursor = await conn.execute(
                        "INSERT INTO scheduled_notifications "
                        "(ntype, task_id, trigger_time, payload, delivered, canceled) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            notification["ntype"],
                            notification.get("task_id"),
                            notification["trigger_time"],
                            notification.get("payload"),
                            notification.get("delivered", 0),
                            notification.get("canceled", 0),
                        )
                    )
                    await conn.commit()
                    return cursor.lastrowid
                await conn.execute(
                    "UPDATE scheduled_notifications SET ntype=?, task_id=?, trigger_time=?, "
                    "payload=?, delivered=?, canceled=? WHERE id=?",
                    (
                        notification["ntype"],
                        notification.get("task_id"),
                        notification["trigger_time"],
                        notification.get("payload"),
                        notification.get("delivered", 0),
                        notification.get("canceled", 0),
                        notification["id"],
                    )
                )
                await conn.commit()
                return notification["id"]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error saving notification: {e}")
            raise DatabaseError(f"Failed to save notification: {e}") from e

    async def load_pending_notifications(self, trigger_before: str) -> List[Dict[str, Any]]:
        """Load pending notifications that should fire before the given time."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM scheduled_notifications "
                    "WHERE trigger_time <= ? AND delivered = 0 AND canceled = 0 "
                    "ORDER BY trigger_time ASC",
                    (trigger_before,)
                ) as cursor:
                    return [dict(r) async for r in cursor]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading pending notifications: {e}")
            raise DatabaseError(f"Failed to load pending notifications: {e}") from e

    async def mark_notification_delivered(self, notification_id: int) -> None:
        """Mark a notification as delivered."""
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "UPDATE scheduled_notifications SET delivered = 1 WHERE id = ?",
                    (notification_id,)
                )
                await conn.commit()
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error marking notification delivered: {e}")
            raise DatabaseError(f"Failed to mark notification delivered: {e}") from e

    async def cancel_notifications_for_task(self, task_id: int) -> int:
        """Cancel all pending notifications for a task.

        Returns:
            Number of notifications canceled
        """
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "UPDATE scheduled_notifications SET canceled = 1 "
                    "WHERE task_id = ? AND delivered = 0 AND canceled = 0",
                    (task_id,)
                )
                await conn.commit()
                return cursor.rowcount
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error canceling notifications for task {task_id}: {e}")
            raise DatabaseError(f"Failed to cancel notifications: {e}") from e

    async def delete_notifications_for_task(self, task_id: int) -> int:
        """Delete all notifications for a task (unfired only).

        Returns:
            Number of notifications deleted
        """
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "DELETE FROM scheduled_notifications "
                    "WHERE task_id = ? AND delivered = 0",
                    (task_id,)
                )
                await conn.commit()
                return cursor.rowcount
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error deleting notifications for task {task_id}: {e}")
            raise DatabaseError(f"Failed to delete notifications: {e}") from e

    async def load_notifications_for_task(self, task_id: int) -> List[Dict[str, Any]]:
        """Load all notifications for a specific task."""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(
                    "SELECT * FROM scheduled_notifications WHERE task_id = ? "
                    "ORDER BY trigger_time ASC",
                    (task_id,)
                ) as cursor:
                    return [dict(r) async for r in cursor]
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error loading notifications for task {task_id}: {e}")
            raise DatabaseError(f"Failed to load notifications: {e}") from e

    async def cancel_all_pending_notifications(self) -> int:
        """Cancel all pending notifications (for cleanup on app close).

        Returns:
            Number of notifications canceled
        """
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "UPDATE scheduled_notifications SET canceled = 1 "
                    "WHERE delivered = 0 AND canceled = 0"
                )
                await conn.commit()
                return cursor.rowcount
        except (sqlite3.Error, ValueError, KeyError, TypeError) as e:
            logger.error(f"Error canceling all pending notifications: {e}")
            raise DatabaseError(f"Failed to cancel notifications: {e}") from e
