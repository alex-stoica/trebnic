import json
import logging
import flet as ft
from datetime import date, datetime, time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from config import (
    COLORS,
    BORDER_RADIUS,
    PageType,
    PermissionResult,
    DURATION_SLIDER_STEP,
    DURATION_SLIDER_MIN,
    DURATION_SLIDER_MAX,
    DIALOG_WIDTH_MD,
    SPACING_XS,
    SPACING_SM,
    SPACING_MD,
    SPACING_LG,
    SPACING_2XL,
    PADDING_SM,
    PADDING_MD,
    PADDING_LG,
    PADDING_XL,
    PADDING_2XL,
)
from models.entities import AppState
from database import db, DatabaseError
from services.logic import TaskService
from services.notification_service import notification_service, NotificationBackend
from services.settings_service import SettingsService
from ui.helpers import format_duration, danger_btn, SnackService
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

        def _apply_language(lang: str) -> None:
            self.state.language = lang
            set_language(lang)
            update_toggle_state()
            event_bus.emit(AppEvent.LANGUAGE_CHANGED)
            self.page.update()

            async def _persist() -> None:
                try:
                    await db.set_setting("language", lang)
                except DatabaseError as ex:
                    self.snack.show(f"{t('failed')}: {ex}", COLORS["danger"])
            self.page.run_task(_persist)

        def select_en(e: ft.ControlEvent) -> None:
            if get_language() == "en":
                return
            _apply_language("en")

        def select_ro(e: ft.ControlEvent) -> None:
            if get_language() == "ro":
                return
            _apply_language("ro")

        is_en = self.state.language == "en"

        # English: Globe icon + GB text
        en_container = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LANGUAGE, size=16, color=COLORS["white"]),
                    self._build_lang_en(),
                ],
                spacing=SPACING_SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=PADDING_MD, vertical=PADDING_SM),
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
                spacing=SPACING_SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding.symmetric(horizontal=PADDING_MD, vertical=PADDING_SM),
            border_radius=12,
            bgcolor=COLORS["accent"] if not is_en else "transparent",
            on_click=select_ro,
            ink=True,
        )

        return ft.Container(
            content=ft.Row(
                [en_container, ro_container],
                spacing=SPACING_XS,
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
                    ft.Divider(height=SPACING_LG, color=COLORS["border"]),
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
                        spacing=SPACING_LG,
                        wrap=True,
                    ),
                ],
                spacing=SPACING_MD,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
            border_radius=BORDER_RADIUS,
        )

    def _open_reset_dialog(self, e: ft.ControlEvent) -> None:
        keyword = t("reset_keyword")
        reset_btn = danger_btn(t("reset_everything"), lambda e: None)
        reset_btn.disabled = True

        def on_input_change(e: ft.ControlEvent) -> None:
            typed = (e.control.value or "").strip()
            reset_btn.disabled = typed != keyword
            reset_btn.update()

        confirm_field = ft.TextField(
            hint_text=t("type_reset_to_confirm").format(keyword=keyword),
            border_color=COLORS["border"],
            bgcolor=COLORS["input_bg"],
            border_radius=BORDER_RADIUS,
            text_align=ft.TextAlign.CENTER,
            on_change=on_input_change,
        )

        def confirm(e: ft.ControlEvent) -> None:
            async def _reset() -> None:
                try:
                    await self.task_service.reset()
                except DatabaseError as ex:
                    self.snack.show(t("factory_reset_failed").format(error=ex), COLORS["danger"])
                    return
                close()
                event_bus.emit(AppEvent.DATA_RESET)
                self.snack.show(t("all_data_reset"), COLORS["danger"])
            self.page.run_task(_reset)

        reset_btn.on_click = confirm

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
                    confirm_field,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING_2XL,
            ),
        )

        _, close = open_dialog(
            self.page,
            t("factory_reset_title"),
            content,
            lambda c: [
                ft.TextButton(t("cancel"), on_click=c),
                reset_btn,
            ],
        )

    def _build_preferences_section(self) -> ft.Container:
        """Build the preferences section with estimated time and notifications.

        Every control auto-persists on change. There is no Save button — the page
        behaves like a real Android settings screen so users never lose changes
        by tapping back. The slider persists on release (on_change_end) to avoid
        a DB write per drag tick.
        """
        duration_label = ft.Text(
            format_duration(self.state.default_estimated_minutes),
            size=14,
            weight="bold",
        )

        def on_slider(e: ft.ControlEvent) -> None:
            duration_label.value = format_duration(int(e.control.value) * DURATION_SLIDER_STEP)
            duration_label.update()

        def on_slider_end(e: ft.ControlEvent) -> None:
            new_value = int(e.control.value) * DURATION_SLIDER_STEP
            self.state.default_estimated_minutes = new_value
            if self.tasks_view:
                self.tasks_view.pending_details["estimated_minutes"] = new_value
                self.tasks_view._details_text.value = t("add_details")

            async def _do() -> None:
                try:
                    await db.set_setting("default_estimated_minutes", new_value)
                except DatabaseError as ex:
                    self.snack.show(f"{t('failed')}: {ex}", COLORS["danger"])
            self.page.run_task(_do)

        slider = ft.Slider(
            min=DURATION_SLIDER_MIN,
            max=DURATION_SLIDER_MAX,
            divisions=DURATION_SLIDER_MAX - DURATION_SLIDER_MIN,
            value=self.state.default_estimated_minutes // DURATION_SLIDER_STEP,
            on_change=on_slider,
            on_change_end=on_slider_end,
        )

        def on_email_change(e: ft.ControlEvent) -> None:
            self.state.email_weekly_stats = e.control.value

            async def _do() -> None:
                try:
                    await db.set_setting("email_weekly_stats", e.control.value)
                except DatabaseError as ex:
                    self.snack.show(f"{t('failed')}: {ex}", COLORS["danger"])
            self.page.run_task(_do)

        email_cb = ft.Checkbox(
            value=self.state.email_weekly_stats,
            label=t("email_weekly_stats"),
            on_change=on_email_change,
        )

        # Notification settings — auto-persist on change so the master toggle and
        # sub-switches don't silently drop their value when the user navigates away.
        notification_sub_controls = ft.Column(spacing=SPACING_MD)

        def _persist(db_key: str, value: object) -> None:
            async def _do() -> None:
                try:
                    await db.set_setting(db_key, value)
                    await notification_service.reschedule_digests()
                except DatabaseError as ex:
                    self.snack.show(f"{t('failed')}: {ex}", COLORS["danger"])
            self.page.run_task(_do)

        def on_notifications_toggle(e: ft.ControlEvent) -> None:
            async def _toggle() -> None:
                if e.control.value:
                    result = await notification_service.request_permission()
                    if result == PermissionResult.DENIED:
                        e.control.value = False
                        self.snack.show(t("notification_permission_denied"), COLORS["danger"])
                        self.page.update()
                        return
                    self.snack.show(t("notification_permission_granted"))
                self.state.notifications_enabled = e.control.value
                notification_sub_controls.visible = e.control.value
                try:
                    try:
                        await db.set_setting("notifications_enabled", e.control.value)
                        await notification_service.reschedule_digests()
                    except (DatabaseError, TypeError, ValueError, OSError, RuntimeError) as ex:
                        # Don't let a failed reschedule revert the user's UI choice —
                        # visibility + DB write must stick even if the alarm scheduling
                        # extension throws. Log and surface as a snack.
                        logger.exception("notifications toggle: reschedule failed")
                        self.snack.show(f"{t('failed')}: {ex}", COLORS["danger"])
                finally:
                    self.page.update()
            self.page.run_task(_toggle)

        def on_send_overdue_now(e: ft.ControlEvent) -> None:
            backend = notification_service.backend
            if backend == NotificationBackend.NONE:
                self.snack.show(f"{t('test_notification_unavailable')} (backend: none)", COLORS["danger"])
                return

            async def _send() -> None:
                try:
                    sent = await notification_service.send_overdue_digest_now()
                    if sent:
                        self.snack.show(t("overdue_digest_sent"))
                    else:
                        self.snack.show(t("no_overdue_tasks"))
                except (OSError, RuntimeError, ValueError) as ex:
                    self.snack.show(f"Error: {ex}", COLORS["danger"])
            self.page.run_task(_send)

        notifications_switch = ft.Switch(
            value=self.state.notifications_enabled,
            on_change=on_notifications_toggle,
        )

        # Hour options for digest time pickers (06:00 - 22:00)
        hour_options = [ft.dropdown.Option(key=str(h), text=f"{h:02d}:00") for h in range(6, 23)]

        def _make_digest_row(
            label_key: str, desc_key: str, enabled: bool, current_time: time,
            enabled_key: str, time_key: str,
        ) -> tuple:
            # DB key and AppState attribute name are intentionally the same here.
            def on_switch_change(e: ft.ControlEvent) -> None:
                setattr(self.state, enabled_key, e.control.value)
                _persist(enabled_key, e.control.value)

            def on_time_change(e: ft.ControlEvent) -> None:
                new_time = time(int(e.control.value), 0)
                setattr(self.state, time_key, new_time)
                _persist(time_key, new_time.strftime("%H:%M"))

            switch = ft.Switch(value=enabled, on_change=on_switch_change)
            dropdown = ft.Dropdown(
                options=hour_options,
                value=str(current_time.hour),
                width=100,
                dense=True,
                content_padding=ft.Padding.symmetric(horizontal=PADDING_MD, vertical=PADDING_SM),
                on_select=on_time_change,
            )
            row = ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(t(label_key), size=13),
                            ft.Text(t(desc_key), size=11, color=COLORS["done_text"]),
                        ],
                        spacing=SPACING_XS,
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
            "daily_digest_enabled", "daily_digest_time",
        )
        preview_row, preview_switch, preview_dropdown = _make_digest_row(
            "evening_preview", "evening_preview_desc",
            self.state.evening_preview_enabled, self.state.evening_preview_time,
            "evening_preview_enabled", "evening_preview_time",
        )
        overdue_row, overdue_switch, overdue_dropdown = _make_digest_row(
            "overdue_nudge", "overdue_nudge_desc",
            self.state.overdue_nudge_enabled, self.state.overdue_nudge_time,
            "overdue_nudge_enabled", "overdue_nudge_time",
        )

        notification_sub_controls.controls = [
            digest_row,
            preview_row,
            overdue_row,
            ft.Divider(height=SPACING_SM, color="transparent"),
            ft.TextButton(
                t("send_overdue_digest_now"),
                icon=ft.Icons.NOTIFICATIONS_ACTIVE,
                on_click=on_send_overdue_now,
            ),
        ]
        notification_sub_controls.visible = self.state.notifications_enabled

        def reset_defaults(e: ft.ControlEvent) -> None:
            slider.value = 15 // DURATION_SLIDER_STEP
            duration_label.value = format_duration(15)
            email_cb.value = False
            self.state.default_estimated_minutes = 15
            self.state.email_weekly_stats = False
            if self.tasks_view:
                self.tasks_view.pending_details["estimated_minutes"] = 15
                self.tasks_view._details_text.value = t("add_details")
            if get_language() != "en":
                self.state.language = "en"
                set_language("en")
                event_bus.emit(AppEvent.LANGUAGE_CHANGED)
            self.page.update()

            async def _persist_reset() -> None:
                try:
                    await db.set_setting("default_estimated_minutes", 15)
                    await db.set_setting("email_weekly_stats", False)
                    await db.set_setting("language", self.state.language)
                except DatabaseError as ex:
                    self.snack.show(f"{t('failed')}: {ex}", COLORS["danger"])
            self.page.run_task(_persist_reset)

        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(t("preferences"), weight="bold", size=16),
                    ft.Divider(height=SPACING_LG, color=COLORS["border"]),
                    ft.Text(t("default_estimated_time"), size=13),
                    ft.Row([ft.Icon(ft.Icons.TIMER, size=18), duration_label], spacing=SPACING_MD),
                    slider,
                    ft.Text(
                        t("time_range_hint"),
                        size=11,
                        color=COLORS["done_text"],
                    ),
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    ft.Text(t("notifications"), size=13),
                    email_cb,
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.NOTIFICATIONS, size=18),
                                    ft.Text(t("notifications_enabled"), size=13),
                                ],
                                spacing=SPACING_MD,
                            ),
                            notifications_switch,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    notification_sub_controls,
                    ft.Divider(height=SPACING_LG, color="transparent"),
                    ft.Row(
                        [
                            ft.TextButton(
                                t("reset_defaults"),
                                on_click=reset_defaults,
                                style=ft.ButtonStyle(color=COLORS["done_text"]),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=SPACING_MD,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_2XL,
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
                spacing=SPACING_SM,
            ),
            alignment=ft.Alignment(0, 0),
            padding=PADDING_LG,
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
                        spacing=SPACING_XS,
                        expand=True,
                    ),
                ],
                spacing=SPACING_LG,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_XL,
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
                        spacing=SPACING_XS,
                        expand=True,
                    ),
                ],
                spacing=SPACING_LG,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_XL,
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
                        spacing=SPACING_XS,
                        expand=True,
                    ),
                ],
                spacing=SPACING_LG,
            ),
            bgcolor=COLORS["card"],
            padding=PADDING_XL,
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
                ft.Divider(height=SPACING_LG, color=COLORS["border"]),
                account_age_card,
                tasks_completed_card,
                most_active_card,
                ft.Divider(height=SPACING_2XL, color="transparent"),
                preferences_section,
                ft.Divider(height=SPACING_2XL, color="transparent"),
                data_management_section,
                ft.Divider(height=SPACING_2XL, color="transparent"),
                reset_btn_container,
            ],
            spacing=SPACING_MD,
        )