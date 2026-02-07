"""
Authentication dialogs for Trebnic.

Provides:
- Unlock dialog (enter master password)
- Setup dialog (create master password)
- Change password dialog
- Encryption settings dialog
"""
import flet as ft
from typing import Callable, Optional, Awaitable

from config import (
    COLORS, BORDER_RADIUS, DIALOG_WIDTH_LG,
    PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH,
    FONT_SIZE_SM, FONT_SIZE_MD, SPACING_MD, SPACING_LG,
)
from i18n import t
from ui.dialogs.base import open_dialog


def _create_password_field(
    label: str,
    hint: str = "",
    on_submit: Optional[Callable[[ft.ControlEvent], None]] = None,
) -> ft.TextField:
    """Create a styled password input field."""
    return ft.TextField(
        label=label,
        hint_text=hint,
        password=True,
        can_reveal_password=True,
        border_radius=BORDER_RADIUS,
        bgcolor=COLORS["input_bg"],
        border_color=COLORS["border"],
        focused_border_color=COLORS["accent"],
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        on_submit=on_submit,
    )


def _validate_password(password: str) -> Optional[str]:
    """Validate password meets security requirements. Returns error message or None.

    Requirements:
    - At least PASSWORD_MIN_LENGTH characters
    - At most PASSWORD_MAX_LENGTH characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return t("password_min_length").format(length=PASSWORD_MIN_LENGTH)
    if len(password) > PASSWORD_MAX_LENGTH:
        return t("password_max_length").format(length=PASSWORD_MAX_LENGTH)
    if not any(c.isupper() for c in password):
        return t("password_needs_uppercase")
    if not any(c.islower() for c in password):
        return t("password_needs_lowercase")
    if not any(c.isdigit() for c in password):
        return t("password_needs_digit")
    return None


def open_unlock_dialog(
    page: ft.Page,
    on_unlock: Callable[[str], Awaitable[bool]],
    on_cancel: Optional[Callable[[], None]] = None,
    allow_cancel: bool = True,
) -> None:
    """Open the unlock dialog for entering master password.

    Args:
        page: Flet page
        on_unlock: Async callback that receives password, returns True if valid
        on_cancel: Optional callback when user cancels
        allow_cancel: Whether to show cancel button (False for mandatory unlock)
    """
    password_field = _create_password_field(
        t("master_password"),
        t("enter_master_password"),
    )
    error_text = ft.Text("", color=COLORS["danger"], size=FONT_SIZE_SM, visible=False)
    loading = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

    async def handle_unlock(e: Optional[ft.ControlEvent] = None) -> None:
        password = password_field.value or ""

        if not password:
            error_text.value = t("please_enter_password")
            error_text.visible = True
            page.update()
            return

        # Show loading state
        loading.visible = True
        error_text.visible = False
        page.update()

        try:
            success = await on_unlock(password)
            if success:
                page.pop_dialog()
            else:
                error_text.value = t("incorrect_password")
                error_text.visible = True
                password_field.value = ""
                password_field.focus()
        finally:
            loading.visible = False
            page.update()

    # Wire up submit on enter
    password_field.on_submit = lambda e: page.run_task(handle_unlock)

    content = ft.Column(
        [
            ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color=COLORS["accent"]),
            ft.Text(
                t("your_data_is_encrypted"),
                size=FONT_SIZE_MD,
                color=COLORS["done_text"],
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=SPACING_LG),
            password_field,
            error_text,
        ],
        width=DIALOG_WIDTH_LG,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=SPACING_MD,
    )

    def make_actions(close: Callable[[], None]):
        actions = []

        if allow_cancel:
            def handle_cancel(e):
                close()
                if on_cancel:
                    on_cancel()

            actions.append(
                ft.TextButton(t("cancel"), on_click=handle_cancel)
            )

        actions.append(
            ft.Row(
                [
                    loading,
                    ft.Button(
                        t("unlock"),
                        icon=ft.Icons.LOCK_OPEN,
                        bgcolor=COLORS["accent"],
                        color=COLORS["white"],
                        on_click=lambda e: page.run_task(handle_unlock),
                    ),
                ],
                spacing=SPACING_MD,
            )
        )

        return actions

    dialog, _ = open_dialog(page, t("unlock_trebnic"), content, make_actions)


def open_setup_password_dialog(
    page: ft.Page,
    on_setup: Callable[[str], Awaitable[None]],
    on_skip: Optional[Callable[[], None]] = None,
) -> None:
    """Open dialog to set up master password for first time.

    Args:
        page: Flet page
        on_setup: Async callback that receives the new password
        on_skip: Optional callback when user skips encryption setup
    """
    password_field = _create_password_field(
        t("create_password"),
        t("choose_strong_password"),
    )
    confirm_field = _create_password_field(
        t("confirm_password"),
        t("enter_password_again"),
    )
    error_text = ft.Text("", color=COLORS["danger"], size=FONT_SIZE_SM, visible=False)
    loading = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

    async def handle_setup(e: Optional[ft.ControlEvent] = None) -> None:
        password = password_field.value or ""
        confirm = confirm_field.value or ""

        # Validate password
        validation_error = _validate_password(password)
        if validation_error:
            error_text.value = validation_error
            error_text.visible = True
            page.update()
            return

        # Check passwords match
        if password != confirm:
            error_text.value = t("passwords_do_not_match")
            error_text.visible = True
            confirm_field.value = ""
            confirm_field.focus()
            page.update()
            return

        # Show loading state
        loading.visible = True
        error_text.visible = False
        page.update()

        try:
            await on_setup(password)
            page.pop_dialog()
        except Exception as ex:
            error_text.value = f"{t('setup_failed')}: {ex}"
            error_text.visible = True
        finally:
            loading.visible = False
            page.update()

    # Wire up submit on enter
    confirm_field.on_submit = lambda e: page.run_task(handle_setup)

    content = ft.Column(
        [
            ft.Icon(ft.Icons.SECURITY, size=48, color=COLORS["accent"]),
            ft.Text(
                t("protect_data_with_encryption"),
                size=FONT_SIZE_MD,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                t("master_password_desc"),
                size=FONT_SIZE_SM,
                color=COLORS["done_text"],
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(height=SPACING_MD),
            password_field,
            confirm_field,
            error_text,
            ft.Container(height=SPACING_MD),
            ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER, size=16, color=COLORS["orange"]),
                    ft.Text(
                        t("password_forget_warning"),
                        size=FONT_SIZE_SM,
                        color=COLORS["orange"],
                        expand=True,
                    ),
                ],
                spacing=SPACING_MD,
            ),
        ],
        width=DIALOG_WIDTH_LG,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=SPACING_MD,
    )

    def make_actions(close: Callable[[], None]):
        actions = []

        if on_skip:
            def handle_skip(e):
                close()
                on_skip()

            actions.append(
                ft.TextButton(t("skip_for_now"), on_click=handle_skip)
            )

        actions.append(
            ft.Row(
                [
                    loading,
                    ft.Button(
                        t("enable_encryption"),
                        icon=ft.Icons.LOCK,
                        bgcolor=COLORS["accent"],
                        color=COLORS["white"],
                        on_click=lambda e: page.run_task(handle_setup),
                    ),
                ],
                spacing=SPACING_MD,
            )
        )

        return actions

    dialog, _ = open_dialog(page, t("set_up_encryption"), content, make_actions)


def open_change_password_dialog(
    page: ft.Page,
    on_change: Callable[[str, str], Awaitable[bool]],
) -> None:
    """Open dialog to change master password.

    Args:
        page: Flet page
        on_change: Async callback (old_password, new_password) -> success
    """
    current_field = _create_password_field(t("current_password"))
    new_field = _create_password_field(t("new_password"))
    confirm_field = _create_password_field(t("confirm_new_password"))
    error_text = ft.Text("", color=COLORS["danger"], size=FONT_SIZE_SM, visible=False)
    loading = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)

    async def handle_change(e: Optional[ft.ControlEvent] = None) -> None:
        current = current_field.value or ""
        new_password = new_field.value or ""
        confirm = confirm_field.value or ""

        if not current:
            error_text.value = t("please_enter_current_password")
            error_text.visible = True
            page.update()
            return

        validation_error = _validate_password(new_password)
        if validation_error:
            error_text.value = validation_error
            error_text.visible = True
            page.update()
            return

        if new_password != confirm:
            error_text.value = t("new_passwords_do_not_match")
            error_text.visible = True
            confirm_field.value = ""
            confirm_field.focus()
            page.update()
            return

        loading.visible = True
        error_text.visible = False
        page.update()

        try:
            success = await on_change(current, new_password)
            if success:
                page.pop_dialog()
                # TODO: Show success snackbar
            else:
                error_text.value = t("current_password_incorrect")
                error_text.visible = True
                current_field.value = ""
                current_field.focus()
        except Exception as ex:
            error_text.value = f"{t('failed')}: {ex}"
            error_text.visible = True
        finally:
            loading.visible = False
            page.update()

    confirm_field.on_submit = lambda e: page.run_task(handle_change)

    content = ft.Column(
        [
            current_field,
            ft.Divider(height=SPACING_LG, color="transparent"),
            new_field,
            confirm_field,
            error_text,
        ],
        width=DIALOG_WIDTH_LG,
        spacing=SPACING_MD,
    )

    def make_actions(close: Callable[[], None]):
        return [
            ft.TextButton(t("cancel"), on_click=lambda e: close()),
            ft.Row(
                [
                    loading,
                    ft.Button(
                        t("change_password"),
                        bgcolor=COLORS["accent"],
                        color=COLORS["white"],
                        on_click=lambda e: page.run_task(handle_change),
                    ),
                ],
                spacing=SPACING_MD,
            ),
        ]

    dialog, _ = open_dialog(page, t("change_master_password"), content, make_actions)


def open_encryption_settings_dialog(
    page: ft.Page,
    is_enabled: bool,
    is_passkey_available: bool,
    is_passkey_enabled: bool,
    on_setup: Callable[[], None],
    on_change_password: Callable[[], None],
    on_disable: Callable[[], Awaitable[None]],
    on_toggle_passkey: Callable[[bool], Awaitable[None]],
) -> None:
    """Open encryption settings dialog.

    Args:
        page: Flet page
        is_enabled: Whether encryption is currently enabled
        is_passkey_available: Whether biometric auth is available
        is_passkey_enabled: Whether biometric auth is enabled
        on_setup: Callback to open setup dialog
        on_change_password: Callback to open change password dialog
        on_disable: Async callback to disable encryption
        on_toggle_passkey: Async callback to toggle passkey (True = enable)
    """

    def create_setting_row(icon: str, title: str, subtitle: str, action: ft.Control) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon, color=COLORS["accent"], size=24),
                    ft.Column(
                        [
                            ft.Text(title, weight=ft.FontWeight.W_500),
                            ft.Text(subtitle, size=FONT_SIZE_SM, color=COLORS["done_text"]),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    action,
                ],
                spacing=SPACING_LG,
            ),
            padding=SPACING_MD,
        )

    if is_enabled:
        # Encryption is enabled - show management options
        rows = [
            ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color=COLORS["green"], size=20),
                        ft.Text(t("encryption_enabled"), color=COLORS["green"]),
                    ],
                    spacing=SPACING_MD,
                ),
                padding=SPACING_MD,
                bgcolor=COLORS["card"],
                border_radius=BORDER_RADIUS,
            ),
            ft.Divider(height=SPACING_LG, color="transparent"),
            create_setting_row(
                ft.Icons.KEY,
                t("change_password"),
                t("update_master_password"),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    on_click=lambda e: (page.pop_dialog(), on_change_password()),
                ),
            ),
        ]

        # Passkey option (if available)
        if is_passkey_available:
            async def toggle_passkey(e):
                await on_toggle_passkey(not is_passkey_enabled)
                page.pop_dialog()

            rows.append(
                create_setting_row(
                    ft.Icons.FINGERPRINT,
                    t("biometric_unlock"),
                    t("biometric_unlock_desc"),
                    ft.Switch(
                        value=is_passkey_enabled,
                        on_change=lambda e: page.run_task(toggle_passkey),
                    ),
                )
            )

        # Disable encryption option
        async def handle_disable(e):
            # TODO: Show confirmation dialog
            await on_disable()
            page.pop_dialog()

        rows.append(
            ft.Container(
                content=ft.TextButton(
                    t("disable_encryption"),
                    icon=ft.Icons.LOCK_OPEN,
                    icon_color=COLORS["danger"],
                    style=ft.ButtonStyle(color=COLORS["danger"]),
                    on_click=lambda e: page.run_task(handle_disable),
                ),
                padding=ft.Padding.only(top=SPACING_LG),
            )
        )
    else:
        # Encryption not enabled - show setup option
        rows = [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.SHIELD_OUTLINED, size=48, color=COLORS["accent"]),
                        ft.Text(
                            t("encryption_not_enabled"),
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            t("encryption_not_enabled_desc"),
                            size=FONT_SIZE_SM,
                            color=COLORS["done_text"],
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=SPACING_MD,
                ),
                padding=SPACING_LG,
            ),
            ft.Button(
                t("set_up_encryption"),
                icon=ft.Icons.LOCK,
                bgcolor=COLORS["accent"],
                color=COLORS["white"],
                on_click=lambda e: (page.pop_dialog(), on_setup()),
            ),
        ]

    content = ft.Column(
        rows,
        width=DIALOG_WIDTH_LG,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=SPACING_MD,
    )

    def make_actions(close: Callable[[], None]):
        return [
            ft.Button(
                t("close"),
                icon=ft.Icons.CLOSE,
                on_click=lambda e: close(),
            )
        ]

    dialog, _ = open_dialog(page, t("encryption_settings"), content, make_actions)
