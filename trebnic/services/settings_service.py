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
        await db.set_setting("remind_1h_before", self.state.remind_1h_before)
        await db.set_setting("remind_6h_before", self.state.remind_6h_before)
        await db.set_setting("remind_12h_before", self.state.remind_12h_before)
        await db.set_setting("remind_24h_before", self.state.remind_24h_before)
        await db.set_setting("reminder_minutes_before", self.state.reminder_minutes_before)

    async def get_setting(self, key: str, default=None):
        """Get a setting value from database."""
        return await db.get_setting(key, default)

    async def set_setting(self, key: str, value) -> None:
        """Set a setting value in database."""
        await db.set_setting(key, value)
