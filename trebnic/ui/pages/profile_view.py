import json
import flet as ft
from datetime import date, datetime, time
from typing import Callable, Optional

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    PermissionResult,
    DURATION_SLIDER_STEP,
    DURATION_SLIDER_MIN,
    DURATION_SLIDER_MAX,
    DIALOG_WIDTH_MD,
)
from models.entities import AppState
from database import db, DatabaseError
from services.logic import TaskService
from services.notification_service import notification_service, NotificationBackend
from services.settings_service import SettingsService
from ui.helpers import format_duration, accent_btn, danger_btn, SnackService
from ui.dialogs.base import open_dialog
from events import event_bus, AppEvent
from i18n import set_language, t, get_language


class ProfilePage:
    def __init__(
        self,
        page: ft.Page,
        state: AppState,
        task_service: TaskService,
        settings_service: SettingsService,
        snack: SnackService,
        navigate: Callable[[PageType], None],
        tasks_view=None,
    ) -> None:
        self.page = page
        self.state = state
        self.task_service = task_service
        self.settings_service = settings_service
        self.snack = snack
        self.navigate = navigate
        self.tasks_view = tasks_view
        self._avatar_path: Optional[str] = None
        self._avatar_icon: Optional[ft.Icon] = None
        self._avatar_image: Optional[ft.Image] = None
        self._file_picker = ft.FilePicker()
        self.page.services.append(self._file_picker)

    def cleanup(self) -> None:
        """Remove file picker from page services. Call when the page is destroyed."""
        if self._file_picker in self.page.services:
            self.page.services.remove(self._file_picker)

    def set_tasks_view(self, tasks_view) -> None:
        """Set the tasks view reference (for updating pending details on save)."""
        self.tasks_view = tasks_view

    def _on_avatar_click(self, e: ft.ControlEvent) -> None:
        """Open file picker to select avatar image."""
        async def _pick_avatar() -> None:
            files = await self._file_picker.pick_files(
                allowed_extensions=["png", "jpg", "jpeg", "gif", "webp"],
                dialog_title=t("select_profile_photo"),
            )
            if files and len(files) > 0:
                self._avatar_path = files[0].path
                if self._avatar_icon and self._avatar_image:
                    self._avatar_icon.visible = False
                    self._avatar_image.src = self._avatar_path
                    self._avatar_image.visible = True
                    self.page.update()
        self.page.run_task(_pick_avatar)

    def _build_lang_en(self) -> ft.Text:
        """Build English language option with EN code."""
        return ft.Text("EN", size=12, weight="bold")

    def _build_lang_ro(self) -> ft.Text:
        """Build Romanian language option with RO code."""
        return ft.Text("RO", size=12, weight="bold")

    def _build_romanian_flag(self) -> ft.Container:
        """Build a Romanian flag using colored stripes (blue, yellow, red)."""
        flag_height = 12
        stripe_width = 6
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(width=stripe_width, height=flag_height, bgcolor="#002B7F"),  # Blue
                    ft.Container(width=stripe_width, height=flag_height, bgcolor="#FCD116"),  # Yellow
                    ft.Container(width=stripe_width, height=flag_height, bgcolor="#CE1126"),  # Red
                ],
                spacing=0,
            ),
            border_radius=2,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )

    def _build_language_toggle(self) -> ft.Container:
        """Build a pill-style language toggle: Globe > GB > RO > Romanian flag."""
        # Store refs for dynamic updates
        en_container: ft.Container = None
        ro_container: ft.Container = None

        def update_toggle_state() -> None:
            is_en = self.state.language == "en"
            en_container.bgcolor = COLORS["accent"] if is_en else "transparent"
            ro_container.bgcolor = COLORS["accent"] if not is_en else "transparent"

        def select_en(e: ft.ControlEvent) -> None:
            if get_language() == "en":
                return
            self.state.language = "en"
            set_language("en")
            update_toggle_state()
            event_bus.emit(AppEvent.LANGUAGE_CHANGED)
            self.page.update()

        def select_ro(e: ft.ControlEvent) -> None:
            if get_language() == "ro":
                return
            self.state.language = "ro"
            set_language("ro")
            update_toggle_state()
            event_bus.emit(AppEvent.LANGUAGE_CHANGED)
            self.page.update()

        is_en = self.state.language == "en"

        # English: Globe icon + GB text
        en_container = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LANGUAGE, size=16, color=COLORS["white"]),
                    self._build_lang_en(),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=5),
            border_radius=12,
            bgcolor=COLORS["accent"] if is_en else "transparent",
            on_click=select_en,
            ink=True,
        )

        # Romanian: RO text + Romanian flag
        ro_container = ft.Container(
            content=ft.Row(
                [
                    self._build_lang_ro(),
                    self._build_romanian_flag(),
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=5),
            border_radius=12,
            bgcolor=COLORS["accent"] if not is_en else "transparent",
            on_click=select_ro,
            ink=True,
        )

        return ft.Container(
            content=ft.Row(
                [en_container, ro_container],
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=COLORS["input_bg"],
            border_radius=16,
            padding=3,
        )

    def _export_data(self, e: ft.ControlEvent) -> None:
        """Export all app data to a JSON file."""
        async def _do_export() -> None:
            data = await db.export_all()
            json_data = json.dumps(data, indent=2, ensure_ascii=False)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trebnic_backup_{timestamp}.json"

            result = await self._file_picker.save_file(
                dialog_title=t("export_data"),
                file_name=filename,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["json"],
            )
            if result:
                try:
                    with open(result, "w", encoding="utf-8") as f:
                        f.write(json_data)
                    self.snack.show(f"{t('exported_to')} {result}")
                except OSError as ex:
                    self.snack.show(f"{t('export_failed')}: {ex}", COLORS["danger"])

        self.page.run_task(_do_export)

    def _import_data(self, e: ft.ControlEvent) -> None:
        """Import app data from a JSON backup file."""
        async def _do_import() -> None:
            files = await self._file_picker.pick_files(
                allowed_extensions=["json"],
                dialog_title=t("import_data"),
            )
            if not files:
                return

            file_path = files[0].path
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.loads(f.read())
            except (OSError, json.JSONDecodeError) as ex:
                self.snack.show(f"{t('import_failed')}: {ex}", COLORS["danger"])
                return

            def confirm_import(ce: ft.ControlEvent) -> None:
                async def _run_import() -> None:
                    try:
                        await db.import_all(
                            projects=data.get("projects", []),
                            tasks=data.get("tasks", []),
                            time_entries=data.get("time_entries", []),
                            daily_notes=data.get("daily_notes", []),
                            settings=data.get("settings", {}),
                        )
                        close()
                        event_bus.emit(AppEvent.DATA_RESET)
                        self.snack.show(t("import_success"))
                    except DatabaseError as ex:
                        close()
                        self.snack.show(f"{t('import_failed')}: {ex}", COLORS["danger"])
                self.page.run_task(_run_import)

            _, close = open_dialog(
                self.page,
                t("import_confirm_title"),
                ft.Container(
                    width=DIALOG_WIDTH_MD,
                    content=ft.Text(t("import_confirm_body"), text_align=ft.TextAlign.CENTER),
                ),
                lambda c: [
                    ft.TextButton(t("cancel"), on_click=c),
                    danger_btn(t("import_data"), confirm_import),
                ],
            )

        self.page.run_task(_do_import)

    def _build_data_management_section(self) -> ft.Container:
        """Build the data management section with export and import buttons."""
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(t("data_management"), weight="bold", size=16),
                    ft.Divider(height=10, color=COLORS["border"]),
                    ft.Row(
                        [
                            ft.Button(
                                t("export_data"),
                                icon=ft.Icons.FILE_DOWNLOAD,
                                on_click=self._export_data,
                                bgcolor=COLORS["accent"],
                                color=COLORS["bg"],
                            ),
                            ft.Button(
                                t("import_data"),
                                icon=ft.Icons.FILE_UPLOAD,
                                on_click=self._import_data,
                                bgcolor=COLORS["card"],
                                color=COLORS["white"],
                            ),
                        ],
                        spacing=10,
                        wrap=True,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=COLORS["card"],
            padding=15,
            border_radius=BORDER_RADIUS,
        )

    def _open_reset_dialog(self, e: ft.ControlEvent) -> None:
        def confirm(e: ft.ControlEvent) -> None:
            async def _reset() -> None:
                await self.task_service.reset()
                close()
                event_bus.emit(AppEvent.DATA_RESET)
                self.snack.show(t("all_data_reset"), COLORS["danger"])
            self.page.run_task(_reset)

        content = ft.Container(
            width=DIALOG_WIDTH_MD,
            content=ft.Column(
                [
                    ft.Icon(
                        ft.Icons.WARNING_AMBER_ROUNDED,
                        size=48,
                        color=COLORS["danger"],
                    ),
                    ft.Text(
                        t("cannot_be_undone"),
                        weight="bold",
                        color=COLORS["danger"],
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        t("all_data_deleted"),
                        text_align=ft.TextAlign.CENTER,
                        color=COLORS["done_text"],
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=15,
            ),
        )

        _, close = open_dialog(
            self.page,
            t("factory_reset_title"),
            content,
            lambda c: [
                ft.TextButton(t("cancel"), on_click=c),
                danger_btn(t("reset_everything"), confirm),
            ],
        )

    def _build_preferences_section(self) -> ft.Container:
        """Build the preferences section with estimated time and notifications."""
        duration_label = ft.Text(
            format_duration(self.state.default_estimated_minutes),
            size=14,
            weight="bold",
        )

        def on_slider(e: ft.ControlEvent) -> None:
            duration_label.value = format_duration(int(e.control.value) * DURATION_SLIDER_STEP)
            duration_label.update()

        slider = ft.Slider(
            min=DURATION_SLIDER_MIN,
            max=DURATION_SLIDER_MAX,
            divisions=DURATION_SLIDER_MAX - DURATION_SLIDER_MIN,
            value=self.state.default_estimated_minutes // DURATION_SLIDER_STEP,
            on_change=on_slider,
        )

        email_cb = ft.Checkbox(
            value=self.state.email_weekly_stats,
            label=t("email_weekly_stats"),
        )

        # Notification settings
        def on_notifications_toggle(e: ft.ControlEvent) -> None:
            async def _toggle() -> None:
                if e.control.value:
                    result = await notification_service.request_permission()
                    if result == PermissionResult.DENIED:
                        e.control.value = False
                        self.snack.show(t("notification_permission_denied"), COLORS["danger"])
                        self.page.update()
                        return
                    else:
                        self.snack.show(t("notification_permission_granted"))
                self.state.notifications_enabled = e.control.value
                self.page.update()
            self.page.run_task(_toggle)

        def on_test_notification(e: ft.ControlEvent) -> None:
            try:
                backend = notification_service.backend
                if backend == NotificationBackend.NONE:
                    self.snack.show(f"{t('test_notification_unavailable')} (backend: none)", COLORS["danger"])
                    return

                async def _test() -> None:
                    try:
                        ntitle = t("test_notification_title")
                        body = t("test_notification_body")
                        success = await notification_service.test_notification(ntitle, body)
                        if success:
                            self.snack.show(f"{t('test_notification_sent')} ({backend.value})")
                        else:
                            self.snack.show(f"{t('test_notification_failed')} ({backend.value})", COLORS["danger"])
                    except (OSError, RuntimeError, ValueError) as ex:
                        self.snack.show(f"Error: {ex}", COLORS["danger"])
                self.page.run_task(_test)
            except (OSError, RuntimeError, ValueError) as ex:
                self.snack.show(f"Error: {ex}", COLORS["danger"])

        notifications_switch = ft.Switch(
            value=self.state.notifications_enabled,
            on_change=on_notifications_toggle,
        )

        # Hour options for digest time pickers (06:00 - 22:00)
        hour_options = [ft.Option(key=str(h), text=f"{h:02d}:00") for h in range(6, 23)]

        def _make_digest_row(label_key: str, desc_key: str, enabled: bool, current_time: time) -> tuple:
            switch = ft.Switch(value=enabled)
            dropdown = ft.Dropdown(
                options=hour_options,
                value=str(current_time.hour),
                width=100,
                dense=True,
                content_padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            )
            row = ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(t(label_key), size=13),
                            ft.Text(t(desc_key), size=11, color=COLORS["done_text"]),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    switch,
                    dropdown,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            return row, switch, dropdown

        digest_row, digest_switch, digest_dropdown = _make_digest_row(
            "daily_digest", "daily_digest_desc",
            self.state.daily_digest_enabled, self.state.daily_digest_time,
        )
        preview_row, preview_switch, preview_dropdown = _make_digest_row(
            "evening_preview", "evening_preview_desc",
            self.state.evening_preview_enabled, self.state.evening_preview_time,
        )
        overdue_row, overdue_switch, overdue_dropdown = _make_digest_row(
            "overdue_nudge", "overdue_nudge_desc",
            self.state.overdue_nudge_enabled, self.state.overdue_nudge_time,
        )

        notification_sub_controls = ft.Column(
            [
                digest_row,
                preview_row,
                overdue_row,
                ft.Divider(height=5, color="transparent"),
                ft.TextButton(
                    t("test_notification"),
                    icon=ft.Icons.NOTIFICATIONS_ACTIVE,
                    on_click=on_test_notification,
                ),
            ],
            spacing=8,
        )

        def save(e: ft.ControlEvent) -> None:
            async def _save() -> None:
                self.state.default_estimated_minutes = (
                    int(slider.value) * DURATION_SLIDER_STEP
                )
                self.state.email_weekly_stats = email_cb.value
                # Sync digest notification settings to state before saving
                self.state.daily_digest_enabled = digest_switch.value
                self.state.daily_digest_time = time(int(digest_dropdown.value), 0)
                self.state.evening_preview_enabled = preview_switch.value
                self.state.evening_preview_time = time(int(preview_dropdown.value), 0)
                self.state.overdue_nudge_enabled = overdue_switch.value
                self.state.overdue_nudge_time = time(int(overdue_dropdown.value), 0)
                try:
                    await self.settings_service.save_settings()
                except DatabaseError as ex:
                    self.snack.show(f"{t('failed')}: {ex}", COLORS["danger"])
                    return
                # Reschedule digest alarms after settings change
                await notification_service.reschedule_digests()
                if self.tasks_view:
                    self.tasks_view.pending_details["estimated_minutes"] = (
                        self.state.default_estimated_minutes
                    )
                    self.tasks_view._details_text.value = t("add_details")
                self.snack.show(t("preferences_saved"))
            self.page.run_task(_save)

        def reset_defaults(e: ft.ControlEvent) -> None:
            slider.value = 15 // DURATION_SLIDER_STEP
            duration_label.value = format_duration(15)
            email_cb.value = False
            if get_language() != "en":
                self.state.language = "en"
                set_language("en")
                event_bus.emit(AppEvent.LANGUAGE_CHANGED)
            self.page.update()

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(t("preferences"), weight="bold", size=16),
                    ft.Divider(height=10, color=COLORS["border"]),
                    ft.Text(t("default_estimated_time"), size=13),
                    ft.Row([ft.Icon(ft.Icons.TIMER, size=18), duration_label], spacing=8),
                    slider,
                    ft.Text(
                        t("time_range_hint"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                    ft.Divider(height=10, color="transparent"),
                    ft.Text(t("notifications"), size=13),
                    email_cb,
                    ft.Divider(height=10, color="transparent"),
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.NOTIFICATIONS, size=18),
                                    ft.Text(t("notifications_enabled"), size=13),
                                ],
                                spacing=8,
                            ),
                            notifications_switch,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    notification_sub_controls,
                    ft.Divider(height=10, color="transparent"),
                    ft.Row(
                        [
                            ft.TextButton(
                                t("reset_defaults"),
                                on_click=reset_defaults,
                                style=ft.ButtonStyle(color=COLORS["done_text"]),
                            ),
                            accent_btn(t("save_preferences"), save),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=COLORS["card"],
            padding=15,
            border_radius=BORDER_RADIUS,
        )

    def build(self) -> ft.Column:
        most_active = None
        if self.state.projects:
            most_active = max(
                self.state.projects,
                key=lambda p: len([
                    task for task in self.state.done_tasks if task.project_id == p.id
                ]),
                default=None,
            )

        back_btn = ft.IconButton(
            ft.Icons.ARROW_BACK,
            on_click=lambda e: self.navigate(PageType.TASKS),
            icon_color=COLORS["accent"],
        )
        language_toggle = self._build_language_toggle()
        header = ft.Row(
            [
                back_btn,
                ft.Text(t("profile"), size=24, weight="bold"),
                ft.Container(expand=True),
                language_toggle,
            ],
        )

        self._avatar_icon = ft.Icon(
            ft.Icons.ACCOUNT_CIRCLE,
            size=64,
            color=COLORS["accent"],
            visible=self._avatar_path is None,
        )
        self._avatar_image = ft.Image(
            src=self._avatar_path or "",
            width=64,
            height=64,
            fit=ft.BoxFit.COVER,
            border_radius=32,
            visible=self._avatar_path is not None,
        )
        avatar_section = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Stack(
                            [
                                self._avatar_icon,
                                self._avatar_image,
                            ],
                        ),
                        on_click=self._on_avatar_click,
                        ink=True,
                        border_radius=32,
                    ),
                    ft.Text(t("user"), size=18, weight="bold"),
                    ft.Text(
                        t("tap_photo_to_change"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=5,
            ),
            alignment=ft.Alignment(0, 0),
            padding=10,
        )

        account_age_card = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CALENDAR_TODAY, color=COLORS["accent"], size=18),
                    ft.Column(
                        [
                            ft.Text(t("account_age"), weight="bold", size=13),
                            ft.Text(
                                f"{t('since')} {(self.state.account_created or date.today()).strftime('%b %d, %Y')}",
                                color=COLORS["done_text"],
                                size=12,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=12,
            border_radius=BORDER_RADIUS,
        )

        tasks_completed_card = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color=COLORS["green"], size=18),
                    ft.Column(
                        [
                            ft.Text(t("tasks_completed"), weight="bold", size=13),
                            ft.Text(
                                f"{len(self.state.done_tasks)} {t('total')}",
                                color=COLORS["done_text"],
                                size=12,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=12,
            border_radius=BORDER_RADIUS,
        )

        most_active_name = most_active.name if most_active else t("none")
        most_active_card = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.FOLDER, color=COLORS["blue"], size=18),
                    ft.Column(
                        [
                            ft.Text(t("most_active_project"), weight="bold", size=13),
                            ft.Text(
                                most_active_name,
                                color=COLORS["done_text"],
                                size=12,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=10,
            ),
            bgcolor=COLORS["card"],
            padding=12,
            border_radius=BORDER_RADIUS,
        )

        preferences_section = self._build_preferences_section()
        data_management_section = self._build_data_management_section()

        reset_btn_container = ft.Container(
            content=danger_btn(
                t("factory_reset"),
                self._open_reset_dialog,
                icon=ft.Icons.RESTORE,
            ),
            alignment=ft.Alignment(0, 0),
        )

        return ft.Column(
            [
                header,
                avatar_section,
                ft.Divider(height=10, color=COLORS["border"]),
                account_age_card,
                tasks_completed_card,
                most_active_card,
                ft.Divider(height=15, color="transparent"),
                preferences_section,
                ft.Divider(height=15, color="transparent"),
                data_management_section,
                ft.Divider(height=15, color="transparent"),
                reset_btn_container,
            ],
            spacing=8,
        )