import subprocess
from .input_base import BaseInputInjector

try:
    from evdev import UInput, ecodes as e, AbsInfo
except ImportError:
    UInput = None
    e = None

# Mapping of Windows extended scan codes (0xE0xx) to Linux evdev keycodes.
# Non-extended scan codes (< 0x100) are identical between Windows PS/2 Set 1 and Linux.
WIN_EXTENDED_TO_LINUX = {
    0xE01D: 97,   # KEY_RIGHTCTRL
    0xE038: 100,  # KEY_RIGHTALT
    0xE047: 102,  # KEY_HOME
    0xE048: 103,  # KEY_UP
    0xE049: 104,  # KEY_PAGEUP
    0xE04B: 105,  # KEY_LEFT
    0xE04D: 106,  # KEY_RIGHT
    0xE04F: 107,  # KEY_END
    0xE050: 108,  # KEY_DOWN
    0xE051: 109,  # KEY_PAGEDOWN
    0xE052: 110,  # KEY_INSERT
    0xE053: 111,  # KEY_DELETE
    0xE05B: 125,  # KEY_LEFTMETA  (Win/Super)
    0xE05C: 126,  # KEY_RIGHTMETA
    0xE05D: 127,  # KEY_COMPOSE   (Apps/Menu)
    0xE037: 99,   # KEY_SYSRQ     (PrintScreen)
    0xE035: 98,   # KEY_KPSLASH   (Numpad /)
    0xE01C: 96,   # KEY_KPENTER   (Numpad Enter)
}

class LinuxInputInjector(BaseInputInjector):
    def __init__(self):
        if UInput is None:
            raise RuntimeError("[RemoteControl] Library UInput not installed")

        self.width, self.height = self._get_display_size()

        capabilities = {
            e.EV_KEY: [
                e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA,
                *range(1, 256)
            ],
            e.EV_REL: [
                e.REL_WHEEL, e.REL_HWHEEL
            ],
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(value=0, min=0, max=self.width, fuzz=0, flat=0, resolution=0)),
                (e.ABS_Y, AbsInfo(value=0, min=0, max=self.height, fuzz=0, flat=0, resolution=0))
            ]
        }

        self.ui = UInput(capabilities, name="MARS-Virtual-Input-Device", version=0x1)

    def _get_display_size(self) -> tuple[int, int]:
        try:
            output = subprocess.check_output(["xrandr"]).decode("utf-8")
            for line in output.splitlines():
                if "*" in line:
                    res = line.split()[0].split('x')
                    return int(res[0]), int(res[1])
        except Exception:
            pass
        return 1920, 1080

    def get_screen_size(self) -> tuple[int, int]:
        return self.width, self.height

    def mouse_move(self, x: int, y: int):
        self.ui.write(e.EV_ABS, e.ABS_X, x)
        self.ui.write(e.EV_ABS, e.ABS_Y, y)
        self.ui.syn()

    def mouse_click(self, button: str, is_down: bool):
        btn_map = {
            "left": e.BTN_LEFT,
            "right": e.BTN_RIGHT,
            "middle": e.BTN_MIDDLE,
            "x1": e.BTN_SIDE,
            "x2": e.BTN_EXTRA
        }
        btn_code = btn_map.get(button)
        if btn_code:
            self.ui.write(e.EV_KEY, btn_code, 1 if is_down else 0)
            self.ui.syn()

    def mouse_scroll(self, clicks: int):
        steps = clicks // 120 if abs(clicks) >= 120 else clicks
        self.ui.write(e.EV_REL, e.REL_WHEEL, steps)
        self.ui.syn()

    def _translate_scancode(self, scan_code: int) -> int:
        """Translates a Windows scan code to a Linux evdev keycode.
        
        Non-extended codes (< 0x100) are identical between PS/2 Set 1 and Linux.
        Extended codes (0xE0xx) need explicit mapping.
        """
        if scan_code >= 0xE000:
            return WIN_EXTENDED_TO_LINUX.get(scan_code, 0)
        return scan_code

    def inject_scancode(self, scan_code: int, is_down: bool):
        """Inject a hardware key event. Accepts Windows scan codes and translates to Linux."""
        linux_code = self._translate_scancode(scan_code)
        if linux_code == 0:
            return
        
        self.ui.write(e.EV_KEY, linux_code, 1 if is_down else 0)
        self.ui.syn()

    def inject_unicode(self, char: str):
        """No-op: all input now comes through scancodes. Kept for interface compatibility."""
        pass