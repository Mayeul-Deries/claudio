import sys
import threading
import time

# IMPORTANT: On Windows, PyTorch (imported via Whisper in transcriber) must be 
# imported BEFORE PyQt6, otherwise it causes an OSError: [WinError 1114] DLL init failed.
from transcriber import TranscriberThread

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QVBoxLayout, 
    QLineEdit, QScrollArea, QPushButton, QLabel, QFrame
)
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QBrush, QAction
from PyQt6.QtCore import Qt, QTimer, QSharedMemory, QSize, QEvent

from ui import VoiceBarUI, UIState
from recorder import AudioRecorder, get_input_devices
from paste import copy_and_paste
from hotkeys import HotkeyListener


class MicrophoneSelector(QWidget):
    def __init__(self, parent=None, current_device_id=None, on_select=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.current_device_id = current_device_id
        self.on_select = on_select
        self.all_devices = sorted(get_input_devices(), key=lambda x: x[1].lower())
        
        self._setup_ui()
        self.setFixedWidth(280)
        
    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container frame for styling
        self.container = QFrame()
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            #container {
                background-color: rgba(25, 25, 25, 230);
                border: 1px solid rgba(80, 80, 80, 150);
                border-radius: 12px;
            }
            QLineEdit {
                background-color: rgba(45, 45, 45, 200);
                color: white;
                border: 1px solid rgba(100, 100, 100, 100);
                border-radius: 6px;
                padding: 6px 10px;
                margin: 8px 8px 4px 8px;
                font-size: 13px;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            #scroll_content {
                background-color: transparent;
            }
            QPushButton {
                background-color: transparent;
                color: #ccc;
                text-align: left;
                padding: 8px 12px;
                border-radius: 6px;
                margin: 1px 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 25);
                color: white;
            }
            QPushButton[selected="true"] {
                color: #55aaff;
                background-color: rgba(85, 170, 255, 30);
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 4px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 100, 100, 150);
                min-height: 20px;
                border-radius: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 4)
        container_layout.setSpacing(0)
        
        # Search Box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Rechercher un micro...")
        self.search_box.textChanged.connect(self._filter_devices)
        container_layout.addWidget(self.search_box)
        
        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("scroll_content")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 4, 0, 4)
        self.scroll_layout.setSpacing(0)
        
        self.scroll.setWidget(self.scroll_content)
        container_layout.addWidget(self.scroll)
        
        self.main_layout.addWidget(self.container)
        
        # Initial device list
        self._refresh_list(self.all_devices)
        
    def _refresh_list(self, devices):
        # Clear existing
        for i in reversed(range(self.scroll_layout.count())): 
            self.scroll_layout.itemAt(i).widget().setParent(None)
            
        # Add 'Auto-détection'
        auto_btn = QPushButton("Auto-détection (Windows par défaut)")
        auto_btn.setProperty("selected", self.current_device_id is None)
        auto_btn.clicked.connect(lambda: self._select_device(None))
        self.scroll_layout.addWidget(auto_btn)
        
        # Add devices
        for idx, name in devices:
            btn = QPushButton(name)
            btn.setProperty("selected", idx == self.current_device_id)
            btn.clicked.connect(lambda checked, i=idx: self._select_device(i))
            self.scroll_layout.addWidget(btn)
            
        # Limit height to max 10 items (approx 40px per item + search box)
        item_count = len(devices) + 1
        display_count = min(10, item_count)
        scroll_h = display_count * 36 + 10
        self.scroll.setFixedHeight(scroll_h)
        
    def _filter_devices(self, text):
        if not text:
            self._refresh_list(self.all_devices)
            return
            
        filtered = [d for d in self.all_devices if text.lower() in d[1].lower()]
        self._refresh_list(filtered)
        
    def _select_device(self, index):
        if self.on_select:
            self.on_select(index)
        self.close()

    def showAt(self, point):
        # Center horizontally on the point, show above/below
        self.move(point.x() - self.width() // 2, point.y() + 10)
        self.show()
        self.search_box.setFocus()

class ClaudioApp:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
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
        
        # Safe Wake-up Detection (Timer-based)
        # We check the time every 5 seconds. If the difference is significantly
        # larger (e.g. > 15s), the system likely slept.
        self.last_check_time = time.time()
        self.wake_timer = QTimer()
        self.wake_timer.timeout.connect(self._check_system_wake)
        self.wake_timer.start(5000) # 5 seconds
        
        # Hotkey health watchdog — periodically purge stuck modifier keys
        # from the keyboard library's internal state. This is a known bug
        # where Ctrl/Alt get "stuck" after right-key presses or pyautogui use.
        # See: https://github.com/boppreh/keyboard/issues/666
        self.hotkey_watchdog = QTimer()
        self.hotkey_watchdog.timeout.connect(self.hotkeys.purge_stale_state)
        self.hotkey_watchdog.start(30000) # every 30 seconds
        
    def _setup_tray(self):
        icon = QIcon("icon.ico")
        self.app.setWindowIcon(icon)
        self.ui.setWindowIcon(icon)
        
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip("Claudio - Voice to Text")
        
        menu = QMenu()
        show_action = menu.addAction("Afficher l'interface")
        show_action.triggered.connect(self.show_ui)
        menu.addSeparator()
        
        quit_action = menu.addAction("Quit Claudio")
        quit_action.triggered.connect(self.quit)
        
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _setup_connections(self):
        # Hotkeys -> Controller
        self.hotkeys.toggle_record_signal.connect(self.toggle_recording)
        self.hotkeys.cancel_record_signal.connect(self.cancel_recording)
        
        # UI -> Controller
        self.ui.minimize_signal.connect(self.ui.minimize_animated)
        self.ui.settings_signal.connect(self.show_settings_menu)
        
        # Note: transcriber fires callback directly — no persistent signal to connect here

    def show_ui(self):
        """Restore the UI visibility with animation."""
        self.ui.show_animated()

    def toggle_recording(self):
        """Called by Ctrl+Space."""
        if self.ui.isHidden():
            self.show_ui()
            
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

    def show_settings_menu(self):
        """Show a custom searchable menu to select the audio input device."""
        if hasattr(self, '_selector') and self._selector.isVisible():
            self._selector.close()
            return
            
        self._selector = MicrophoneSelector(
            current_device_id=self.recorder.device_index,
            on_select=self._set_device
        )
        
        if self.ui._settings_btn_rect:
            btn_pos = self.ui._settings_btn_rect.bottomLeft()
            global_pos = self.ui.mapToGlobal(btn_pos.toPoint())
            self._selector.showAt(global_pos)

    def _set_device(self, device_index):
        print(f"Claudio: Setting input device to {device_index}", file=sys.stderr)
        self.recorder.device_index = device_index
        # If recording, we don't restart it mid-way. 
        # The new device will be used on the next recording.

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

    def _check_system_wake(self):
        """Timer callback to detect if the system went to sleep."""
        current_time = time.time()
        time_diff = current_time - self.last_check_time
        self.last_check_time = current_time
        
        # If the timer hasn't fired for > 15 seconds, we assume the PC was asleep
        if time_diff > 15.0:
            print(f"Claudio: System wake-up detected! (Time jump: {time_diff:.1f}s)", file=sys.stderr)
            
            # Ensure UI is visible using the animated restoration which now resets scale/opacity
            self.show_ui()
            
            # Re-center UI twice to handle geometry stabilisation
            self.ui._center_on_screen()
            QTimer.singleShot(500, self.ui._center_on_screen)
            
            # Refresh hotkeys
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
    app_instance = QApplication.instance() or QApplication(sys.argv)
    
    shared_mem = QSharedMemory("claudio_app_unique_lock")
    if not shared_mem.create(1):
        print("Claudio: An instance is already running. Exiting.", file=sys.stderr)
        
        # Try to show a native message box to inform the user
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "Claudio est déjà lancé et actif.", "Claudio", 0x30 | 0x0)
        except Exception:
            pass
            
        sys.exit(0)

    app = ClaudioApp()
    sys.exit(app.run())
