# Module dependencies are installed automatically by server.py.
__requirements__ = ["pythonnet", "psutil"]

import os
import psutil
from mars.core.http.decorators import mars_module, read_dataset
from mars.core.http.registry import registry

import clr 

@mars_module(
    name="Hardware Monitor", 
    prefix="/hwmon", 
    compatibility=["windows"],
    requires_tools=["LibreHardwareMonitorLib.dll"]
)
class HardwareMonitorModule:
    def __init__(self):
        self.computer = None
        self._init_hardware_monitor()

    def _init_hardware_monitor(self):
        """Initialize a headless connection to the LibreHardwareMonitor DLL."""
        current_dir = os.path.dirname(os.path.abspath(__file__))

        dll_path = os.path.join(current_dir, "LibreHardwareMonitor", "LibreHardwareMonitorLib.dll")
        
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"[HW Monitor] DLL not found at: {dll_path}")

        try:
            clr.AddReference(dll_path)
            from LibreHardwareMonitor import Hardware
            
            self.computer = Hardware.Computer()
            self.computer.IsCpuEnabled = True
            self.computer.IsGpuEnabled = True
            self.computer.IsMemoryEnabled = True
            self.computer.Open()
        except Exception as e:
            print(f"[HW Monitor] Failed to initialize sensors: {e}")

    def _get_sensor_val(self, hw_type_name: str, sensor_type_name: str) -> str:
        """Read a value from a specific sensor through the C# objects."""
        if not self.computer:
            return "N/A"
            
        for hw in self.computer.Hardware:
            if hw_type_name in str(hw.HardwareType):
                hw.Update()
                for sensor in hw.Sensors:
                    if sensor_type_name in str(sensor.SensorType) and "Package" in str(sensor.Name):
                        return f"{round(sensor.Value, 1)}"
                for sensor in hw.Sensors:
                    if sensor_type_name in str(sensor.SensorType):
                        return f"{round(sensor.Value, 1)}"
        return "N/A"

    @read_dataset(columns=["Parameter", "Value"], label="Central Processor (CPU)", refresh_interval_ms=1000)
    def get_cpu_info(self) -> list[dict]:
        """Return CPU utilization, temperature, and power information."""
        return [
            {"Parameter": "Load (%)", "Value": f"{psutil.cpu_percent(interval=0.1)}"},
            {"Parameter": "Temperature (°C)", "Value": self._get_sensor_val("Cpu", "Temperature")},
            {"Parameter": "Power (W)", "Value": self._get_sensor_val("Cpu", "Power")}
        ]

    @read_dataset(columns=["Parameter", "Value"], label="Graphics Card (GPU)", refresh_interval_ms=1000)
    def get_gpu_info(self) -> list[dict]:
        """Return GPU utilization, temperature, and power information."""
        return [
            {"Parameter": "Load (%)", "Value": self._get_sensor_val("Gpu", "Load")},
            {"Parameter": "Temperature (°C)", "Value": self._get_sensor_val("Gpu", "Temperature")},
            {"Parameter": "Power (W)", "Value": self._get_sensor_val("Gpu", "Power")}
        ]

    @read_dataset(columns=["Parameter", "Value"], label="Random Access Memory (RAM)", refresh_interval_ms=1000)
    def get_ram_info(self) -> list[dict]:
        """Return RAM utilization information."""
        ram = psutil.virtual_memory()
        ram_used = round(ram.used / (1024**3), 2)
        ram_total = round(ram.total / (1024**3), 2)
        return [
            {"Parameter": "Load (%)", "Value": f"{ram.percent}"},
            {"Parameter": "Used (GB)", "Value": f"{ram_used}"},
            {"Parameter": "Total (GB)", "Value": f"{ram_total}"}
        ]

registry.register(HardwareMonitorModule)