__requirements__ = ["PyAudioWPatch", "pyaudio"]

import os
import json
import asyncio
import platform
import logging
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

logger = logging.getLogger("MARS.RemoteControl")

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
        self.audio_websockets = set()
        self.audio_task = None

    def _get_ffmpeg_cmd(self, width, height, draw, crf, scale):
        if self.os_system == "Windows":
            return [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "gdigrab", "-framerate", "30", "-draw_mouse", draw,
                "-offset_x", "0", "-offset_y", "0", "-video_size", f"{width}x{height}",
                "-i", "desktop",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-crf", crf, "-vf", f"scale={scale}",
                "-pix_fmt", "yuv420p", "-f", "h264", "-"
            ]
        else:
            # On Linux, the server is already running in the user session via sudo from Daemon
            display = os.environ.get('DISPLAY', ':0')
            return [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "x11grab", "-framerate", "30", "-draw_mouse", draw,
                "-video_size", f"{width}x{height}", "-i", f"{display}+0,0",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-crf", crf, "-vf", f"scale={scale}",
                "-pix_fmt", "yuv420p", "-f", "h264", "-"
            ]

    async def _ffmpeg_worker(self, video_queue, options, process_ref):
        width, height = self.injector.get_screen_size()
        draw = "1" if options['show_cursor'] else "0"
        crf = "28"
        scale = "iw:ih"
        if options['quality'] == "best": crf = "20"
        elif options['quality'] == "optimal": scale = "iw*0.8:ih*0.8"
        elif options['quality'] == "performance": crf = "35"; scale = "iw*0.6:ih*0.6"

        cmd = self._get_ffmpeg_cmd(width, height, draw, crf, scale)
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy()
            )
            process_ref[0] = process
            while True:
                data = await process.stdout.read(8192)
                if not data:
                    err = await process.stderr.read()
                    if err: logger.error(f"FFmpeg stderr: {err.decode().strip()}")
                    break
                await video_queue.put(data)
        except Exception as e:
            logger.error(f"FFmpeg worker failed: {e}")
        finally:
            if process is not None and process.returncode is None:
                try: process.terminate()
                except: pass

    @ws_endpoint(path="/stream")
    async def stream_and_control(self, websocket: WebSocket):
        await websocket.accept()
        
        video_queue = asyncio.Queue(maxsize=50)
        options = {"show_cursor": True, "quality": "optimal"}
        current_process_ref = [None]
        worker_task_ref = [None]
        
        async def start_worker():
            if worker_task_ref[0]: worker_task_ref[0].cancel()
            if current_process_ref[0]:
                try: current_process_ref[0].terminate()
                except: pass
            while not video_queue.empty(): video_queue.get_nowait()
            worker_task_ref[0] = asyncio.create_task(self._ffmpeg_worker(video_queue, options, current_process_ref))

        await start_worker()

        try:
            while True:
                data_task = asyncio.create_task(websocket.receive_text())
                video_task = asyncio.create_task(video_queue.get())
                
                done, pending = await asyncio.wait([data_task, video_task], return_when=asyncio.FIRST_COMPLETED)
                
                if video_task in done:
                    await websocket.send_bytes(video_task.result())
                
                if data_task in done:
                    cmd = json.loads(data_task.result())
                    action = cmd.get("action")
                    if action == "set_quality":
                        options['quality'] = cmd.get("mode", "optimal")
                        await start_worker()
                    elif action == "toggle_cursor":
                        options['show_cursor'] = cmd.get("state", True)
                        await start_worker()
                    else:
                        screen_width, screen_height = self.injector.get_screen_size()
                        x, y = cmd.get("x"), cmd.get("y")
                        if x is not None and y is not None:
                            self.injector.mouse_move(int(x * screen_width), int(y * screen_height))
                        if action == "mouse_click": self.injector.mouse_click(cmd.get("button", "left"), cmd.get("state") == "down")
                        elif action == "scroll": self.injector.mouse_scroll(cmd.get("clicks", 0))
                        elif action == "scancode": self.injector.inject_scancode(cmd.get("code", 0), cmd.get("state") == "down")
                        elif action == "unicode": self.injector.inject_unicode(cmd.get("char", ""))
                
                for p in pending: p.cancel()
        except: pass
        finally:
            if worker_task_ref[0]: worker_task_ref[0].cancel()
            if current_process_ref[0]:
                try: current_process_ref[0].terminate()
                except: pass

    @ws_endpoint(path="/audio")
    async def audio_stream(self, websocket: WebSocket):
        await websocket.accept()
        self.audio_websockets.add(websocket)
        if not self.audio_task or self.audio_task.done():
            self.audio_task = asyncio.create_task(self._audio_broadcaster())
        try:
            while True: await websocket.receive_text()
        except: pass
        finally: self.audio_websockets.discard(websocket)

    async def _audio_broadcaster(self):
        if self.os_system == "Linux":
            try:
                user = os.environ.get("MARS_SESSION_USER")
                cmd = ["parec", "--format=s16le", "--rate=22050", "--channels=1"]
                if user:
                    cmd = ["sudo", "-u", user, "env", f"XDG_RUNTIME_DIR={os.environ.get('XDG_RUNTIME_DIR')}", "parec", "--format=s16le", "--rate=22050", "--channels=1"]
                
                process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
                while True:
                    data = await process.stdout.read(2048)
                    if not data: break
                    for ws in list(self.audio_websockets):
                        try: await ws.send_bytes(data)
                        except: self.audio_websockets.discard(ws)
            except Exception as e:
                logger.error(f"Linux audio failed: {e}")
        elif self.os_system == "Windows":
            if not pyaudio: return
            p = pyaudio.PyAudio()
            try:
                default_out = p.get_default_output_device_info()
                target_name = default_out.get("name")
                loopback_device = None
                
                for i in range(p.get_device_count()):
                    info = p.get_device_info_by_index(i)
                    if info.get("isLoopbackDevice") and target_name in info.get("name"):
                        loopback_device = info
                        break
                
                if not loopback_device:
                    for i in range(p.get_device_count()):
                        info = p.get_device_info_by_index(i)
                        if info.get("isLoopbackDevice"):
                            loopback_device = info
                            break
                
                if not loopback_device: return

                native_rate = int(loopback_device.get("defaultSampleRate", 48000))
                native_channels = int(loopback_device.get("maxInputChannels", 2))
                
                stream = p.open(
                    format=pyaudio.paInt16, 
                    channels=native_channels, 
                    rate=native_rate, 
                    input=True, 
                    input_device_index=loopback_device["index"]
                )
                
                while True:
                    raw_data = await asyncio.get_event_loop().run_in_executor(None, lambda: stream.read(1024, exception_on_overflow=False))
                    if not raw_data: continue

                    # Manual Downsampling: Stereo to Mono and Half Sample Rate
                    frame_size = native_channels * 2
                    processed_data = bytearray()
                    for i in range(0, len(raw_data), frame_size * 2):
                        processed_data.extend(raw_data[i:i+2])
                    
                    data = bytes(processed_data)
                    for ws in list(self.audio_websockets):
                        try: await ws.send_bytes(data)
                        except: self.audio_websockets.discard(ws)
            except Exception as e:
                logger.error(f"Windows audio broadcast error: {e}")
            finally:
                p.terminate()

ws_registry.register(RemoteControlModule)