__requirements__ = ["PyAudioWPatch", "pyaudio"]

import os
import json
import asyncio
import platform
from fastapi import WebSocket, WebSocketDisconnect
from mars.core.websocket.registry import mars_ws_module, ws_endpoint, ws_registry

if platform.system() == "Windows":
    from .input_windows import WindowsInputInjector as InputInjector
else:
    from .input_linux import LinuxInputInjector as InputInjector
    
try:
    import pyaudiowpatch as pyaudio
except ImportError:
    try:
        import pyaudio
    except ImportError:
        pyaudio = None

@mars_ws_module(
    name="Remote Control", 
    prefix="/remote", 
    compatibility=["windows", "linux"],
    requires_tools=["ffmpeg"]
)
class RemoteControlModule:
    
    def __init__(self):
        self.injector = InputInjector()
        self.os_system = platform.system()
        self.show_cursor = True
        self.quality_mode = "optimal"
        
        self.video_queue = asyncio.Queue(maxsize=100)
        self.switch_event = asyncio.Event()
        self.active_process = None
        self.audio_websockets = set()
        self.audio_task = None

    def _get_ffmpeg_cmd(self, show_cursor: bool, quality_mode: str):
        draw = "1" if show_cursor else "0"
        width, height = self.injector.get_screen_size()
        
        if self.os_system == "Windows":
            input_format = [
                "-f", "gdigrab", "-framerate", "30", "-draw_mouse", draw,
                "-offset_x", "0", "-offset_y", "0", "-video_size", f"{width}x{height}",
                "-i", "desktop"
            ]
        else:
            display = os.environ.get('DISPLAY', ':0.0')
            input_format = [
                "-f", "x11grab", "-framerate", "30", "-draw_mouse", draw,
                "-video_size", f"{width}x{height}", "-i", f"{display}+0,0"
            ]

        crf = "28"
        scale = "iw:ih"

        if quality_mode == "best":
            crf = "20"
        elif quality_mode == "optimal":
            crf = "28"
            scale = "iw*0.8:ih*0.8"
        elif quality_mode == "performance":
            crf = "35"
            scale = "iw*0.6:ih*0.6"

        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            *input_format,
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-crf", crf, "-vf", f"scale={scale}",
            "-pix_fmt", "yuv420p", "-f", "h264", "-"
        ]

    async def _ffmpeg_worker(self, show_cursor: bool, quality_mode: str, is_transition=False):
        """Run FFmpeg and push encoded chunks into the video queue."""
        cmd = self._get_ffmpeg_cmd(show_cursor, quality_mode) 
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        if is_transition:
            first_chunk = await process.stdout.read(4096)
            if first_chunk:
                if self.active_process:
                    self.active_process.terminate()
                self.active_process = process
                await self.video_queue.put(first_chunk)
        else:
            self.active_process = process

        try:
            while True:
                chunk = await process.stdout.read(8192)
                if not chunk: break
                if self.active_process == process:
                    await self.video_queue.put(chunk)
                else:
                    break
        finally:
            if process.returncode is None:
                process.terminate()

    async def _windows_audio_broadcaster(self):
        """Capture system audio on Windows using WASAPI loopback (PyAudioWPatch).
        No Stereo Mix needed — captures directly from the default output device.
        Resamples to s16le mono 22050Hz to match the client's ffplay format.
        """
        import audioop
        
        p = pyaudio.PyAudio()
        try:
            # Find WASAPI host API
            wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_output_idx = wasapi_info["defaultOutputDevice"]
            default_speakers = p.get_device_info_by_index(default_output_idx)
            
            # Find the loopback device that corresponds to the default speakers
            # PyAudioWPatch exposes loopback devices with isLoopbackDevice=True
            loopback_device = None
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if dev.get("isLoopbackDevice") and default_speakers["name"] in dev["name"]:
                    loopback_device = dev
                    break
            
            if loopback_device is None:
                print(f"[Audio] No WASAPI loopback device found for '{default_speakers['name']}'")
                return
            
            native_rate = int(loopback_device["defaultSampleRate"])
            native_channels = loopback_device["maxInputChannels"]
            
            CHUNK = 1024
            stream = p.open(
                format=pyaudio.paInt16,
                channels=native_channels,
                rate=native_rate,
                input=True,
                input_device_index=loopback_device["index"],
                frames_per_buffer=CHUNK,
            )
            
            TARGET_RATE = 22050
            loop = asyncio.get_event_loop()
            
            try:
                while True:
                    # Read audio in a thread to avoid blocking the event loop
                    raw = await loop.run_in_executor(
                        None, lambda: stream.read(CHUNK, exception_on_overflow=False)
                    )
                    if not raw:
                        break
                    
                    # Convert to mono if stereo
                    data = raw
                    if native_channels > 1:
                        data = audioop.tomono(data, 2, 1, 1)
                    
                    # Resample to 22050Hz if needed
                    if native_rate != TARGET_RATE:
                        data, _ = audioop.ratecv(data, 2, 1, native_rate, TARGET_RATE, None)
                    
                    
                    if not self.audio_websockets:
                        continue
                    
                    dead = set()
                    for ws in self.audio_websockets:
                        try:
                            await ws.send_bytes(data)
                        except RuntimeError:
                            dead.add(ws)
                    for ws in dead:
                        self.audio_websockets.discard(ws)
                        
            except asyncio.CancelledError:
                pass
            finally:
                stream.close()
                
        except Exception as e:
            print(f"[Audio] WASAPI loopback error: {e}")
        finally:
            p.terminate()

    async def _audio_broadcaster(self):
        """Continuously read audio and broadcast it only to connected listeners."""
        env = os.environ.copy()
        audio_cmd = []

        if self.os_system == "Linux":
            import pwd
            import subprocess
            try:
                real_user = os.environ.get("SUDO_USER") or pwd.getpwuid(1000).pw_name
                real_uid = pwd.getpwnam(real_user).pw_uid
                
                env_xdg = f"XDG_RUNTIME_DIR=/run/user/{real_uid}"
                env_pulse = f"PULSE_SERVER=unix:/run/user/{real_uid}/pulse/native"
                
                monitor_device = "default.monitor" 
                try:
                    cmd_pactl = ["sudo", "-u", real_user, "env", env_xdg, env_pulse, "pactl", "get-default-sink"]
                    default_sink = subprocess.check_output(cmd_pactl).decode("utf-8").strip()
                    monitor_device = f"{default_sink}.monitor"
                except Exception:
                    pass

                print(f"[Remote Control] Configuring audio through parec. Monitor: {monitor_device}")
                audio_cmd = [
                    "sudo", "-u", real_user, "env", env_xdg, env_pulse, 
                    "parec", 
                    "--format=s16le", 
                    "--rate=22050", 
                    "--channels=1", 
                    "--device", monitor_device
                ]
            except Exception as e:
                print(f"[Audio error] {e}")
                
        elif self.os_system == "Windows":
            # Use PyAudio WASAPI loopback — captures system audio directly, no Stereo Mix needed
            if pyaudio is None:
                print("[Audio] PyAudioWPatch not installed. Install with: pip install PyAudioWPatch")
                return
            await self._windows_audio_broadcaster()
            return

        if not audio_cmd: return

        try:
            process = await asyncio.create_subprocess_exec(
                *audio_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env
            )
            
            while True:
                data = await process.stdout.read(2048)
                if not data:
                    break
                
                if not self.audio_websockets:
                    continue 

                dead_sockets = set()
                for ws in self.audio_websockets:
                    try:
                        await ws.send_bytes(data)
                    except RuntimeError:
                        dead_sockets.add(ws)
                
                for ws in dead_sockets:
                    self.audio_websockets.discard(ws)
                    
        except asyncio.CancelledError:
            pass
        finally:
            if 'process' in locals() and process.returncode is None:
                process.terminate()

    async def _stream_manager(self):
        """Manage seamless video stream switching."""
        asyncio.create_task(self._ffmpeg_worker(self.show_cursor, self.quality_mode))
        
        while True:
            await self.switch_event.wait()
            self.switch_event.clear()
            
            asyncio.create_task(self._ffmpeg_worker(self.show_cursor, self.quality_mode, is_transition=True))

    async def _receive_commands(self, websocket: WebSocket):
        """Receive and execute remote control commands from the client."""
        screen_width, screen_height = self.injector.get_screen_size()
        
        try:
            while True:
                data_str = await websocket.receive_text()
                command = json.loads(data_str)
                action = command.get("action")

                if action == "set_quality":
                    new_mode = command.get("mode")
                    if new_mode in ["best", "optimal", "performance"] and new_mode != self.quality_mode:
                        self.quality_mode = new_mode
                        self.switch_event.set() 
                    continue

                if action == "toggle_cursor":
                    new_state = command.get("state", True)
                    if new_state != self.show_cursor:
                        self.show_cursor = new_state
                        self.switch_event.set()
                    continue

                abs_x, abs_y = None, None
                if "x" in command and "y" in command:
                    abs_x = int(command["x"] * screen_width)
                    abs_y = int(command["y"] * screen_height)
                if action == "mouse_move" and abs_x is not None:
                    self.injector.mouse_move(abs_x, abs_y)
                    
                elif action == "mouse_click":
                    button = command.get("button", "left")
                    state = command.get("state", "down")
                    self.injector.mouse_click(button, state == "down")
                    
                elif action == "scroll":
                    clicks = command.get("clicks", 0)
                    self.injector.mouse_scroll(clicks)
                    
                elif action == "scancode":
                    code = command.get("code", 0)
                    state = command.get("state", "down")
                    self.injector.inject_scancode(code, state == "down")
                    
                elif action == "unicode":
                    char = command.get("char", "")
                    self.injector.inject_unicode(char)

        except (WebSocketDisconnect, asyncio.CancelledError, json.JSONDecodeError):
            pass

    @ws_endpoint(path="/stream")
    async def stream_and_control(self, websocket: WebSocket):
        """Stream the desktop video and accept control commands over WebSocket."""
        await websocket.accept()
        
        if not self.audio_task or self.audio_task.done():
            self.audio_task = asyncio.create_task(self._audio_broadcaster())

        while not self.video_queue.empty(): self.video_queue.get_nowait()
        self.is_running = True 

        manager_task = asyncio.create_task(self._stream_manager())
        control_task = asyncio.create_task(self._receive_commands(websocket))
        
        try:
            while self.is_running:
                chunk = await self.video_queue.get()
                if self.is_running: 
                    await websocket.send_bytes(chunk)
        except (WebSocketDisconnect, asyncio.CancelledError, RuntimeError):
            pass
        finally:
            self.is_running = False 
            manager_task.cancel()
            control_task.cancel()
            if self.active_process: self.active_process.terminate()
            
            if self.audio_task: self.audio_task.cancel()
            print("[Remote Control] Connection closed")

    @ws_endpoint(path="/audio")
    async def audio_stream(self, websocket: WebSocket):
        """Stream audio only over WebSocket."""
        await websocket.accept()
        print("[Remote Control] Client connected to the audio channel.")
        
        self.audio_websockets.add(websocket)
        
        if not self.audio_task or self.audio_task.done():
            self.audio_task = asyncio.create_task(self._audio_broadcaster())

        try:
            while True:
                await websocket.receive_text()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            self.audio_websockets.discard(websocket)

ws_registry.register(RemoteControlModule)