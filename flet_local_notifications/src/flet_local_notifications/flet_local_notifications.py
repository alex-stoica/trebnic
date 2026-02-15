import flet as ft
from typing import Optional


@ft.control("flet_local_notifications")
class FletLocalNotifications(ft.Service):
    on_notification_tap: Optional[ft.ControlEventHandler["FletLocalNotifications"]] = None

    def before_update(self):
        super().before_update()

    async def show_notification(self, notification_id: int, title: str, body: str, payload: str = "") -> str:
        result = await self._invoke_method(
            method_name="show_notification",
            arguments={"id": notification_id, "title": title, "body": body, "payload": payload},
        )
        return str(result) if result is not None else "error:no_response"

    async def request_permissions(self) -> str:
        result = await self._invoke_method(
            method_name="request_permissions",
        )
        return str(result) if result is not None else "error:no_response"

    async def check_permissions(self) -> str:
        result = await self._invoke_method(
            method_name="check_permissions",
        )
        return str(result) if result is not None else "error:no_response"
