import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
import flet as ft
from flet_android_background import BackgroundTask

from services.remote_commands import RemoteCommands


class ChatGPTBridge:
    def __init__(self, page, api, is_locked):
        self.page = page
        self.commands = RemoteCommands(api, is_locked)
        self.runner = BackgroundTask()
        self.path = Path(os.environ.get("FLET_APP_STORAGE_DATA") or ".") / ".chatgpt-bridge.json"
        self.status = "Disconnected"
        self.url = ""
        self.token = ""
        self._desktop_task = None
        if self.path.exists():
            try:
                config = json.loads(self.path.read_text(encoding="utf-8"))
                self.url, self.token = config["url"], config["token"]
            except (ValueError, KeyError, OSError):
                pass

    async def start(self, url, token):
        parsed = urlparse(url.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("Use the HTTPS address of your private Trebnic bridge")
        if not token.strip():
            raise ValueError("Enter the device access token")
        await self.stop()
        self.url, self.token = url.strip().rstrip("/"), token.strip()
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(self.url + "/api/device", headers=self.headers,
                                         json={"action": "ping"})
            response.raise_for_status()
            if response.json().get("service") != "trebnic-bridge":
                raise ValueError("This address is not a Trebnic bridge")
        if self.page.platform == ft.PagePlatform.ANDROID:
            if not await self.runner.service.request_permissions():
                raise ValueError("Allow notifications to keep Trebnic connected")
            await self.runner.start(self.listen, notification_id=7301,
                                    title="Trebnic · ChatGPT connected",
                                    body="Receiving task commands. Tap Stop to disconnect.",
                                    enable_cpu_lock=True, cpu_lock_timeout=3600)
        else:
            self._desktop_task = asyncio.create_task(self.listen())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"url": self.url, "token": self.token}), encoding="utf-8")
        self.status = "Connected for this session (up to 1 hour)"

    @property
    def headers(self):
        return {"OAI-Sites-Authorization": "Bearer " + self.token}

    async def stop(self):
        await self.runner.stop()
        if self._desktop_task:
            self._desktop_task.cancel()
            await asyncio.gather(self._desktop_task, return_exceptions=True)
            self._desktop_task = None
        self.status = "Disconnected"

    async def close(self):
        await self.runner.on_session_close()
        if self._desktop_task:
            self._desktop_task.cancel()
            await asyncio.gather(self._desktop_task, return_exceptions=True)

    async def listen(self):
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                while True:
                    try:
                        response = await client.post(self.url + "/api/device", headers=self.headers,
                                                     json={"action": "poll"})
                        response.raise_for_status()
                        for command in response.json().get("commands", []):
                            result = await self.commands.execute(command)
                            reply = await client.post(self.url + "/api/device", headers=self.headers,
                                                      json={"action": "result", "id": command["id"], "result": result})
                            reply.raise_for_status()
                        self.status = "Connected for this session (up to 1 hour)"
                    except (httpx.HTTPError, ValueError, KeyError):
                        self.status = "Connection interrupted; retrying"
                    await asyncio.sleep(3)
        finally:
            self.status = "Disconnected"

    def show(self, event=None):
        url = ft.TextField(label="Bridge address", value=self.url, keyboard_type=ft.KeyboardType.URL)
        token = ft.TextField(label="Device access token", value=self.token, password=True)
        status = ft.Text(self.status)
        async def connect(event):
            try:
                await self.start(url.value, token.value)
                self.page.pop_dialog()
            except Exception as exc:
                status.value = "Could not connect. Check the address, token and notification permission."
            self.page.update()
        async def disconnect(event):
            await self.stop()
            status.value = self.status
            self.page.update()
        dialog = ft.AlertDialog(title=ft.Text("ChatGPT connection"),
            content=ft.Column([ft.Text("Keep Trebnic available while using ChatGPT. Reconnect after closing the app or when the session expires."), url, token, status], tight=True, width=400),
            actions=[ft.TextButton("Disconnect", on_click=disconnect),
                     ft.TextButton("Connect", on_click=connect),
                     ft.TextButton("Close", on_click=lambda e: self.page.pop_dialog())])
        self.page.show_dialog(dialog)
