__requirements__ = ["pyperclip"]

import json
import asyncio
import os
import platform
import subprocess
from fastapi import WebSocket, WebSocketDisconnect
from mars.core.websocket.registry import mars_ws_module, ws_endpoint, ws_registry

import pyperclip

@mars_ws_module(
    name="Clipboard Sync",
    prefix="/clipboard",
    compatibility=["windows", "linux"],
    requires_tools=["xclip", "xsel", "wl_clipboard"]
)
class ClipboardSyncModule:
    
    def __init__(self):
        self.os_system = platform.system()
        if self.os_system != "Linux":
            try:
                pyperclip.paste()
            except pyperclip.PyperclipException:
                raise RuntimeError("Clipboard mechanism not found.")

    def _paste(self):
        """Cross-platform paste using environment provided by Daemon."""
        if self.os_system != "Linux":
            return pyperclip.paste()
            
        # Try Wayland
        if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_RUNTIME_DIR"):
            try:
                return subprocess.check_output(["wl-paste", "--no-newline"], stderr=subprocess.DEVNULL, text=True)
            except Exception:
                pass

        # Try X11
        if os.environ.get("DISPLAY"):
            try:
                return subprocess.check_output(["xclip", "-selection", "clipboard", "-o"], stderr=subprocess.DEVNULL, text=True)
            except Exception:
                pass

        return pyperclip.paste()

    def _copy(self, text):
        """Cross-platform copy using environment provided by Daemon."""
        if self.os_system != "Linux":
            pyperclip.copy(text)
            return
            
        # Try Wayland
        if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_RUNTIME_DIR"):
            try:
                subprocess.run(["wl-copy"], input=text, text=True, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

        # Try X11
        if os.environ.get("DISPLAY"):
            try:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

        pyperclip.copy(text)

    @ws_endpoint(path="/stream")
    async def sync_clipboard(self, websocket: WebSocket):
        """Synchronize clipboard contents with the connected client."""

        await websocket.accept()
        print("[Clipboard] Client connected.")

        last_clipboard = self._paste()

        async def send_updates_to_client():
            nonlocal last_clipboard
            try:
                while True:
                    current_clipboard = self._paste()
                    if current_clipboard != last_clipboard:
                        last_clipboard = current_clipboard
                        await websocket.send_text(json.dumps({
                            "action": "update",
                            "text": current_clipboard
                        }))
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass

        async def receive_updates_from_client():
            nonlocal last_clipboard
            try:
                while True:
                    data = await websocket.receive_text()
                    payload = json.loads(data)
                    
                    if payload.get("action") == "update":
                        new_text = payload.get("text", "")
                        last_clipboard = new_text 
                        self._copy(new_text)
            except (WebSocketDisconnect, json.JSONDecodeError, asyncio.CancelledError):
                pass

        task1 = asyncio.create_task(send_updates_to_client())
        task2 = asyncio.create_task(receive_updates_from_client())

        try:
            done, pending = await asyncio.wait(
                [task1, task2],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
        except WebSocketDisconnect:
            print("[Clipboard] Client disconnected.")

ws_registry.register(ClipboardSyncModule)