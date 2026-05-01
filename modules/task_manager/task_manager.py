__requirements__ = ["psutil", "pydantic"]

import psutil
from pydantic import BaseModel
from mars.core.http.decorators import mars_module, read_dataset, execute_with_params
from mars.core.http.registry import registry

class KillProcessPayload(BaseModel):
    """Payload used to terminate a process by PID."""
    pid: int

@mars_module(name="Task Manager", prefix="/taskmgr", compatibility=["windows", "linux"])
class TaskManagerModule:

    @read_dataset(columns=["PID", "Name", "RAM (MB)", "Status"], label="Process List", refresh_interval_ms=3000)
    def get_processes(self) -> list[dict]:
        """Return a list of all active processes in the system."""
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'status']):
            try:
                info = proc.info
                ram_mb = round(info['memory_info'].rss / (1024 * 1024), 2)
                
                processes.append({
                    "PID": info['pid'],
                    "Name": info['name'],
                    "RAM (MB)": ram_mb,
                    "Status": info['status']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        processes.sort(key=lambda x: x["RAM (MB)"], reverse=True)
        return processes

    @execute_with_params(
        label="Terminate Process",
        danger_level="high",
        params_schema=[
            {
                "name": "pid",
                "label": "Select a process to terminate",
                "type": "select_from_dataset",
                "source_endpoint": get_processes,
                "value_key": "PID",
                "display_key": "Name"
            }
        ]
    )
    def kill_process(self, payload: KillProcessPayload):
        """Terminate a process by the provided PID."""
        try:
            proc = psutil.Process(payload.pid)
            proc_name = proc.name()
            
            proc.terminate()
            
            return {"status": "success", "message": f"Process {proc_name} (PID: {payload.pid}) terminated successfully"}
            
        except psutil.NoSuchProcess:
            return {"status": "error", "message": f"Process with PID {payload.pid} no longer exists"}
        except psutil.AccessDenied:
            return {"status": "error", "message": f"Access denied. Cannot terminate process {payload.pid}"}
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}


registry.register(TaskManagerModule)