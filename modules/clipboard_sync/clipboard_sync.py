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

    def _get_linux_session(self):
        """Detect the active user session for Linux breakthrough."""
        import pwd
        try:
            # Same detection as in remote_control and audio_stream
            real_user = os.environ.get("SUDO_USER") or pwd.getpwuid(1000).pw_name
            user_info = pwd.getpwnam(real_user)
            real_uid = user_info.pw_uid
            real_home = user_info.pw_dir
            env_xdg = f"XDG_RUNTIME_DIR=/run/user/{real_uid}"
            
            is_wayland = os.path.exists(os.path.join(env_xdg, "wayland-0"))
            
            env = {"USER": real_user, "XDG_RUNTIME_DIR": env_xdg}
            if is_wayland:
                env["WAYLAND_DISPLAY"] = "wayland-0"
            else:
                env["DISPLAY"] = os.environ.get('DISPLAY') or ':0'
                env["XAUTHORITY"] = os.path.join(real_home, ".Xauthority")
            return real_user, env
        except Exception:
            return None, {}

    def _paste(self):
        """Cross-platform paste with Linux session breakthrough."""
        if self.os_system != "Linux":
            return pyperclip.paste()
            
        user, env = self._get_linux_session()
        if not user:
            return pyperclip.paste()

        # Try Wayland
        if "WAYLAND_DISPLAY" in env:
            try:
                cmd = ["sudo", "-u", user, "env", f"XDG_RUNTIME_DIR={env['XDG_RUNTIME_DIR']}", "wl-paste", "--no-newline"]
                return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
            except Exception:
                pass

        # Try X11
        try:
            display = env.get("DISPLAY", ":0")
            xauth = env.get("XAUTHORITY", "")
            cmd = ["sudo", "-u", user, "env", f"DISPLAY={display}", f"XAUTHORITY={xauth}", "xclip", "-selection", "clipboard", "-o"]
            return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        except Exception:
            pass

        return pyperclip.paste()

    def _copy(self, text):
        """Cross-platform copy with Linux session breakthrough."""
        if self.os_system != "Linux":
            pyperclip.copy(text)
            return
            
        user, env = self._get_linux_session()
        if not user:
            pyperclip.copy(text)
            return

        # Try Wayland
        if "WAYLAND_DISPLAY" in env:
            try:
                cmd = ["sudo", "-u", user, "env", f"XDG_RUNTIME_DIR={env['XDG_RUNTIME_DIR']}", "wl-copy"]
                subprocess.run(cmd, input=text, text=True, stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass

        # Try X11
        try:
            display = env.get("DISPLAY", ":0")
            xauth = env.get("XAUTHORITY", "")
            cmd = ["sudo", "-u", user, "env", f"DISPLAY={display}", f"XAUTHORITY={xauth}", "xclip", "-selection", "clipboard"]
            subprocess.run(cmd, input=text, text=True, stderr=subprocess.DEVNULL)
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