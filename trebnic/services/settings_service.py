from database import db
from models.entities import AppState


class SettingsService:
    """Service for application settings.

    Handles settings persistence with database.
    All data operations are async.
    """

    def __init__(self, state: AppState) -> None:
        self.state = state

    async def save_settings(self) -> None:
        """Save application settings to database."""
        await db.set_setting("default_estimated_minutes", self.state.default_estimated_minutes)
        await db.set_setting("email_weekly_stats", self.state.email_weekly_stats)
        await db.set_setting("language", self.state.language)
        # Notification settings
        await db.set_setting("notifications_enabled", self.state.notifications_enabled)
        await db.set_setting("notify_timer_complete", self.state.notify_timer_complete)
        await db.set_setting("daily_digest_enabled", self.state.daily_digest_enabled)
        await db.set_setting("daily_digest_time", self.state.daily_digest_time.strftime("%H:%M"))
        await db.set_setting("evening_preview_enabled", self.state.evening_preview_enabled)
        await db.set_setting("evening_preview_time", self.state.evening_preview_time.strftime("%H:%M"))
        await db.set_setting("overdue_nudge_enabled", self.state.overdue_nudge_enabled)
        await db.set_setting("overdue_nudge_time", self.state.overdue_nudge_time.strftime("%H:%M"))
        await db.set_setting("task_nudges_enabled", self.state.task_nudges_enabled)
        await db.set_setting("task_nudge_time", self.state.task_nudge_time.strftime("%H:%M"))

    async def get_setting(self, key: str, default=None):
        """Get a setting value from database."""
        return await db.get_setting(key, default)

    async def set_setting(self, key: str, value) -> None:
        """Set a setting value in database."""
        await db.set_setting(key, value)
