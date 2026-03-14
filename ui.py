import math
from enum import Enum
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer, pyqtProperty, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath

class UIState(Enum):
    IDLE = 1
    RECORDING = 2
    PROCESSING = 3
    ERROR = 4

class VoiceBarUI(QWidget):
    # Signals to communicate to the main controller
    # Though UI is mostly driven *by* the controller, we provide slots for updates
    
    def __init__(self):
        super().__init__()
        
        # UI State
        self.state = UIState.IDLE
        
        # Dimensions and properties
        self._bar_width = 40.0
        self._bar_height = 6.0
        
        # Animations
        self.anim_group = None
        
        # Waveform data
        self.current_amplitude = 0.0
        self.waveform_timer = QTimer(self)
        self.waveform_timer.timeout.connect(self.update)
        
        # Red dot pulse
        self._dot_opacity = 0.0
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._animate_dot)
        self.pulse_phase = 0.0
        
        # Shimmer effect
        self._shimmer_pos = -1.0
        self.shimmer_timer = QTimer(self)
        self.shimmer_timer.timeout.connect(self._animate_shimmer)
        
        # Error flash
        self._error_flash_opacity = 0.0
        self.error_timer = QTimer(self)
        self.error_timer.setSingleShot(True)
        self.error_timer.timeout.connect(self._reset_error)
        
        self._setup_window()
        
    def _setup_window(self):
        # Frameless, stay on top, tool window (no taskbar icon)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        
        # Transparent background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Fixed size container (large enough to fit max expanded size + shadow)
        self.setFixedSize(100, 50)
        
        # Center horizontally at the top of the screen
        self._center_on_screen()
        
    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + 10 # 10px from the top
        self.move(x, y)

    # --- Properties for QPropertyAnimation ---
    
    @pyqtProperty(float)
    def barWidth(self):
        return self._bar_width

    @barWidth.setter
    def barWidth(self, v):
        self._bar_width = v
        self.update()

    @pyqtProperty(float)
    def barHeight(self):
        return self._bar_height

    @barHeight.setter
    def barHeight(self, v):
        self._bar_height = v
        self.update()

    # --- State Transitions ---

    def set_state_idle(self):
        self.state = UIState.IDLE
        self._stop_all_timers()
        self._animate_size(40.0, 6.0)

    def set_state_recording(self):
        self.state = UIState.RECORDING
        self._stop_all_timers()
        self.waveform_timer.start(30) # ~33fps
        self.pulse_timer.start(50)
        self._animate_size(60.0, 24.0)

    def set_state_processing(self):
        self.state = UIState.PROCESSING
        self._stop_all_timers()
        self._shimmer_pos = -1.0
        self.shimmer_timer.start(16) # ~60fps
        self._animate_size(40.0, 6.0)
        
    def set_state_error(self):
        self.state = UIState.ERROR
        self._stop_all_timers()
        self._error_flash_opacity = 1.0
        self._animate_size(40.0, 6.0)
        self.error_timer.start(300) # Flash for 300ms
        self.update()

    # --- Actions / Updaters ---

    def update_amplitude(self, amp: float):
        # Scale amplitude (experimentally determined based on sounddevice float32 output)
        # Assuming typical speech RMS is around 0.01 to 0.1
        scaled = min(1.0, amp * 10.0) 
        # Smooth out the visual (simple low pass)
        self.current_amplitude = (self.current_amplitude * 0.7) + (scaled * 0.3)

    # --- Internal Animation Helpers ---
    
    def _stop_all_timers(self):
        self.waveform_timer.stop()
        self.pulse_timer.stop()
        self.shimmer_timer.stop()
        self.current_amplitude = 0.0
        self._dot_opacity = 0.0
        
    def _animate_size(self, target_w, target_h):
        self.anim_w = QPropertyAnimation(self, b"barWidth")
        self.anim_w.setEndValue(float(target_w))
        self.anim_w.setDuration(200)
        
        self.anim_h = QPropertyAnimation(self, b"barHeight")
        self.anim_h.setEndValue(float(target_h))
        self.anim_h.setDuration(200)
        
        self.anim_w.start()
        self.anim_h.start()

    def _animate_dot(self):
        self.pulse_phase += 0.2
        # Pulse between roughly 0.2 and 1.0
        self._dot_opacity = 0.6 + 0.4 * math.sin(self.pulse_phase)
        self.update()
        
    def _animate_shimmer(self):
        self._shimmer_pos += 0.05
        if self._shimmer_pos > 2.0:
            self._shimmer_pos = -1.0
        self.update()
        
    def _reset_error(self):
        self._error_flash_opacity = 0.0
        self.set_state_idle()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Center coordinates
        cx = self.width() / 2
        cy = self.height() / 2
        
        w = self._bar_width
        h = self._bar_height
        
        # Bar bounds
        rect = QRectF(cx - w/2, cy - h/2, w, h)
        
        self._draw_background(painter, rect, h)
        self._draw_state_overlay(painter, rect, cx, cy, w, h)

    def _draw_background(self, painter: QPainter, rect: QRectF, h: float):
        # Draw shadow
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(rect.translated(0, 2), h/2, h/2)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 50))
        
        # Draw main pill background
        bg_color = QColor(10, 10, 10) # #0a0a0a
        
        if self.state == UIState.ERROR:
            # Blend in red
            r = int(10 + (245 * self._error_flash_opacity))
            bg_color = QColor(r, 10, 10)
            
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, h/2, h/2)

    def _draw_state_overlay(self, painter: QPainter, rect: QRectF, cx: float, cy: float, w: float, h: float):
        if self.state == UIState.IDLE:
            self._draw_idle_mic(painter, cx, cy)
        elif self.state == UIState.RECORDING:
            self._draw_recording_waveform(painter, cx, cy, w, h)
        elif self.state == UIState.PROCESSING:
            self._draw_processing_shimmer(painter, rect, h)

    def _draw_idle_mic(self, painter: QPainter, cx: float, cy: float):
        # Draw tiny mic icon (a circle and a rounded rect)
        painter.setOpacity(0.4)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRoundedRect(QRectF(cx - 1, cy - 2, 2, 4), 1, 1)
        # Simple curved standard
        painter.setPen(QPen(QColor(255, 255, 255), 0.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(cx - 2, cy - 1, 4, 3), 0, -180 * 16)
        painter.setOpacity(1.0)
        
    def _draw_recording_waveform(self, painter: QPainter, cx: float, cy: float, w: float, h: float):
        # 1. Red pulsing dot
        painter.setOpacity(self._dot_opacity)
        painter.setBrush(QColor(255, 50, 50))
        painter.setPen(Qt.PenStyle.NoPen)
        dot_r = 2.5
        painter.drawEllipse(QPointF(cx - w/2 + 8, cy), dot_r, dot_r)
        
        # 2. Waveform bars
        painter.setOpacity(1.0)
        painter.setBrush(QColor(255, 255, 255))
        
        num_bars = 5
        spacing = 4
        bar_w = 2
        total_w = (num_bars * bar_w) + ((num_bars - 1) * spacing)
        start_x = cx - total_w / 2 + 4 # Shift slightly right to account for red dot
        
        multipliers = [0.4, 0.8, 1.0, 0.7, 0.3]
        max_h = h - 8
        
        for i in range(num_bars):
            bar_h = 2 + (max_h * self.current_amplitude * multipliers[i])
            bx = start_x + (i * (bar_w + spacing))
            by = cy - bar_h / 2
            painter.drawRoundedRect(QRectF(bx, by, bar_w, bar_h), bar_w/2, bar_w/2)

    def _draw_processing_shimmer(self, painter: QPainter, rect: QRectF, h: float):
        # Draw Shimmer effect using a linear gradient overlay
        grad = QLinearGradient(rect.topLeft(), rect.topRight())
        
        grad.setColorAt(max(0.0, min(1.0, self._shimmer_pos - 0.2)), QColor(255, 255, 255, 0))
        grad.setColorAt(max(0.0, min(1.0, self._shimmer_pos)), QColor(255, 255, 255, 60))
        grad.setColorAt(max(0.0, min(1.0, self._shimmer_pos + 0.2)), QColor(255, 255, 255, 0))
        
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(rect, h/2, h/2)
