import sys
import keyboard
from PyQt6.QtCore import QObject, pyqtSignal

class HotkeyListener(QObject):
    # Signals to communicate with the main UI thread
    toggle_record_signal = pyqtSignal()
    cancel_record_signal = pyqtSignal()

    def __init__(self, start_stop_hotkey="ctrl+space", cancel_hotkey="esc"):
        super().__init__()
        self.start_stop_hotkey = start_stop_hotkey
        self.cancel_hotkey = cancel_hotkey
        self._registered = False

    def _on_toggle(self):
        """Callback for the start/stop hotkey."""
        self.toggle_record_signal.emit()

    def _on_cancel(self):
        """Callback for the cancel hotkey."""
        self.cancel_record_signal.emit()

    def register(self):
        """Register the global hotkeys. Requires admin privileges on some systems."""
        if self._registered:
            return
            
        try:
            keyboard.add_hotkey(self.start_stop_hotkey, self._on_toggle, suppress=True)
            keyboard.add_hotkey(self.cancel_hotkey, self._on_cancel, suppress=True)
            self._registered = True
            print(f"Hotkeys registered: '{self.start_stop_hotkey}', '{self.cancel_hotkey}'", file=sys.stderr)
        except ImportError as e:
            print(f"Failed to register hotkeys: {e}", file=sys.stderr)
            print("Note: On Windows, the 'keyboard' library may require administrator privileges.", file=sys.stderr)

    def unregister(self):
        """Unregister all hotkeys."""
        if not self._registered:
            return
            
        try:
            keyboard.remove_hotkey(self.start_stop_hotkey)
            keyboard.remove_hotkey(self.cancel_hotkey)
            self._registered = False
        except Exception as e:
            print(f"Failed to unregister hotkeys: {e}", file=sys.stderr)
