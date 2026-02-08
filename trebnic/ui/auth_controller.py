"""
Authentication controller for Trebnic.

Manages the authentication UI flow:
- Check auth state on startup
- Show unlock dialog if locked
- Show setup dialog for first-time encryption setup
- Handle password changes and settings
"""
import flet as ft
import logging
from typing import Callable, Optional, Awaitable

from config import COLORS
from database import db
from i18n import t
from services.auth import AuthService, AuthState, get_auth_service
from ui.dialogs.auth_dialogs import (
    open_unlock_dialog,
    open_setup_password_dialog,
    open_change_password_dialog,
    open_encryption_settings_dialog,
)

logger = logging.getLogger(__name__)


class AuthController:
    """
    Controller for authentication UI flows.

    Coordinates between:
    - AuthService (state management)
    - Auth dialogs (UI)
    - App lifecycle (startup, background, etc.)

    Usage:
        auth_ctrl = AuthController(page)
        await auth_ctrl.initialize()

        # On startup
        if auth_ctrl.needs_unlock:
            auth_ctrl.show_unlock_dialog()

        # Open settings
        auth_ctrl.show_encryption_settings()
    """

    def __init__(self, page: ft.Page, snack=None) -> None:
        """Initialize the auth controller.

        Args:
            page: Flet page for showing dialogs
            snack: Optional SnackService for showing feedback messages
        """
        self.page = page
        self.snack = snack
        self._auth: Optional[AuthService] = None
        self._on_unlocked: Optional[Callable[[], Awaitable[None]]] = None
        self._on_locked: Optional[Callable[[], None]] = None

    async def initialize(self) -> None:
        """Initialize the auth service and load configuration.

        Call this during app startup, before loading any data.
        """
        self._auth = get_auth_service(db.get_setting, db.set_setting)
        await self._auth.load_config()
        logger.info(f"Auth initialized - state: {self._auth.state.value}")

    @property
    def is_initialized(self) -> bool:
        """Check if the auth controller has been initialized."""
        return self._auth is not None

    @property
    def needs_unlock(self) -> bool:
        """Check if the app needs to be unlocked before use."""
        if self._auth is None:
            return False
        return self._auth.state == AuthState.LOCKED

    @property
    def is_unlocked(self) -> bool:
        """Check if the app is currently unlocked."""
        if self._auth is None:
            return True  # No auth means always "unlocked"
        return self._auth.is_unlocked

    @property
    def is_encryption_enabled(self) -> bool:
        """Check if encryption has been set up."""
        if self._auth is None:
            return False
        return self._auth.is_encryption_enabled

    @property
    def is_crypto_available(self) -> bool:
        """Check if the cryptography library is installed."""
        if self._auth is None:
            return False
        return self._auth.is_crypto_available

    def set_unlock_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Set callback to be called when app is successfully unlocked.

        This is typically used to reload data after unlocking.
        """
        self._on_unlocked = callback

    def set_lock_callback(self, callback: Callable[[], None]) -> None:
        """Set callback to be called when app is locked."""
        self._on_locked = callback

    def show_unlock_dialog(
        self,
        allow_cancel: bool = True,
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> None:
        """Show the unlock dialog.

        Args:
            allow_cancel: Whether to allow canceling (False for mandatory unlock)
            on_cancel: Callback when user cancels
        """
        if self._auth is None:
            return

        async def handle_unlock(password: str) -> bool:
            success = await self._auth.unlock_with_password(password)
            if success and self._on_unlocked:
                await self._on_unlocked()
            return success

        open_unlock_dialog(
            self.page,
            on_unlock=handle_unlock,
            on_cancel=on_cancel,
            allow_cancel=allow_cancel,
        )

    def show_setup_dialog(
        self,
        on_skip: Optional[Callable[[], None]] = None,
    ) -> None:
        """Show the initial encryption setup dialog.

        Args:
            on_skip: Callback when user skips setup
        """
        if self._auth is None:
            return

        async def handle_setup(password: str) -> None:
            await self._auth.setup_master_password(password)
            if self._on_unlocked:
                await self._on_unlocked()

        open_setup_password_dialog(
            self.page,
            on_setup=handle_setup,
            on_skip=on_skip,
        )

    def show_change_password_dialog(self) -> None:
        """Show the change password dialog."""
        if self._auth is None:
            return

        async def handle_change(old_password: str, new_password: str) -> bool:
            success = await self._auth.change_master_password(
                old_password,
                new_password,
                reencrypt_data_fn=db.reencrypt_all_data
            )
            if success and self.snack:
                self.snack.show(t("password_changed"), COLORS["green"])
            return success

        open_change_password_dialog(self.page, on_change=handle_change)

    def show_encryption_settings(self) -> None:
        """Show the encryption settings dialog."""
        if self._auth is None:
            return

        async def handle_disable(password: str) -> bool:
            success = await self._auth.disable_encryption(
                password,
                decrypt_data_fn=db.reencrypt_all_data,
            )
            if success and self.snack:
                self.snack.show(t("encryption_disabled"), COLORS["green"])
            return success

        async def handle_toggle_passkey(enable: bool) -> None:
            if enable:
                # TODO: Show password dialog to enable passkey
                pass
            else:
                await self._auth.disable_passkey()

        open_encryption_settings_dialog(
            self.page,
            is_enabled=self._auth.is_encryption_enabled,
            is_passkey_available=self._auth.is_passkey_available,
            is_passkey_enabled=self._auth.is_passkey_enabled,
            on_setup=lambda: self.show_setup_dialog(),
            on_change_password=lambda: self.show_change_password_dialog(),
            on_disable=handle_disable,
            on_toggle_passkey=handle_toggle_passkey,
        )

    def lock(self) -> None:
        """Lock the app, clearing encryption key from memory."""
        if self._auth is None:
            return
        self._auth.lock()
        if self._on_locked:
            self._on_locked()

    async def try_biometric_unlock(self) -> bool:
        """Attempt to unlock using biometric authentication.

        Returns:
            True if unlock succeeded, False otherwise
        """
        if self._auth is None:
            return False
        success = await self._auth.unlock_with_passkey()
        if success and self._on_unlocked:
            await self._on_unlocked()
        return success
