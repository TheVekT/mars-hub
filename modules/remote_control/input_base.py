import abc

class BaseInputInjector(abc.ABC):
    @abc.abstractmethod
    def get_screen_size(self) -> tuple[int, int]:
        """Returns the width and height of the remote screen in pixels."""
        pass

    @abc.abstractmethod
    def mouse_move(self, x: int, y: int):
        """Moves the mouse cursor to the specified (x, y) coordinates on the remote screen."""
        pass

    @abc.abstractmethod
    def mouse_click(self, button: str, is_down: bool):
        """button: 'left', 'right', 'middle', 'x1' (mouse4), 'x2' (mouse5)"""
        pass

    @abc.abstractmethod
    def mouse_scroll(self, clicks: int):
        """Scrolls the mouse wheel. Positive clicks scroll up, negative clicks scroll down."""
        pass

    @abc.abstractmethod
    def inject_scancode(self, scan_code: int, is_down: bool):
        """Injects a keyboard scancode. scan_code is the hardware scancode of the key, and is_down indicates whether the key is being pressed (True) or released (False)."""
        pass

    @abc.abstractmethod
    def inject_unicode(self, char: str):
        """Injects a Unicode character as keyboard input. char is the character to be injected, and it will be sent as a key press followed by a key release."""
        pass