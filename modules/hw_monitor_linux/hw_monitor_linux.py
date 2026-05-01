__requirements__ = ["psutil"]

import os
import glob
import psutil
from mars.core.http.decorators import mars_module, read_dataset
from mars.core.http.registry import registry

@mars_module(
    name="Hardware Monitor (Linux)",
    prefix="/hwmon_linux",
    compatibility=["linux"]
)
class HardwareMonitorLinuxModule:
    
    def __init__(self):
        pass

    def _get_cpu_temperature(self) -> str:
        """Read CPU temperature from the Linux filesystem (sysfs)."""
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if name in ['coretemp', 'k10temp', 'cpu_thermal']:
                        for entry in entries:
                            if 'Package' in entry.label or not entry.label:
                                return str(round(entry.current, 1))
                        if entries:
                            return str(round(entries[0].current, 1))
            
            thermal_zones = glob.glob('/sys/class/thermal/thermal_zone*/temp')
            if thermal_zones:
                with open(thermal_zones[0], 'r') as f:
                    temp_millidegrees = int(f.read().strip())
                    return str(round(temp_millidegrees / 1000.0, 1))
                    
        except Exception as e:
            print(f"[HW Monitor Linux] Failed to read temperature: {e}")
            
        return "N/A"

    def _get_gpu_temperature(self) -> str:
        """Attempt to read GPU temperature on Linux."""
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if name in ['amdgpu', 'nouveau', 'nvme', 'radeon']:
                        if entries:
                            return str(round(entries[0].current, 1))
            
        except Exception:
            pass
        return "N/A"

    @read_dataset(columns=["Parameter", "Value"], label="Central Processor (CPU)", refresh_interval_ms=1000)
    def get_cpu_info(self) -> list[dict]:
        """Return CPU utilization, temperature, and frequency information."""
        cpu_freq = psutil.cpu_freq()
        freq_str = f"{round(cpu_freq.current, 0)} MHz" if cpu_freq else "N/A"
        
        return [
            {"Parameter": "Load (%)", "Value": f"{psutil.cpu_percent(interval=0.1)}"},
            {"Parameter": "Temperature (°C)", "Value": self._get_cpu_temperature()},
            {"Parameter": "Current frequency", "Value": freq_str}
        ]

    @read_dataset(columns=["Parameter", "Value"], label="Graphics Card (GPU)", refresh_interval_ms=1000)
    def get_gpu_info(self) -> list[dict]:
        """Return basic GPU information available on Linux."""
        return [
            {"Parameter": "Temperature (°C)", "Value": self._get_gpu_temperature()},
            {"Parameter": "Power (W)", "Value": "Requires Root/SMI"},
            {"Parameter": "Load (%)", "Value": "Requires Root/SMI"}
        ]

    @read_dataset(columns=["Parameter", "Value"], label="Random Access Memory (RAM)", refresh_interval_ms=1000)
    def get_ram_info(self) -> list[dict]:
        """Return RAM and swap utilization information."""
        ram = psutil.virtual_memory()
        ram_used = round(ram.used / (1024**3), 2)
        ram_total = round(ram.total / (1024**3), 2)
        
        swap = psutil.swap_memory()
        swap_used = round(swap.used / (1024**3), 2)
        
        return [
            {"Parameter": "Load (%)", "Value": f"{ram.percent}"},
            {"Parameter": "Used (GB)", "Value": f"{ram_used}"},
            {"Parameter": "Total (GB)", "Value": f"{ram_total}"},
            {"Parameter": "Swap used (GB)", "Value": f"{swap_used}"}
        ]

registry.register(HardwareMonitorLinuxModule)