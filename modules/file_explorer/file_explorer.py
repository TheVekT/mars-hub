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
        
    def _extract_zip_to_folder(self, zip_bytes: bytes, dest_folder: str, overwrite: bool = False):
        """Extract a ZIP archive from memory into a folder."""
        memory_file = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(memory_file, 'r') as zf:
            if not overwrite:
                for name in zf.namelist():
                    target = os.path.join(dest_folder, name)
                    if os.path.exists(target) and not name.endswith('/'):
                        raise FileExistsError(name)
            zf.extractall(dest_folder)

    @ws_endpoint(path="/stream")
    async def manager_session(self, websocket: WebSocket):
        """Handle the file manager WebSocket session."""
        await websocket.accept()
        
        pending_upload_meta = None
        pending_upload_buffer = bytearray()
        pending_upload_expected = 0

        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
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
                            try:
                                entries = list(os.scandir(path))
                            except PermissionError:
                                raise PermissionError(f"No permission to read {path}")
                                
                            for entry in entries:
                                is_hidden = self._is_hidden(entry.path)
                                if is_hidden and not show_hidden:
                                    continue
                                try:
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
                                except (PermissionError, OSError):
                                    continue
                            
                            await websocket.send_text(json.dumps({
                                "status": "ok", "action": "list_dir", "path": path, "items": items
                            }))

                        elif action == "delete":
                            paths = payload.get("paths", [])
                            for p in paths:
                                if not os.path.exists(p):
                                    continue
                                if not os.access(os.path.dirname(p), os.W_OK):
                                    raise PermissionError(f"No permission to delete {p}")
                                if os.path.isdir(p):
                                    shutil.rmtree(p)
                                else:
                                    os.remove(p)
                            await websocket.send_text(json.dumps({"status": "ok", "action": "delete"}))

                        elif action == "rename":
                            path = payload.get("path")
                            new_name = payload.get("new_name")
                            if not path or not new_name:
                                raise ValueError("path and new_name are required")
                            parent = os.path.dirname(path)
                            new_path = os.path.join(parent, new_name)
                            if os.path.exists(new_path):
                                raise FileExistsError(f"{new_name} already exists")
                            os.rename(path, new_path)
                            await websocket.send_text(json.dumps({"status": "ok", "action": "rename"}))

                        elif action == "create_dir":
                            path = payload.get("path")
                            if not path:
                                raise ValueError("path is required")
                            os.makedirs(path, exist_ok=True)
                            await websocket.send_text(json.dumps({"status": "ok", "action": "create_dir"}))

                        elif action == "transfer_local":
                            source_paths = payload.get("sources", [])
                            dest_folder = payload.get("dest_folder")
                            mode = payload.get("mode", "copy")
                            overwrite = payload.get("overwrite", False)

                            for src in source_paths:
                                name = os.path.basename(src)
                                target = os.path.join(dest_folder, name)
                                
                                if os.path.exists(target) and not overwrite:
                                    await websocket.send_text(json.dumps({
                                        "status": "exists", 
                                        "action": "transfer_local",
                                        "name": name, 
                                        "path": target
                                    }))
                                    return
                                
                                if mode == "move":
                                    if os.path.exists(target):
                                        if os.path.isdir(target):
                                            shutil.rmtree(target)
                                        else:
                                            os.remove(target)
                                    shutil.move(src, target)
                                else:
                                    if os.path.exists(target):
                                        if os.path.isdir(target):
                                            shutil.rmtree(target)
                                        else:
                                            os.remove(target)
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
                                            full = os.path.join(root, f)
                                            zf.write(full, os.path.relpath(full, os.path.dirname(path)))
                                data_to_send = mem.getvalue()
                                is_zip = True
                            else:
                                with open(path, "rb") as f:
                                    data_to_send = f.read()
                                is_zip = False

                            total_size = len(data_to_send)
                            await websocket.send_text(json.dumps({
                                "status": "incoming_binary", 
                                "name": item_name, 
                                "is_zip": is_zip,
                                "total_size": total_size
                            }))
                            
                            # Send in chunks for progress tracking
                            CHUNK_SIZE = 64 * 1024  # 64KB
                            sent = 0
                            while sent < total_size:
                                chunk = data_to_send[sent:sent + CHUNK_SIZE]
                                await websocket.send_bytes(chunk)
                                sent += len(chunk)
                            
                            # Signal end of transfer
                            await websocket.send_text(json.dumps({
                                "status": "ok", "action": "download_complete"
                            }))

                        elif action == "upload_request":
                            pending_upload_meta = payload
                            pending_upload_expected = payload.get("total_size", 0)
                            pending_upload_buffer = bytearray()
                            await websocket.send_text(json.dumps({"status": "ready_for_bytes"}))

                    except FileExistsError as e:
                        await websocket.send_text(json.dumps({
                            "status": "exists", "message": str(e), "name": str(e)
                        }))
                    except PermissionError as e:
                        await websocket.send_text(json.dumps({
                            "status": "error", "error_type": "permission", "message": str(e)
                        }))
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "status": "error", "message": str(e)
                        }))
                        
                elif "bytes" in message:
                    if not pending_upload_meta:
                        continue
                    
                    # Accumulate chunks
                    pending_upload_buffer.extend(message["bytes"])
                    
                    # Check if all data received
                    if len(pending_upload_buffer) < pending_upload_expected:
                        continue
                    
                    # All data received — process upload
                    file_bytes = bytes(pending_upload_buffer)
                    dest_folder = pending_upload_meta.get("dest_folder")
                    name = pending_upload_meta.get("name")
                    is_zip = pending_upload_meta.get("is_zip", False)
                    overwrite = pending_upload_meta.get("overwrite", False)
                    
                    target_path = os.path.join(dest_folder, name)
                    
                    try:
                        if not os.access(dest_folder, os.W_OK):
                            raise PermissionError(f"No write permission for {dest_folder}")
                        
                        if os.path.exists(target_path) and not overwrite and not is_zip:
                            await websocket.send_text(json.dumps({
                                "status": "exists",
                                "action": "upload",
                                "name": name,
                                "path": target_path
                            }))
                            pending_upload_meta = None
                            pending_upload_buffer = bytearray()
                            continue
                            
                        if is_zip:
                            self._extract_zip_to_folder(file_bytes, dest_folder, overwrite)
                        else:
                            with open(target_path, "wb") as f:
                                f.write(file_bytes)
                                
                        await websocket.send_text(json.dumps({
                            "status": "ok", 
                            "action": "upload_success",
                            "message": f"Uploaded successfully: {name}"
                        }))
                    except FileExistsError as e:
                        await websocket.send_text(json.dumps({
                            "status": "exists",
                            "action": "upload",
                            "name": str(e),
                            "path": os.path.join(dest_folder, str(e))
                        }))
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "status": "error", "message": f"Write error: {e}"
                        }))
                    finally:
                        pending_upload_meta = None
                        pending_upload_buffer = bytearray()
                        pending_upload_expected = 0

        except WebSocketDisconnect:
            pass

ws_registry.register(FileExplorerModule)