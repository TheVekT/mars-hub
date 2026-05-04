import ctypes
from ctypes import wintypes
from .input_base import BaseInputInjector

PUL = ctypes.POINTER(ctypes.c_ulong)

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", PUL)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", PUL)]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD),
                ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]

class INPUT_I(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT),
                ("mi", MOUSEINPUT),
                ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD),
                ("ii", INPUT_I)]

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800

class WindowsInputInjector(BaseInputInjector):
    def __init__(self):
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)

    def get_screen_size(self) -> tuple[int, int]:
        width = self.user32.GetSystemMetrics(0)
        height = self.user32.GetSystemMetrics(1)
        return width, height

    def _send_input(self, *inputs):
        nInputs = len(inputs)
        LPINPUT = INPUT * nInputs
        pInputs = LPINPUT(*inputs)
        cbSize = ctypes.c_int(ctypes.sizeof(INPUT))
        return self.user32.SendInput(nInputs, pInputs, cbSize)

    def mouse_move(self, x: int, y: int):
        width, height = self.get_screen_size()
        abs_x = int((x * 65535) / width)
        abs_y = int((y * 65535) / height)
        
        mi = MOUSEINPUT(abs_x, abs_y, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None)
        self._send_input(INPUT(INPUT_MOUSE, INPUT_I(mi=mi)))

    def mouse_click(self, button: str, is_down: bool):
        flags = 0
        mouse_data = 0
        
        if button == "left":
            flags = MOUSEEVENTF_LEFTDOWN if is_down else MOUSEEVENTF_LEFTUP
        elif button == "right":
            flags = MOUSEEVENTF_RIGHTDOWN if is_down else MOUSEEVENTF_RIGHTUP
        elif button == "middle":
            flags = MOUSEEVENTF_MIDDLEDOWN if is_down else MOUSEEVENTF_MIDDLEUP
        elif button == "x1": # Mouse 4
            flags = MOUSEEVENTF_XDOWN if is_down else MOUSEEVENTF_XUP
            mouse_data = 0x0001
        elif button == "x2": # Mouse 5
            flags = MOUSEEVENTF_XDOWN if is_down else MOUSEEVENTF_XUP
            mouse_data = 0x0002

        if flags:
            mi = MOUSEINPUT(0, 0, mouse_data, flags, 0, None)
            self._send_input(INPUT(INPUT_MOUSE, INPUT_I(mi=mi)))

    def mouse_scroll(self, clicks: int):
        mi = MOUSEINPUT(0, 0, clicks, MOUSEEVENTF_WHEEL, 0, None)
        self._send_input(INPUT(INPUT_MOUSE, INPUT_I(mi=mi)))

    def inject_scancode(self, scan_code: int, is_down: bool):
        """Ін'єкція апаратного скан-коду.
        
        Handles extended keys (0xE0xx): strips the 0xE0 prefix and sets
        KEYEVENTF_EXTENDEDKEY flag, as required by Windows SendInput.
        """
        flags = KEYEVENTF_SCANCODE
        actual_scan = scan_code
        
        # Extended keys (arrows, RCtrl, RAlt, Win, Delete, Home, etc.)
        if scan_code >= 0xE000:
            actual_scan = scan_code & 0xFF  # Strip 0xE0 prefix
            flags |= KEYEVENTF_EXTENDEDKEY
        
        if not is_down:
            flags |= KEYEVENTF_KEYUP
            
        ki = KEYBDINPUT(0, actual_scan, flags, 0, None)
        self._send_input(INPUT(INPUT_KEYBOARD, INPUT_I(ki=ki)))

    def inject_unicode(self, char: str):
        """No-op: all input now comes through scancodes."""
        pass