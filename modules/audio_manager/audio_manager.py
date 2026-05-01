__requirements__ = ["pycaw", "comtypes", "pydantic"]

import comtypes
from ctypes import cast, POINTER
from typing import Any
from pydantic import BaseModel

from mars.core.http.decorators import mars_module, read_dataset, update_range, update_boolean
from mars.core.http.registry import registry

from pycaw.pycaw import IAudioEndpointVolume, IMMDeviceEnumerator
from pycaw.constants import CLSID_MMDeviceEnumerator

class VolumePayload(BaseModel):
    value: int

class MutePayload(BaseModel):
    state: bool


@mars_module(name="Audio Manager", prefix="/audio", compatibility=["windows"])
class AudioManagerModule:

    def __init__(self):
        comtypes.CoInitialize()
        self._volume_interface = self._create_interface()

    def _create_interface(self) -> Any:
        """Create and return a stable COM interface."""
        device_enumerator = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator,
            IMMDeviceEnumerator,
            comtypes.CLSCTX_INPROC_SERVER
        )
        imm_device = device_enumerator.GetDefaultAudioEndpoint(0, 1)
        interface = imm_device.Activate(
            IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None
        )
        return cast(interface, POINTER(IAudioEndpointVolume))

    def _get_interface(self) -> Any:
        """Return the cached interface and recreate it if it becomes invalid."""
        try:
            self._volume_interface.GetMasterVolumeLevelScalar()
            return self._volume_interface
        except Exception:
            self._volume_interface = self._create_interface()
            return self._volume_interface

    def __del__(self):
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass

    @read_dataset(columns=["Parameter", "Value"], label="Current State", refresh_interval_ms=1000)
    def get_state(self) -> list[dict]:
        """Return the current volume and mute state."""
        vi = self._get_interface()
        current_vol = round(vi.GetMasterVolumeLevelScalar() * 100)
        is_muted = vi.GetMute() == 1
        return [
            {"Parameter": "Volume (%)", "Value": current_vol},
            {"Parameter": "Mute state", "Value": "Enabled" if is_muted else "Disabled"}
        ]

    @update_range(
        min_val=0, max_val=100, label="Adjust Volume",
        bind_source=get_state,
        bind_key="Volume (%)"
    )
    def set_volume(self, payload: VolumePayload):
        """Set the system volume to the requested level."""
        safe_value = max(0, min(100, payload.value))
        self._get_interface().SetMasterVolumeLevelScalar(safe_value / 100.0, None)
        return {"status": "success", "message": f"Volume set to {safe_value}%"}

    @update_boolean(
        label="Mute Toggle",
        bind_source=get_state,
        bind_key="Mute state"
    )
    def set_mute(self, payload: MutePayload):
        """Enable or disable system mute."""
        self._get_interface().SetMute(1 if payload.state else 0, None)
        return {"status": "success", "message": f"Mute state changed to {payload.state}"}


registry.register(AudioManagerModule)