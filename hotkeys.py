import sys
import keyboard
from PyQt6.QtCore import QObject, pyqtSignal


def _purge_keyboard_internal_state():
    """Force-clear the keyboard library's internal modifier/key state.

    The `keyboard` library tracks pressed keys internally. On Windows,
    certain scenarios (right-Ctrl/Alt press with suppress, sleep/wake,
    pyautogui simulated keypresses) desync this internal state from
    reality, leaving modifier keys permanently "stuck". This makes
    combo hotkeys (ctrl+space) silently stop matching.

    See: https://github.com/boppreh/keyboard/issues/666
          https://github.com/boppreh/keyboard/issues/674
    """
    try:
        with keyboard._pressed_events_lock:
            keyboard._pressed_events.clear()
        keyboard._listener.active_modifiers.clear()
        keyboard._logically_pressed_keys.clear()
    except Exception as e:
        print(f"Claudio: keyboard state purge error: {e}", file=sys.stderr)

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

    def register(self, force=False):
        """Register the global hotkeys. Requires admin privileges on some systems."""
        if self._registered and not force:
            return
            
        if force and self._registered:
            self.unregister()
            
        try:
            keyboard.add_hotkey(self.start_stop_hotkey, self._on_toggle, suppress=False)
            keyboard.add_hotkey(self.cancel_hotkey, self._on_cancel, suppress=False)
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

    def refresh(self):
        """Unregister and re-register hotkeys."""
        print("Refreshing hotkeys...", file=sys.stderr)
        _purge_keyboard_internal_state()
        self.register(force=True)

    def purge_stale_state(self):
        """Periodically called by the main app to prevent modifier-stuck issues."""
        _purge_keyboard_internal_state()
