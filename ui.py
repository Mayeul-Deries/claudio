import math
from enum import Enum
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer, pyqtProperty, QRectF, QPointF, QEasingCurve, pyqtSignal, QParallelAnimationGroup
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPainterPath



class UIState(Enum):
    IDLE = 1
    RECORDING = 2
    PROCESSING = 3
    ERROR = 4


# Target sizes for each state
_IDLE_W, _IDLE_H = 60.0, 16.0
_RECORDING_W, _RECORDING_H = 160.0, 44.0
_PROCESSING_W, _PROCESSING_H = 60.0, 16.0

# Container window — must be large enough to hold the expanded bar + shadow room
_CONTAINER_W = 300
_CONTAINER_H = 80


class VoiceBarUI(QWidget):
    minimize_signal = pyqtSignal()

    def __init__(self):
        super().__init__()

        # UI State
        self.state = UIState.IDLE

        # Animated dimensions
        self._bar_width = _IDLE_W
        self._bar_height = _IDLE_H

        # --- Drag & Click state ---
        self._drag_offset = None   # QPoint when dragging
        self._dragging = False
        self._min_btn_rect = None  # Rect of the minimize button for clicks
        self._is_btn_hovered = False # Is mouse strictly over the red button?

        # --- Animation objects (kept as instance vars to prevent GC) ---
        self.anim_w = None
        self.anim_h = None
        self.anim_group = None
        self._global_scale = 1.0

        # --- Waveform: 5 bars, each independently animated ---
        self.current_amplitude = 0.0
        self._num_bars = 5
        self._dot_size = 4.0          # dot diameter when silent
        self._max_bar_h = 22.0        # full height when loudest
        # Each bar tracks its own smooth height
        self._bar_smooth_h = [self._dot_size] * self._num_bars
        # Per-bar phase offset for organic idle breathing
        self._bar_idle_phase = [i * (2 * math.pi / self._num_bars) for i in range(self._num_bars)]
        self._idle_tick = 0.0
        # Multipliers shape the waveform envelope (centre bar tallest)
        self._bar_multipliers = [0.45, 0.75, 1.0, 0.75, 0.45]

        self.waveform_timer = QTimer(self)
        self.waveform_timer.timeout.connect(self._tick_waveform)

        # --- Red dot pulse ---
        self._dot_opacity = 0.0
        self.pulse_phase = 0.0
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._animate_dot)

        # --- Shimmer ---
        self._shimmer_pos = -0.3
        self.shimmer_timer = QTimer(self)
        self.shimmer_timer.timeout.connect(self._animate_shimmer)

        # --- Error flash ---
        self._error_flash_opacity = 0.0
        self.error_timer = QTimer(self)
        self.error_timer.setSingleShot(True)
        self.error_timer.timeout.connect(self._reset_error)

        # --- Hover glow ---
        self._hover_opacity = 0.0   # 0.0 = not hovered, 1.0 = fully hovered
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(16)  # ~60 fps
        self._hover_timer.timeout.connect(self._tick_hover)
        self._hover_target = 0.0

        # --- Button Hover animation ---
        self._btn_hover_opacity = 0.0
        self._btn_hover_target = 0.0
        self._btn_hover_timer = QTimer(self)
        self._btn_hover_timer.setInterval(16)
        self._btn_hover_timer.timeout.connect(self._tick_btn_hover)

        self._setup_window()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True) # Needed to track hover over the small button
        self.setFixedSize(_CONTAINER_W, _CONTAINER_H)
        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + 10
        self.move(x, y)

    # ------------------------------------------------------------------ #
    # PyQt Properties used by QPropertyAnimation                          #
    # ------------------------------------------------------------------ #

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

    @pyqtProperty(float)
    def globalScale(self):
        return self._global_scale

    @globalScale.setter
    def globalScale(self, v):
        self._global_scale = v
        self.update()

    # ------------------------------------------------------------------ #
    # Public state setters                                                 #
    # ------------------------------------------------------------------ #

    def set_state_idle(self):
        self.state = UIState.IDLE
        self._stop_all_timers()
        self._animate_size(_IDLE_W, _IDLE_H)

    def set_state_recording(self):
        self.state = UIState.RECORDING
        self._stop_all_timers()
        self.waveform_timer.start(30)   # ~33 fps for waveform updates
        self.pulse_timer.start(40)      # ~25 fps for dot pulse
        self._animate_size(_RECORDING_W, _RECORDING_H)

    def set_state_processing(self):
        self.state = UIState.PROCESSING
        self._stop_all_timers()
        self._shimmer_pos = -0.3
        self.shimmer_timer.start(16)    # ~60 fps shimmer
        self._animate_size(_PROCESSING_W, _PROCESSING_H)

    def set_state_error(self):
        self.state = UIState.ERROR
        self._stop_all_timers()
        self._error_flash_opacity = 1.0
        self._animate_size(_IDLE_W, _IDLE_H)
        self.error_timer.start(500)
        self.update()

    def update_amplitude(self, amp: float):
        """Called by main controller with raw RMS amplitude.

        Uses a power-curve so that normal speech (RMS ~0.01-0.03) maps to
        60-80% of waveform height instead of ~15%.
        """
        # x^0.35 compresses the dynamic range — quiet sounds get amplified more
        scaled = min(1.0, (amp ** 0.35) * 3.5) if amp > 0 else 0.0
        self.current_amplitude = (self.current_amplitude * 0.55) + (scaled * 0.45)

    def _tick_waveform(self):
        """Called at ~33 fps. Updates each bar's smooth height, then repaints."""
        self._idle_tick += 0.08  # idle breathing speed
        for i in range(self._num_bars):
            if self.current_amplitude > 0.04:  # sound detected
                # Target grows toward amplitude * multiplier * max_bar_h
                target = self._dot_size + (
                    (self._max_bar_h - self._dot_size)
                    * self.current_amplitude
                    * self._bar_multipliers[i]
                )
            else:
                # Silence: gentle sine breathing keeps bars as dots with subtle life
                idle_breath = 0.5 + 0.5 * math.sin(self._idle_tick + self._bar_idle_phase[i])
                target = self._dot_size + idle_breath * 1.5  # max 1.5px above dot_size

            # Low-pass per bar: fast attack (0.45), slower decay (0.15)
            alpha = 0.45 if target > self._bar_smooth_h[i] else 0.15
            self._bar_smooth_h[i] = self._bar_smooth_h[i] * (1 - alpha) + target * alpha

        self.update()

    # ------------------------------------------------------------------ #
    # Drag-to-move support                                                #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            press_pos = event.position()
            # Check if minimize button was clicked
            if self._min_btn_rect is not None and self._hover_opacity > 0.1:
                if self._min_btn_rect.contains(press_pos):
                    self.minimize_signal.emit()
                    return # Do not start dragging

            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position()
        
        # Check if we are hovering specifically over the minimize button
        if self._min_btn_rect is not None:
            was_btn_hovered = self._is_btn_hovered
            self._is_btn_hovered = self._min_btn_rect.contains(pos)
            if was_btn_hovered != self._is_btn_hovered:
                if self._is_btn_hovered:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                    self._btn_hover_target = 1.0
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                    self._btn_hover_target = 0.0
                self._btn_hover_timer.start()
                self.update()

        if self._dragging and self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_offset = None
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        """Mouse entered — start bump animation."""
        self._hover_target = 1.0
        self._hover_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Mouse left — start bump reverse animation and restore cursor."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._is_btn_hovered = False
        self._btn_hover_target = 0.0
        self._btn_hover_timer.start()
        
        self._hover_target = 0.0
        self._hover_timer.start()
        super().leaveEvent(event)

    def _tick_hover(self):
        """Smooth hover opacity interpolation at ~60 fps."""
        speed = 0.12
        self._hover_opacity += (self._hover_target - self._hover_opacity) * speed
        if abs(self._hover_opacity - self._hover_target) < 0.005:
            self._hover_opacity = self._hover_target
            self._hover_timer.stop()
        self.update()

    def _tick_btn_hover(self):
        """Smooth animation for the minus button icon."""
        speed = 0.15
        self._btn_hover_opacity += (self._btn_hover_target - self._btn_hover_opacity) * speed
        if abs(self._btn_hover_opacity - self._btn_hover_target) < 0.005:
            self._btn_hover_opacity = self._btn_hover_target
            self._btn_hover_timer.stop()
        self.update()

    # ------------------------------------------------------------------ #
    # Internal animation helpers                                           #
    # ------------------------------------------------------------------ #

    def _stop_all_timers(self):
        self.waveform_timer.stop()
        self.pulse_timer.stop()
        self.shimmer_timer.stop()
        self.current_amplitude = 0.0
        self._dot_opacity = 0.0

    def _animate_size(self, target_w: float, target_h: float):
        """Animate bar width and height simultaneously with ease-in-out."""
        self.anim_w = QPropertyAnimation(self, b"barWidth")
        self.anim_w.setEndValue(target_w)
        self.anim_w.setDuration(200)
        self.anim_w.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.anim_h = QPropertyAnimation(self, b"barHeight")
        self.anim_h.setEndValue(target_h)
        self.anim_h.setDuration(200)
        self.anim_h.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.anim_w.start()
        self.anim_h.start()

    def _animate_dot(self):
        self.pulse_phase += 0.18
        self._dot_opacity = 0.55 + 0.45 * math.sin(self.pulse_phase)
        self.update()

    def _animate_shimmer(self):
        self._shimmer_pos += 0.04
        if self._shimmer_pos > 1.3:
            self._shimmer_pos = -0.3
        self.update()

    def _reset_error(self):
        self._error_flash_opacity = 0.0
        self.set_state_idle()

    def minimize_animated(self):
        """Play a smooth shrink-to-zero and fade-out animation like iOS."""
        self.anim_group = QParallelAnimationGroup()
        
        anim_s = QPropertyAnimation(self, b"globalScale")
        anim_s.setEndValue(0.0)
        anim_s.setDuration(250)
        anim_s.setEasingCurve(QEasingCurve.Type.InBack)
        
        anim_o = QPropertyAnimation(self, b"windowOpacity")
        anim_o.setEndValue(0.0)
        anim_o.setDuration(200)
        
        self.anim_group.addAnimation(anim_s)
        self.anim_group.addAnimation(anim_o)
        
        self.anim_group.finished.connect(self.hide)
        self.anim_group.start()

    def show_animated(self):
        """Play a smooth pop-out and fade-in animation."""
        self.show()
        self.raise_()
        self.activateWindow()

        self.anim_group = QParallelAnimationGroup()
        
        anim_s = QPropertyAnimation(self, b"globalScale")
        anim_s.setStartValue(self._global_scale)
        anim_s.setEndValue(1.0)
        anim_s.setDuration(350)
        anim_s.setEasingCurve(QEasingCurve.Type.OutBack)
        
        anim_o = QPropertyAnimation(self, b"windowOpacity")
        anim_o.setStartValue(self.windowOpacity() if self.windowOpacity() > 0.0 else 0.0)
        anim_o.setEndValue(1.0)
        anim_o.setDuration(200)
        
        self.anim_group.addAnimation(anim_s)
        self.anim_group.addAnimation(anim_o)
        self.anim_group.start()

    # ------------------------------------------------------------------ #
    # Painting                                                            #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2
        cy = self.height() / 2
        
        # Apply a smooth "bump" scale based on hover, combined with global animated scale
        scale = (1.0 + (0.05 * self._hover_opacity)) * self._global_scale
        
        if scale <= 0.01:
            return # Don't draw if fully minimized
            
        painter.translate(cx, cy)
        painter.scale(scale, scale)
        painter.translate(-cx, -cy)

        w = self._bar_width
        h = self._bar_height
        rect = QRectF(cx - w / 2, cy - h / 2, w, h)
        radius = h / 2

        self._draw_background(painter, rect, radius)
        self._draw_state_overlay(painter, rect, cx, cy, w, h)
        self._draw_minimize_button(painter, rect, radius)

    def _draw_minimize_button(self, painter: QPainter, rect: QRectF, radius: float):
        if self._hover_opacity <= 0.01:
            self._min_btn_rect = None
            return
            
        r = 6.0 # radius of the button
        # Place it on the right side of the pill, securely inside the bounds
        btn_cx = rect.right() - radius
        btn_cy = rect.center().y()
        self._min_btn_rect = QRectF(btn_cx - r, btn_cy - r, r*2, r*2)
        
        painter.setOpacity(self._hover_opacity)
        painter.setBrush(QColor(255, 95, 86)) # Mac Red
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self._min_btn_rect)
        
        # Draw minus sign ONLY fluidly animating on hover
        if self._btn_hover_opacity > 0.01:
            combined_opacity = self._hover_opacity * self._btn_hover_opacity
            painter.setPen(QPen(QColor(0, 0, 0, int(150 * combined_opacity)), 1.5))
            painter.drawLine(QPointF(btn_cx - 3, btn_cy), QPointF(btn_cx + 3, btn_cy))
        
        painter.setOpacity(1.0)

    def _draw_background(self, painter: QPainter, rect: QRectF, radius: float):
        # Soft drop shadow
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(rect.translated(0, 2), radius, radius)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 40))

        # Pill fill
        if self.state == UIState.ERROR:
            r = int(10 + 245 * self._error_flash_opacity)
            bg = QColor(r, 15, 15)
        else:
            bg = QColor(10, 10, 10)

        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)


    def _draw_state_overlay(self, painter: QPainter, rect: QRectF,
                             cx: float, cy: float, w: float, h: float):
        if self.state == UIState.IDLE:
            self._draw_idle_mic(painter, cx, cy)
        elif self.state == UIState.RECORDING:
            self._draw_recording_content(painter, cx, cy, w, h)
        elif self.state == UIState.PROCESSING:
            self._draw_processing_shimmer(painter, rect, h / 2)

    def _draw_idle_mic(self, painter: QPainter, cx: float, cy: float):
        """Tiny mic symbol at 40% opacity in the centre of the idle pill."""
        painter.setOpacity(0.4)
        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(Qt.PenStyle.NoPen)
        # Body
        painter.drawRoundedRect(QRectF(cx - 1, cy - 2.5, 2, 4), 1, 1)
        # Stand arc
        painter.setPen(QPen(QColor(255, 255, 255), 0.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(cx - 2.5, cy - 0.5, 5, 4), 0, -180 * 16)
        # Stem line
        painter.drawLine(QPointF(cx, cy + 3.5), QPointF(cx, cy + 4.5))
        painter.setOpacity(1.0)

    def _draw_recording_content(self, painter: QPainter,
                                 cx: float, cy: float, w: float, h: float):
        """Red pulsing dot on the left + waveform bars.

        At silence: bars collapse to circles (dot_size × dot_size).
        When speaking: bars expand vertically driven by _bar_smooth_h.
        """
        bar_w = 4.0
        spacing = 6.0
        dot_r = 3.5
        dot_gap = 10.0  # space between dot right-edge and first bar

        bars_total_w = self._num_bars * bar_w + (self._num_bars - 1) * spacing
        content_w = dot_r * 2 + dot_gap + bars_total_w
        content_start_x = cx - content_w / 2

        # --- Red pulsing dot ---
        dot_cx = content_start_x + dot_r
        painter.setOpacity(self._dot_opacity)
        painter.setBrush(QColor(255, 55, 55))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(dot_cx, cy), dot_r, dot_r)

        # --- Per-bar waveform ---
        painter.setOpacity(1.0)
        painter.setBrush(QColor(255, 255, 255))

        bars_start_x = content_start_x + dot_r * 2 + dot_gap
        for i in range(self._num_bars):
            bx = bars_start_x + i * (bar_w + spacing)
            bar_h = max(bar_w, self._bar_smooth_h[i])  # never narrower than wide
            by = cy - bar_h / 2
            # radius = half the shorter dimension → perfect circle when bar_h ≈ bar_w
            radius = min(bar_w, bar_h) / 2
            painter.drawRoundedRect(QRectF(bx, by, bar_w, bar_h), radius, radius)

    def _draw_processing_shimmer(self, painter: QPainter, rect: QRectF, radius: float):
        """Sweeping highlight gradient across the pill."""
        grad = QLinearGradient(rect.left(), 0, rect.right(), 0)
        p = self._shimmer_pos
        grad.setColorAt(max(0.0, min(1.0, p - 0.25)), QColor(255, 255, 255, 0))
        grad.setColorAt(max(0.0, min(1.0, p)),         QColor(255, 255, 255, 55))
        grad.setColorAt(max(0.0, min(1.0, p + 0.25)), QColor(255, 255, 255, 0))

        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(rect, radius, radius)

