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

    async def get_setting(self, key: str, default=None):
        """Get a setting value from database."""
        return await db.get_setting(key, default)

    async def set_setting(self, key: str, value) -> None:
        """Set a setting value in database."""
        await db.set_setting(key, value)
