import os
from mars.core.http.decorators import mars_module, read_multiline
from mars.core.http.registry import registry

@mars_module(name="Server Console", prefix="/console", compatibility=["windows", "linux"])
class ServerConsoleModule:
    def __init__(self):
        self.log_file = "server.log"

    @read_multiline(label="Live Console Output", refresh_interval_ms=1000)
    def get_logs(self) -> str:
        """Return the last 100 lines from the server log file."""
        if not os.path.exists(self.log_file):
            return (
                f"[Error] Log file '{self.log_file}' was not found.\n"
            )

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            last_lines = lines[-100:]
            return "".join(last_lines)
            
        except Exception as e:
            return f"[Log read error] {e}"

registry.register(ServerConsoleModule)