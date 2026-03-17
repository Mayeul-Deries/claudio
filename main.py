import sys
import threading

# IMPORTANT: On Windows, PyTorch (imported via Whisper in transcriber) must be 
# imported BEFORE PyQt6, otherwise it causes an OSError: [WinError 1114] DLL init failed.
from transcriber import TranscriberThread

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtCore import Qt, QTimer

from ui import VoiceBarUI, UIState
from recorder import AudioRecorder
from paste import copy_and_paste
from hotkeys import HotkeyListener

class ClaudioApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # Core modules
        self.ui = VoiceBarUI()
        self.recorder = AudioRecorder(samplerate=16000, channels=1)
        self.transcriber = TranscriberThread(model_name="medium", language="fr")
        self.hotkeys = HotkeyListener()
        
        # State
        self.is_recording = False
        
        self._setup_connections()
        self._setup_tray()
        
        # Start initial UI state and show
        self.ui.set_state_idle()
        self.ui.show()
        
        # Load whisper in background so UI opens instantly
        threading.Thread(target=self.transcriber.load_model, daemon=True).start()
        
        # Start hotkeys
        self.hotkeys.register()
        
        # Poll UI for audio amplitude when recording
        self.amp_timer = QTimer()
        self.amp_timer.timeout.connect(self._sync_amplitude_to_ui)
        self.amp_timer.start(30) # ~33fps
        
    def _setup_tray(self):
        icon = QIcon("icon.ico")
        self.app.setWindowIcon(icon)
        self.ui.setWindowIcon(icon)
        
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip("Claudio - Voice to Text")
        
        menu = QMenu()
        quit_action = menu.addAction("Quit Claudio")
        quit_action.triggered.connect(self.quit)
        
        self.tray.setContextMenu(menu)
        self.tray.show()

        # Hotkeys -> Controller
        self.hotkeys.toggle_record_signal.connect(self.toggle_recording)
        self.hotkeys.cancel_record_signal.connect(self.cancel_recording)
        
        # UI (Wake-up) -> Controller
        self.ui.system_wake_signal.connect(self._on_system_wake)

    def toggle_recording(self):
        """Called by Ctrl+Space."""
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        if not self.transcriber.is_loaded():
            print("Whisper model is still loading, please wait...")
            if getattr(self.transcriber, '_load_error', False):
                self.tray.showMessage("Claudio", "Error loading Whisper model. Check your internet connection for the first download.", QSystemTrayIcon.MessageIcon.Critical)
            else:
                self.tray.showMessage("Claudio", "The AI model is still downloading/loading. Please wait...", QSystemTrayIcon.MessageIcon.Information)
            self.ui.set_state_error()
            return
            
        success = self.recorder.start()
        if success:
            self.is_recording = True
            self.ui.set_state_recording()
        else:
            self.tray.showMessage("Claudio", "Microphone error! Could not start recording.", QSystemTrayIcon.MessageIcon.Critical)
            self.ui.set_state_error()

    def _stop_recording(self):
        self.is_recording = False
        self.ui.set_state_processing()
        audio_data = self.recorder.stop()

        if audio_data is not None and len(audio_data) > 0:
            # Each call creates a fresh background thread — no re-start issue
            self.transcriber.transcribe(audio_data, self._on_transcription_finished)
        else:
            self.ui.set_state_idle()

    def cancel_recording(self):
        """Called by Escape."""
        if self.is_recording:
            self.is_recording = False
            self.recorder.stop()
            self.ui.set_state_idle()

    def _on_transcription_finished(self, text: str):
        """Called when Whisper QThread completes."""
        if text:
            # Delegate to our paste logic
            copy_and_paste(text)
            
        self.ui.set_state_idle()
        
    def _sync_amplitude_to_ui(self):
        """Timer callback to fetch recent volume block and feed it to the UI."""
        if self.is_recording and self.ui.state == UIState.RECORDING:
            amp = self.recorder.get_current_amplitude()
            self.ui.update_amplitude(amp)

    def _on_system_wake(self):
        """Called when system wakes from sleep."""
        print("Claudio: Refreshing hotkeys due to system wake event.", file=sys.stderr)
        self.hotkeys.refresh()

    def quit(self):
        self.hotkeys.unregister()
        if self.is_recording:
            self.recorder.stop()
        self.tray.hide()
        self.app.quit()

    def run(self):
        return self.app.exec()

if __name__ == "__main__":
    app = ClaudioApp()
    sys.exit(app.run())
