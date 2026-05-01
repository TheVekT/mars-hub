import platform
import psutil
from datetime import datetime

from mars.core.http.decorators import mars_module, read_scalar, read_dataset
from mars.core.http.registry import registry


@mars_module(name="System Information", prefix="/sysinfo", compatibility=["windows", "linux"])
class SystemInfoModule:
    """
    Module for retrieving general operating system information and basic hardware details.
    """

    @read_scalar(label="OS Version")
    def get_os_version(self) -> dict:
        """Return the operating system name and version."""
        os_name = platform.system()
        os_release = platform.release()
        os_version = platform.version()
        
        display_string = f"{os_name} {os_release} (Build: {os_version})"
        return {"value": display_string}

    @read_scalar(label="Processor Architecture")
    def get_architecture(self) -> dict:
        """Return the OS architecture."""
        arch = platform.machine()
        processor = platform.processor()
        return {"value": f"{arch} - {processor}"}

    @read_scalar(label="System Boot Time")
    def get_boot_time(self) -> dict:
        """Return the system boot time."""
        boot_time_timestamp = psutil.boot_time()
        bt = datetime.fromtimestamp(boot_time_timestamp)
        return {"value": bt.strftime("%Y-%m-%d %H:%M:%S")}

    @read_dataset(columns=["Disk", "File System", "Total (GB)", "Free (GB)"], label="Local Disks", refresh_interval_ms=10000)
    def get_disks_info(self) -> list[dict]:
        """Return a table with information about connected storage devices."""
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    "Disk": partition.device,
                    "File System": partition.fstype,
                    "Total (GB)": round(usage.total / (1024 ** 3), 2),
                    "Free (GB)": round(usage.free / (1024 ** 3), 2)
                })
            except PermissionError:
                continue
                
        return disks


registry.register(SystemInfoModule)