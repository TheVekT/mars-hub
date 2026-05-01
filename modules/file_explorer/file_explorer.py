__requirements__ = []

import os
import io
import json
import shutil
import zipfile
import asyncio
import platform
import ctypes
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect
from mars.core.websocket.registry import mars_ws_module, ws_endpoint, ws_registry

@mars_ws_module(name="File Explorer", prefix="/explorer", compatibility=["windows", "linux"])
class FileExplorerModule:
    
    def __init__(self):
        self.os_type = platform.system()

    def _is_hidden(self, path: str) -> bool:
        name = os.path.basename(path)
        if self.os_type != "Windows":
            return name.startswith('.')
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
            return attrs != -1 and (attrs & 2) 
        except:
            return False

    def _get_permissions(self, path: str) -> Dict[str, bool]:
        return {
            "read": os.access(path, os.R_OK),
            "write": os.access(path, os.W_OK),
            "execute": os.access(path, os.X_OK)
        }
        
    def _extract_zip_to_folder(self, zip_bytes: bytes, dest_folder: str):
        """Extract a ZIP archive from memory into a folder."""
        memory_file = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(memory_file, 'r') as zf:
            zf.extractall(dest_folder)

    @ws_endpoint(path="/stream")
    async def manager_session(self, websocket: WebSocket):
        """Handle the file manager WebSocket session."""
        await websocket.accept()
        
        pending_upload_meta = None 

        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    print("[File Explorer] Connection closed by client.")
                    break
                if "text" in message:
                    data = json.loads(message["text"])
                    action = data.get("action")
                    payload = data.get("payload", {})

                    try:
                        if action == "list_dir":
                            path = payload.get("path") or os.path.expanduser("~")
                            show_hidden = payload.get("show_hidden", False)
                            
                            if not os.path.exists(path):
                                raise FileNotFoundError(f"Path {path} was not found")

                            items = []
                            for entry in os.scandir(path):
                                is_hidden = self._is_hidden(entry.path)
                                if is_hidden and not show_hidden:
                                    continue
                                    
                                stats = entry.stat()
                                items.append({
                                    "name": entry.name,
                                    "path": entry.path,
                                    "is_dir": entry.is_dir(),
                                    "size": stats.st_size,
                                    "mtime": stats.st_mtime,
                                    "hidden": is_hidden,
                                    "permissions": self._get_permissions(entry.path)
                                })
                            
                            await websocket.send_text(json.dumps({
                                "status": "ok", "action": "list_dir", "path": path, "items": items
                            }))

                        elif action == "delete":
                            paths = payload.get("paths", [])
                            for p in paths:
                                if not os.access(os.path.dirname(p), os.W_OK):
                                    raise PermissionError(f"No permission to delete {p}")
                                if os.path.isdir(p):
                                    shutil.rmtree(p)
                                else:
                                    os.remove(p)
                            await websocket.send_text(json.dumps({"status": "ok", "action": "delete"}))

                        elif action == "transfer_local":
                            source_paths = payload.get("sources", [])
                            dest_folder = payload.get("dest_folder")
                            mode = payload.get("mode", "copy") 

                            for src in source_paths:
                                name = os.path.basename(src)
                                target = os.path.join(dest_folder, name)
                                if mode == "move":
                                    shutil.move(src, target)
                                else:
                                    if os.path.isdir(src):
                                        shutil.copytree(src, target)
                                    else:
                                        shutil.copy2(src, target)
                            await websocket.send_text(json.dumps({"status": "ok", "action": "transfer_local"}))

                        elif action == "download_request":
                            path = payload.get("path")
                            item_name = os.path.basename(path)
                            
                            if os.path.isdir(path):
                                mem = io.BytesIO()
                                with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
                                    for root, _, files in os.walk(path):
                                        for f in files:
                                            zf.write(os.path.join(root, f), 
                                                     os.path.relpath(os.path.join(root, f), os.path.dirname(path)))
                                data_to_send = mem.getvalue()
                                is_zip = True
                            else:
                                with open(path, "rb") as f:
                                    data_to_send = f.read()
                                is_zip = False

                            await websocket.send_text(json.dumps({
                                "status": "incoming_binary", "name": item_name, "is_zip": is_zip
                            }))
                            await websocket.send_bytes(data_to_send)

                        elif action == "upload_request":
                            pending_upload_meta = payload
                            await websocket.send_text(json.dumps({"status": "ready_for_bytes"}))

                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "status": "error", "message": str(e)
                        }))
                        
                elif "bytes" in message:
                    if not pending_upload_meta:
                        print("[File Explorer] Received bytes without metadata. Ignoring.")
                        continue
                        
                    file_bytes = message["bytes"]
                    dest_folder = pending_upload_meta.get("dest_folder")
                    name = pending_upload_meta.get("name")
                    is_zip = pending_upload_meta.get("is_zip", False)
                    
                    target_path = os.path.join(dest_folder, name)
                    
                    try:
                        if not os.access(dest_folder, os.W_OK):
                            raise PermissionError(f"No write permission for {dest_folder}")
                            
                        if is_zip:
                            self._extract_zip_to_folder(file_bytes, dest_folder)
                        else:
                            with open(target_path, "wb") as f:
                                f.write(file_bytes)
                                
                        await websocket.send_text(json.dumps({
                            "status": "ok", 
                            "action": "upload_success",
                            "message": f"Uploaded successfully: {name}"
                        }))
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "status": "error", "message": f"Write error: {e}"
                        }))
                    finally:
                        pending_upload_meta = None

        except WebSocketDisconnect:
            pass

ws_registry.register(FileExplorerModule)